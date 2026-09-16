import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from . import cs_client
from .knowledge import BOOLI_URL, LF_PAGES, MOCK_CUSTOMERS, SERVICE_PROVIDERS

# Towns LF Bergslagen actually serves (same list SERVICE_PROVIDERS uses for
# its local claim partners) - reused here so home-search guidance can tell a
# customer plainly whether LF Bergslagen is even the right regional insurer
# for the place they're looking, rather than assuming it always is.
LF_BERGSLAGEN_TOWNS = {city for providers in SERVICE_PROVIDERS.values() for city in {p["city"] for p in providers}}

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
}
MAX_CHARS = 6000
MAX_LINKS = 6
TIMEOUT_SECONDS = 10
CACHE_DIR = Path(__file__).resolve().parent / "cache"
DEFAULT_CUSTOMER_FORM_FIELDS = (
    ("full_name", "Full name", ("Full name", "Namn", "Fullständigt namn", "full_name", "namn")),
    ("personnummer", "Personal ID number", ("Personnummer", "Personal ID number", "Personal number", "SSN", "personnummer")),
    ("date_of_birth", "Date of birth", ("Date of birth", "Födelsedatum", "Född", "DOB", "date_of_birth")),
    ("address", "Address", ("Address", "Adress", "Gatuadress", "address", "adress")),
    ("postnummer", "Postal code", ("Postnummer", "Postal code", "Postcode", "Zip code", "postnummer")),
    ("ort", "City", ("Ort", "City", "Town", "ort", "city")),
    ("phone", "Phone", ("Phone", "Telefon", "Tel", "Mobile", "phone", "telefon")),
    ("email", "Email", ("Email", "E-mail", "Epost", "E-post", "email")),
    ("boendeform", "Type of housing", ("Boendeform", "Type of housing", "Housing type", "boendeform")),
    ("bostadsyta", "Living area (sqm)", ("Bostadsyta", "Living area (sqm)", "Living area", "Area", "bostadsyta")),
    ("antal_rum", "Number of rooms", ("Antal rum", "Number of rooms", "Rooms", "antal_rum")),
    ("byggnadsar", "Year built", ("Byggnadsår", "Year built", "Year of construction", "byggnadsar")),
    ("bostadens_varde", "Property value", ("Bostadens värde", "Value of movable property (SEK)", "Value", "bostadens_varde")),
    ("forsakringstyp", "Insurance type", ("Försäkringstyp", "Type of insurance", "Insurance type", "forsakringstyp")),
    ("onskat_tillagg_1", "Additional cover 1", ("Önskat tillägg 1", "Additional all-risk for movable property", "Additional cover 1", "onskat_tillagg_1")),
    ("onskat_tillagg_2", "Additional cover 2", ("Önskat tillägg 2", "Additional extended travel protection", "Additional cover 2", "onskat_tillagg_2")),
    ("forsakringen_startar", "Desired start date", ("Försäkringen önskas starta", "Desired start date", "Start date", "forsakringen_startar")),
    ("employer", "Employer", ("Employer", "Arbetsgivare", "employer", "arbetsgivare")),
    ("job_title", "Job title", ("Job title", "Yrke", "job title", "yrke")),
    ("annual_income", "Annual income", ("Annual income", "Årsinkomst", "annual income", "årsinkomst")),
    ("loan_amount", "Loan amount", ("Loan amount", "Lånebelopp", "loan amount", "lånebelopp")),
    ("property_address", "Property address", ("Property address", "Fastighetsadress", "property address", "fastighetsadress")),
    ("property_value", "Property value", ("Property value", "Fastighetsvärde", "property value", "fastighetsvärde")),
    ("policy_type", "Policy type", ("Policy type", "Försäkringstyp", "policy type", "försäkringstyp")),
    ("coverage_amount", "Coverage amount", ("Coverage amount", "Försäkringsbelopp", "coverage amount", "försäkringsbelopp")),
    ("monthly_premium", "Monthly premium", ("Monthly premium", "Månadspremie", "monthly premium", "månadspremie")),
)

