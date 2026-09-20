import copy
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from . import cs_client, verified_customer
from .knowledge import BOOLI_URL, HEMNET_URL, HOME_INSURANCE_TIERS, LF_PAGES, MOCK_CUSTOMERS, SERVICE_PROVIDERS

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

# Field name -> (display label, aliases the extractor should recognize in
# uploaded document text, Swedish and English) - used by fill_customer_form
# below to populate a customer form from free-text document content without
# needing a rigid, pre-agreed document format.
DEFAULT_CUSTOMER_FORM_FIELDS = (
    ("full_name", "Full name", ("Full name", "Namn", "Fullständigt namn", "full_name", "namn")),
    ("personnummer", "Personal ID number", ("Personnummer", "Personal ID number", "Personal number", "SSN", "personnummer")),
    ("date_of_birth", "Date of birth", ("Date of birth", "Födelsedatum", "Född", "DOB", "date_of_birth")),
    ("address", "Address", ("Address", "Adress", "Gatuadress", "address", "adress")),
    ("street", "Street address", ("Adress", "Address", "Gatuadress", "Street address", "Street", "street")),
    ("postnummer", "Postal code", ("Postnummer", "Postal code", "Postcode", "Zip code", "postnummer")),
    ("postcode", "Postcode", ("Postnummer", "Postcode", "Postal code", "Zip code", "postcode")),
    ("municipality", "Municipality", ("Kommun", "Municipality", "municipality")),
    ("ort", "City", ("Ort", "City", "Town", "ort", "city")),
    ("city", "City", ("Ort", "City", "Town", "Stad", "city")),
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
    the next line, common date/personnummer formats, and address components
    from labeled or unlabeled Swedish address text without inventing values.
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

    address_components = {
        "street": values.get("street", ""),
        "postcode": values.get("postcode", "") or values.get("postnummer", ""),
        "municipality": values.get("municipality", ""),
        "city": values.get("city", "") or values.get("ort", ""),
    }

    if not address_components["street"] and values.get("address"):
        address_components["street"] = values["address"]

    postcode_pattern = re.compile(r"\b\d{3}\s?\d{2}\b")
    if not address_components["postcode"]:
        for line in lines:
            cleaned = clean_line(line)
            postcode_match = postcode_pattern.search(cleaned)
            if not postcode_match:
                continue
            prefix = cleaned[:postcode_match.start()].strip(" ,;|")
            suffix = cleaned[postcode_match.end():].strip(" ,;|")
            if not address_components["street"] and prefix:
                address_components["street"] = prefix
            if not address_components["city"] and suffix:
                address_components["city"] = suffix
            address_components["postcode"] = postcode_match.group(0)
            break

    for name, value in address_components.items():
        if name in values and not values[name]:
            values[name] = value
    values["address"] = ", ".join(
        value for value in (
            address_components["street"],
            address_components["postcode"],
            address_components["municipality"],
            address_components["city"],
        ) if value
    )

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


def submit_insurance_application(history: list[dict], product: str) -> str:
    """The FORM FILLING flow's actual submission step - called once the
    customer confirms a form fill_customer_form produced. Creates a REAL
    cs-service case (visible in the CS Workspace queue, assignable to an
    advisor) instead of the flow's old behaviour of just narrating "a case
    officer will review this" with nothing behind it. Uses CaseType.OTHER
    (cs-service's Java enum has no dedicated type per insurance product -
    see CaseType.java - so this is the closest real, queueable type rather
    than inventing one the Java service would reject) with the product name
    and every filled field recorded in the case's own description/extra, so
    an advisor opening it sees exactly what was applied for.

    Takes the conversation history, not a form_json argument the model would
    have to retype from memory (unreliable - an earlier version asked the
    LLM to pass back fill_customer_form's exact JSON and it routinely came
    back empty/mangled). Instead this re-derives the fields deterministically
    by re-running fill_customer_form's own text parsing against the most
    recent assistant message that displayed the filled form - the same
    "Label: value" lines it always renders in, so parsing it back is exactly
    as reliable as parsing an uploaded document was.

    Returns the real case ID - the caller should state it verbatim in its
    reply so it round-trips through CASE_ID_RE in main.py, the same way
    every other case-creating flow in this app is picked up."""
    last_form_text = next(
        (m.get("content", "") for m in reversed(history) if m.get("role") == "assistant"), ""
    )
    try:
        fields = json.loads(fill_customer_form(last_form_text)).get("fields", [])
    except (json.JSONDecodeError, TypeError):
        fields = []
    values = {f.get("name", ""): f.get("value", "") for f in fields if f.get("value")}
    full_name = values.get("full_name") or values.get("name") or "Unknown"

    reason = f"{product} application submitted by customer via chat. " + "; ".join(
        f"{f.get('label', f.get('name', ''))}: {f.get('value', '')}" for f in fields if f.get("value")
    )
    case_id, status = cs_client.create_case_with_fallback(
        "other", full_name, None, reason, {"product": product, **values},
    )
    return f"Case created: {case_id} (status: {status})"


# Real, live comparison table on LF's car insurance page (Helförsäkring /
# Halvförsäkring / Trafikförsäkring, feature by feature) - separate from
# fetch_lf_page above because that function flattens all page text, which
# would turn this table into an unreadable jumble. Parses the actual
# <table> markup instead, targeting the specific structure LF's page uses
# (confirmed by inspecting the live HTML): each feature row's short name
# lives in a <button aria-label="..."> (the cell's own text mixes it with
# a long description), and each tier cell's text ends in "ingår" (included)
# or "ingår inte" (not included). If LF changes this structure, parsing
# quietly finds nothing/mismatches and this returns None - the caller falls
# back to fetch_lf_page's plain text rather than show a broken table.
CAR_INSURANCE_TABLE_CACHE_KEY = "car_insurance_table"


def _parse_car_insurance_table(html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        return None

    trs = table.find_all("tr")
    if not trs:
        return None

    header_cells = trs[0].find_all("th")[2:]  # first two are the feature-name/spacer columns
    columns = [
        span.get_text(strip=True)
        for th in header_cells
        for span in th.select("span.d-none.d-md-block")
    ]
    if not columns:
        return None

    rows = []
    for tr in trs[1:]:
        if tr.get("aria-hidden") == "true":
            continue  # the hidden accordion-detail row that follows each feature row
        classes = tr.get("class") or []
        if not any(c.startswith("table-block-row") for c in classes):
            continue
        button = tr.find("button")
        if not button or not button.get("aria-label"):
            continue
        feature = button["aria-label"].strip()
        value_cells = [
            td for td in tr.find_all("td")
            if "table-block-cell-first" not in (td.get("class") or [])
            and "table-block-cell-margin" not in (td.get("class") or [])
        ]
        if len(value_cells) != len(columns):
            continue  # structure didn't match what we expected - skip rather than guess
        values = [not td.get_text(strip=True).lower().endswith("inte") for td in value_cells]
        rows.append({"feature": feature, "values": values})

    if not rows:
        return None
    return {"columns": columns, "rows": rows}


def fetch_car_insurance_comparison() -> dict | None:
    """Live-fetch and parse LF Bergslagen's real car insurance comparison
    table. Returns None (never a guessed/partial table) if the live fetch
    is blocked and there's no cached copy, or if the page structure no
    longer matches what this parser expects."""
    url = LF_PAGES["car_insurance"]
    _ensure_primed()

    try:
        response = _session.get(url, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        response.encoding = response.apparent_encoding
        if _looks_blocked(response.text):
            raise requests.RequestException("blocked by anti-bot page")
        parsed = _parse_car_insurance_table(response.text)
        if parsed is None:
            raise ValueError("comparison table structure not found on page")
    except (requests.RequestException, ValueError):
        cached = _read_cache(CAR_INSURANCE_TABLE_CACHE_KEY)
        if not cached:
            return None
        try:
            return json.loads(cached)
        except json.JSONDecodeError:
            return None

    _write_cache(CAR_INSURANCE_TABLE_CACHE_KEY, json.dumps(parsed, ensure_ascii=False))
    return parsed


# Signals used to personalize the home insurance tier recommendation below -
# same AND/OR keyword-matching style as the category/stage detectors in
# agent.py, kept deterministic (no LLM guessing at the customer's situation).
CONDO_KEYWORDS = [
    "condo", "condominium", "apartment", "bostadsrätt", "bostadsratt",
    "lägenhet", "lagenhet",
]
REMOTE_WORK_KEYWORDS = [
    "work from home", "work remotely", "remote work", "working remotely",
    "hemmakontor", "distansarbete", "jobbar hemifrån",
]
FREQUENT_TRAVEL_KEYWORDS = [
    "travel a lot", "travel frequently", "frequent traveler", "travel internationally",
    "international travel", "travel often",
    "reser mycket", "reser ofta", "reser utomlands",
]


def compare_home_insurance(history: list[dict]) -> dict:
    """Return LF Bergslagen's home insurance tier comparison (Bas/Mellan/
    Stor - see HOME_INSURANCE_TIERS) plus a personalized "could be a good
    fit" pointer (never a directive recommendation - choosing a tier is the
    customer's own decision, or an LF Bergslagen advisor's to help with)
    when the conversation gives enough signal (buying a condo, working
    remotely, frequent international travel). Deterministic Python, not an
    LLM guess - mirrors the rest of this codebase's rule that any decision
    that actually matters is computed in code, with the LLM only narrating
    around it. No pointer is given (recommended_column stays None) when
    none of the signals are present, rather than defaulting to a tier that
    doesn't reflect this customer."""
    combined = " ".join(m.get("content", "") for m in history if m.get("role") == "user").lower()
    is_condo = any(kw in combined for kw in CONDO_KEYWORDS)
    remote_worker = any(kw in combined for kw in REMOTE_WORK_KEYWORDS)
    frequent_traveler = any(kw in combined for kw in FREQUENT_TRAVEL_KEYWORDS)

    recommended_column = None
    recommendation_note = None

    if frequent_traveler:
        recommended_column = 2
        recommendation_note = (
            "Since you travel internationally often, Stor could be a good fit for the extended "
            "45-day travel cover, on top of full property and belongings protection - though it's "
            "worth comparing all three yourself, or asking an LF Bergslagen advisor, before deciding."
        )
    elif is_condo or remote_worker:
        recommended_column = 1
        reasons = []
        if is_condo:
            reasons.append("you're buying a condo (bostadsrätt)")
        if remote_worker:
            reasons.append("you work remotely, often on a personal laptop")
        extras = []
        if remote_worker:
            extras.append("the Allrisk protection (covers accidents like a coffee spill on your laptop)")
        if is_condo:
            extras.append("the Bostadsrättstillägg add-on")
        recommendation_note = (
            f"Since {' and '.join(reasons)}, Mellan could be a good fit for "
            f"{' plus '.join(extras)} - Stor is probably more than you need unless you also travel "
            "internationally multiple times a year, but it's your call, or an LF Bergslagen advisor "
            "can help you weigh it."
        )

    table = copy.deepcopy(HOME_INSURANCE_TIERS)
    table["type"] = "home_insurance_tiers"
    table["recommended_column"] = recommended_column
    table["recommendation_note"] = recommendation_note
    return table


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


def find_home_search_link(location: str = "", property_type: str = "", price_range: str = "") -> str:
    """Point the customer at Booli.se and Hemnet.se - Sweden's two largest
    home-search sites - for actual apartment/villa listings. Neither site's
    live search results can be fetched into this chat (they block automated
    requests), so this never invents specific listings or a guessed deep
    link - only each site's real, verified homepage URL, plus plain
    instructions for what to search/filter for there. Also reports whether
    the location falls inside LF Bergslagen's own service area, so the agent
    can be straight about insurance. Location is optional - callable with
    none yet, to make an early, general mention of both sites."""
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
        f"Booli.se ({BOOLI_URL}) and Hemnet.se ({HEMNET_URL}) are Sweden's two largest "
        f"home-search sites, covering apartments, villas, and more all across the "
        f"country.{location_clause} Live listing data can't be pulled directly into this chat "
        "(both sites block automated access), so their own sites are the real place to see "
        "what's actually on the market right now.\n"
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
            verified_customer.mark_verified(customer["customer_id"])
            return f"VERIFIED\ncustomer_id: {customer['customer_id']}\nname: {customer['name']}"

    return (
        "NOT VERIFIED: no customer record matches that name, personnummer, and date of "
        "birth together. Do not proceed - ask the user to double-check the details, or "
        "offer to connect them with customer service instead."
    )


def verify_customer_by_personnummer(personnummer: str) -> dict | None:
    """BankID-style verification: unlike verify_customer_identity, this only
    needs the personnummer - a real BankID login already knows the signer's
    name and date of birth, so there's nothing else to ask for. Demo data
    only - looks up the mock customer directory, same as above."""
    pnr_digits = _digits_only(personnummer)
    if not pnr_digits:
        return None
    for customer in MOCK_CUSTOMERS:
        if pnr_digits == _digits_only(customer["personnummer"]):
            verified_customer.mark_verified(customer["customer_id"])
            return customer
    return None


def get_customer_portfolio(customer_id: str) -> str:
    """List a verified customer's current LF Bergslagen products, with
    each product's size, specific plan/fund name, and other useful details
    (a mortgage's rate/tenure/maturity, a policy's renewal date, etc.) -
    see knowledge.MOCK_CUSTOMERS for the structured data this reads."""
    customer = _find_customer(customer_id)
    if not customer:
        return f"Unknown customer_id '{customer_id}'."

    lines = []
    for product in customer["portfolio"]:
        header = product["name"]
        if product.get("product_type"):
            header += f" — {product['product_type']}"
        if product.get("size"):
            header += f" ({product['size']})"
        lines.append(f"- {header}")
        for key, value in (product.get("details") or {}).items():
            label = key.replace("_", " ").capitalize()
            lines.append(f"    {label}: {value}")

    return f"Current products for {customer['name']}:\n" + "\n".join(lines)


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