# Keywords that mark a link as worth surfacing to the agent (get-a-price /
# buy / contact-a-human actions), so it can give concrete next steps instead
# of vague ones. Split into text vs. href keywords because every href on
# this site contains "lansforsakringar.se", which itself contains "ring" -
# matching hrefs on a bare substring like that would let almost any link through.
USEFUL_TEXT_KEYWORDS = (
    "kontakt", "kundservice", "kundtj", "ring oss", "chatt",
    "pris", "köp", "teckna", "ansök", "ansok", "skadeanmal",
)
USEFUL_HREF_KEYWORDS = (
    "tel:", "mailto:", "/kundservice", "/kundtjanst", "/kontakt",
    "/skadeanmalan", "/kop/",
)
# Transactional links (call us, get a price, apply) matter more than generic
# footer nav ("Kundservice", "Bank & pension") that repeats on every page.
PRIORITY_HREF_PREFIXES = ("tel:", "mailto:")
PRIORITY_TEXT_KEYWORDS = ("pris", "köp", "teckna", "ansök", "ansok")
MAX_LINK_TEXT_CHARS = 60

# Overview page primes the "bolagskod" region cookie so pages that don't
# carry /bergslagen/ in their path (e.g. the shared customer-service page)
# still resolve to LF Bergslagen content instead of a random default region.
_PRIMING_URL = LF_PAGES["overview"]

_session = requests.Session()
_session.headers.update(BROWSER_HEADERS)
_primed = False


def _ensure_primed() -> None:
    global _primed
    if _primed:
        return
    try:
        _session.get(_PRIMING_URL, timeout=TIMEOUT_SECONDS)
    except requests.RequestException:
        pass
    _primed = True


def _cache_path(topic: str) -> Path:
    return CACHE_DIR / f"{topic}.txt"


def _read_cache(topic: str) -> str | None:
    path = _cache_path(topic)
    return path.read_text(encoding="utf-8") if path.exists() else None


def _write_cache(topic: str, text: str) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    _cache_path(topic).write_text(text, encoding="utf-8")


def _looks_blocked(html: str) -> bool:
    # LF's WAF serves a tiny "Stopp!" interstitial instead of the real page
    # when a request looks bot-like. Treat that as a failed fetch.
    return len(html) < 2000 or "support-ID" in html or ">Stopp!<" in html


def _link_priority(text_lower: str, href_lower: str) -> int:
    if href_lower.startswith(PRIORITY_HREF_PREFIXES):
        return 0
    if any(kw in text_lower for kw in PRIORITY_TEXT_KEYWORDS):
        return 0
    return 1


def _extract_links(soup: BeautifulSoup, page_url: str) -> list[tuple[str, str]]:
    seen: set[str] = set()
    candidates: list[tuple[int, str, str]] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = " ".join(a.get_text(separator=" ").split())
        if not text or href.lower().startswith("mailto:?"):
            continue  # "share this page by email" links, not a real contact address
        absolute = urljoin(page_url, href)
        text_lower, href_lower = text.lower(), href.lower()
        matches = any(kw in text_lower for kw in USEFUL_TEXT_KEYWORDS) or any(
            kw in href_lower for kw in USEFUL_HREF_KEYWORDS
        )
        if not matches:
            continue
        if absolute == page_url or absolute in seen:
            continue
        seen.add(absolute)
        if len(text) > MAX_LINK_TEXT_CHARS:
            text = text[: MAX_LINK_TEXT_CHARS - 1].rstrip() + "…"
        candidates.append((_link_priority(text_lower, href_lower), text, absolute))

    candidates.sort(key=lambda c: c[0])
    return [(text, url) for _, text, url in candidates[:MAX_LINKS]]


def _extract_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return " ".join(soup.get_text(separator=" ").split())[:MAX_CHARS]


def _format_result(text: str, links: list[tuple[str, str]]) -> str:
    if not links:
        return text
    link_lines = "\n".join(f"- {label}: {url}" for label, url in links)
    return f"{text}\n\nUseful links on this page:\n{link_lines}"


def fetch_lf_page(topic: str) -> str:
    url = LF_PAGES.get(topic)
    if not url:
        return f"Unknown topic '{topic}'. Valid topics: {', '.join(LF_PAGES)}"

    _ensure_primed()

    try:
        response = _session.get(url, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        response.encoding = response.apparent_encoding
        if _looks_blocked(response.text):
            raise requests.RequestException("blocked by anti-bot page")

        soup = BeautifulSoup(response.text, "html.parser")
        links = _extract_links(soup, response.url)
        text = _extract_text(soup)
        result = _format_result(text, links)
    except requests.RequestException:
        cached = _read_cache(topic)
        if cached:
            return f"[Live fetch failed, using last saved copy of this page]\n{cached}"
        return (
            f"Could not fetch {url} right now, and no cached copy is available. "
            "Answer from general knowledge and suggest the user check the page directly."
        )

    _write_cache(topic, result)
    return result


def fill_customer_form(extracted_text: str, form_template: dict | None = None) -> str:
    """Populate a form from realistic Swedish insurance application text.

    Handles Swedish and English aliases, bullets, bold headings with values on
    the next line, common date/personnummer formats, spaced currency amounts,
    and postcode/city address continuations without inventing missing values.
    """
    default_fields = {
        name: (label, aliases)
        for name, label, aliases in DEFAULT_CUSTOMER_FORM_FIELDS
    }
    template = form_template or {
        "type": "customer_details",
        "title": "Customer details from uploaded document",
        "fields": [
            {"name": name, "label": label, "type": "text"}
            for name, (label, _aliases) in default_fields.items()
        ],
    }

    lines = (extracted_text or "").splitlines()

    def clean_line(line: str) -> str:
        # Accept Markdown bullets/headings without letting their markers become field values.
        return re.sub(r"^\s*(?:[-*•]\s+|#+\s*)", "", line).strip()

    def field_aliases(name: str, label: str) -> list[str]:
        aliases = set(default_fields.get(name, ("", ()))[1])
        aliases.update({label, name, name.replace("_", " ")})
        return sorted((alias for alias in aliases if alias), key=lambda alias: len(_fold(alias)), reverse=True)

    def find_fields(line: str, field_specs: list[tuple[str, str]]) -> list[tuple[int, int, str, str, str]]:
        cleaned = clean_line(line)
        folded = _fold(cleaned)
        candidates = []
        for name, label in field_specs:
            for alias in field_aliases(name, label):
                folded_alias = _fold(alias)
                # Search the folded line so Swedish accents and unaccented OCR both match.
                pattern = rf"(?<!\w)(?:\*\*)?{re.escape(folded_alias)}(?:\*\*)?\s*(?::|=|-)(?:\s*)"
                for match in re.finditer(pattern, folded, re.IGNORECASE):
                    candidates.append((match.start(), match.end(), name, label, match.group(0)))
        candidates.sort(key=lambda candidate: (candidate[0], -(candidate[1] - candidate[0])))
        matches = []
        for candidate in candidates:
            if any(candidate[0] >= existing[0] and candidate[1] <= existing[1] for existing in matches):
                continue
            matches.append(candidate)
        return matches

    def find_heading(line: str, field_specs: list[tuple[str, str]]) -> tuple[str, str] | None:
        cleaned = clean_line(line)
        folded = _fold(cleaned)
        for name, label in field_specs:
            for alias in field_aliases(name, label):
                alias_pattern = re.escape(_fold(alias))
                # Bold-only headings use the following line as their value.
                if re.fullmatch(rf"\*\*{alias_pattern}\*\*\s*:?[\s]*", folded, re.IGNORECASE):
                    return name, label
        return None

    def clean_value(value: str) -> str:
        return re.sub(r"\*\*$", "", value).strip()

    field_specs = [
        (str(field.get("name", "field")), str(field.get("label", field.get("name", "field").replace("_", " ").title())))
        for field in template.get("fields", [])
    ]
    values = {name: "" for name, _label in field_specs}
    for index, line in enumerate(lines):
        found_fields = find_fields(line, field_specs)
        if not found_fields:
            heading = find_heading(line, field_specs)
            if not heading:
                continue
            name, _label = heading
            value = clean_value(clean_line(lines[index + 1])) if index + 1 < len(lines) else ""
            if value:
                values[name] = value
            continue
        for field_index, match in enumerate(found_fields):
            start, end, name, _label, _matched = match
            next_start = found_fields[field_index + 1][0] if field_index + 1 < len(found_fields) else len(clean_line(line))
            value = clean_value(clean_line(line)[end:next_start].strip(" ,;|"))
            if not value and field_index == 0 and index + 1 < len(lines):
                next_line = clean_line(lines[index + 1])
                if next_line and not find_fields(next_line, field_specs) and not find_heading(next_line, field_specs):
                    value = next_line

            if name == "personnummer":
                # Swedish personnummer may be written with either a two- or four-digit year.
                personnummer = re.search(r"\b(?:\d{6}|\d{8})-\d{4}\b", value)
                value = personnummer.group(0) if personnummer else ""

            if name in {"address", "property_address"} and value and field_index == len(found_fields) - 1:
                continuation = clean_line(lines[index + 1]) if index + 1 < len(lines) else ""
                if continuation and not find_fields(continuation, field_specs) and not find_heading(continuation, field_specs):
                    if re.search(r"\b\d{3}\s?\d{2}\b", continuation) or len(continuation) <= 80:
                        value = f"{value}, {continuation}"
            if value:
                values[name] = value

    populated_fields = []
    for field in template.get("fields", []):
        name = str(field.get("name", "field"))
        label = str(field.get("label", name.replace("_", " ").title()))
        populated_fields.append({
            **field,
            "name": name,
            "label": label,
            "value": values.get(name, ""),
            "required": field.get("required", False),
        })

    return json.dumps({**template, "fields": populated_fields}, ensure_ascii=False)


def find_service_provider(category: str, location: str) -> str:
    """Look up the nearest partner that would actually carry out a claim
    (e.g. the workshop that picks up and repairs a car), coordinated with
    LF Bergslagen. Demo data: matches by town name, falling back to the
    closest regional hub rather than inventing a provider."""
    providers = SERVICE_PROVIDERS.get(category)
    if not providers:
        return f"Unknown service category '{category}'. Valid categories: {', '.join(SERVICE_PROVIDERS)}"

    location_norm = _fold(location)
    match = next((p for p in providers if _fold(p["city"]) in location_norm or location_norm in _fold(p["city"])), None)
    provider = match or providers[0]
    note = "" if match else (
        f" No partner is listed in {location.strip()} itself, so this is the nearest one in the network:"
    )

    return (
        f"Nearest LF Bergslagen partner for this claim:{note}\n"
        f"- {provider['name']}\n"
        f"- Address: {provider['address']}\n"
        f"- Phone: {provider['phone']}\n"
        f"- Hours: {provider['hours']}\n"
        "This partner works directly with LF Bergslagen to carry out the claim "
        "(e.g. pickup/delivery or repair is coordinated between them and LF Bergslagen)."
    )



def _fold(text: str) -> str:
    """Lowercase and strip diacritics (Örebro -> orebro) so a town match
    doesn't depend on whether the customer/model typed Swedish characters -
    "Orebro" and "Malmo" are common ASCII spellings of "Örebro"/"Malmö"."""
    decomposed = unicodedata.normalize("NFKD", (text or "").strip().lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _in_lf_bergslagen_area(location: str) -> bool:
    location_norm = _fold(location)
    return any(_fold(town) in location_norm or location_norm in _fold(town) for town in LF_BERGSLAGEN_TOWNS)


def find_home_search_link(location: str, property_type: str = "", price_range: str = "") -> str:
    """Point the customer at Booli.se - Sweden's largest home-search site -
    for actual apartment/villa listings. Booli.se's live search results can't
    be fetched into this chat (they block automated requests), so this never
    invents specific listings or a guessed deep link - only the site's real,
    verified homepage URL, plus plain instructions for what to search/filter
    for there. Also reports whether the location falls inside LF Bergslagen's
    own service area, so the agent can be straight about insurance."""
    location = (location or "").strip()
    filters = []
    if property_type:
        filters.append(property_type)
    if price_range:
        filters.append(f"in the {price_range} range")
    filter_clause = f", filtering for {' '.join(filters)}" if filters else ""
    location_clause = f' Search for "{location}"{filter_clause} once you\'re there.' if location else ""

    in_area = _in_lf_bergslagen_area(location) if location else None
    if in_area is True:
        area_note = f"{location} is inside LF Bergslagen's own service area, so their home insurance applies there."
    elif in_area is False:
        area_note = (
            f"{location} is outside LF Bergslagen's own service area (they cover the "
            "Örebro/Bergslagen region) - a different regional Länsförsäkringar company would "
            "be the one to actually insure a home there, though LF Bergslagen's home insurance "
            "page is still useful as general information on what to expect."
        )
    else:
        area_note = "Once you know the town, I can say whether LF Bergslagen's own home insurance applies there."

    return (
        f"Booli.se ({BOOLI_URL}) is Sweden's largest home-search site, covering apartments, "
        f"villas, and more all across the country.{location_clause} Live listing data can't be "
        "pulled directly into this chat (booli.se blocks automated access), so Booli's own site "
        "is the real place to see what's actually on the market right now.\n"
        f"{area_note}"
    )


def _digits_only(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _find_customer(customer_id: str) -> dict | None:
    return next((c for c in MOCK_CUSTOMERS if c["customer_id"] == customer_id), None)


def verify_customer_identity(name: str, personnummer: str, dob: str) -> str:
    """Check a name + personnummer + date of birth against the mock
    customer directory. Demo data only - never invent a match."""
    name_norm = (name or "").strip().lower()
    pnr_digits = _digits_only(personnummer)
    dob_digits = _digits_only(dob)

    for customer in MOCK_CUSTOMERS:
        record_pnr_digits = _digits_only(customer["personnummer"])
        record_dob_digits = _digits_only(customer["dob"])
        name_matches = name_norm and name_norm in customer["name"].lower()
        pnr_matches = pnr_digits and pnr_digits == record_pnr_digits
        dob_matches = dob_digits and (
            dob_digits == record_dob_digits or record_pnr_digits.startswith(dob_digits)
        )
        if name_matches and pnr_matches and dob_matches:
            return f"VERIFIED\ncustomer_id: {customer['customer_id']}\nname: {customer['name']}"

    return (
        "NOT VERIFIED: no customer record matches that name, personnummer, and date of "
        "birth together. Do not proceed - ask the user to double-check the details, or "
        "offer to connect them with customer service instead."
    )


def get_customer_portfolio(customer_id: str) -> str:
    """List a verified customer's current LF Bergslagen products."""
    customer = _find_customer(customer_id)
    if not customer:
        return f"Unknown customer_id '{customer_id}'."
    lines = "\n".join(f"- {p}" for p in customer["portfolio"])
    return f"Current products for {customer['name']}:\n{lines}"


def request_callback(name: str, phone: str, preferred_time: str = "") -> str:
    """Create a callback-request case in the Customer Service application so
    a CS agent can pick it up and call the customer back."""
    description = f"Customer requested a callback. Preferred time: {preferred_time or 'not specified'}."
    case_id, status = cs_client.create_case_with_fallback(
        "callback", name, None, description, {"phone": phone, "preferredTime": preferred_time}
    )
    return (
        "Callback request created.\n"
        f"Case ID: {case_id}\n"
        f"Status: {status}\n"
        "A customer service agent will call you back at the number you provided."
    )


def get_case_status(case_id: str) -> str:
    """Look up an existing case's status in the Customer Service application
    - e.g. an ongoing mortgage application, or an earlier fraud/dispute/
    callback case. Never invent a status; only report what the tool finds."""
    result = cs_client.get_case(case_id)
    if result is None:
        return "Could not reach the Customer Service application to check this case's status right now."
    if result.get("not_found"):
        return f"No case found with ID '{case_id}'. Double-check the case ID with the user."

    extra_lines = "\n".join(f"{k}: {v}" for k, v in (result.get("extra") or {}).items())
    return (
        f"Case {result.get('id')}\n"
        f"Type: {result.get('type')}\n"
        f"Status: {result.get('status')}\n"
        f"Description: {result.get('description')}\n"
        f"Assigned agent: {result.get('assignedAgent') or 'Not yet assigned'}\n"
        f"Last updated: {result.get('updatedAt') or result.get('createdAt')}"
        + (f"\n{extra_lines}" if extra_lines else "")
    )
