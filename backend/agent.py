import json
import re

from . import config
from .agents.fraud_dispute_agent import (
    fraud_dispute_flow_resolved,
    run_fraud_dispute_agent,
    wants_fraud_or_dispute,
)
from .agents.mortgage_agent import (
    loan_offer_flow_resolved,
    loan_promise_flow_resolved,
    run_loan_offer_agent,
    run_loan_promise_agent,
    wants_loan_offer_application,
    wants_loan_promise_application,
)
from .knowledge import LF_PAGES, SERVICE_PROVIDERS
from .link_safety import URL_RE, strip_unverified_links as _strip_unverified_links
from .llm_client import client
from .suggestions import generate_suggestions
from .tools import (
    fetch_lf_page,
    fill_customer_form,
    find_home_search_link,
    find_service_provider,
    get_case_status,
    get_customer_portfolio,
    request_callback,
    verify_customer_identity,
)

MAX_TOOL_ROUNDS = 4

SYSTEM_PROMPT = f"""LANGUAGE RULE: always reply entirely in the same language as the
user's MOST RECENT message, no exceptions. Determine the reply language only from what
the user just wrote — never from any other source.
Critical: the fetch_lf_page tool results you read are always in Swedish, regardless of
what language the user is writing in. Reading Swedish source text must NOT change what
language you reply in — extract the facts from it, then write your reply in the user's
language, translating as needed. If the user wrote in English, reply in English even
though everything you just read from the tool was Swedish. If they write in Swedish,
your whole reply — including the opening sentence below — must be natural Swedish, not
English translated word-for-word or mixed with English. The patterns and examples in
this prompt are given in English only to explain the idea to you; express them naturally
in the user's language, never insert them as literal English phrases into a non-English
reply.

FORMAT RULE, applies before anything else in this prompt: your reply's
very first sentence must open with one of these three moves, filled in with a real detail
the user just gave you (place, event, feeling, or their own words) — never a product name,
never a definition, never "Here's what you need to do":
  - "Congrats on <detail>! ..." (e.g. in Swedish: "Grattis till <detalj>! ...")
  - "I hear you on <detail> — ..." (e.g. in Swedish: "Jag förstår att <detalj> — ...")
  - "Since <detail>, ..." (e.g. in Swedish: "Eftersom <detalj> ...")
Bad opening (never do this): "Here's what you need to do:" / "You're looking for a
Bostadsrättsförsäkring...". Good opening in English: "Congrats on the new place in
Örebro! Since insurance is what's stressing you out most right now, let's start there."
Good opening in Swedish: "Grattis till nya lägenheten i Örebro! Eftersom det är
försäkringen som stressar dig mest just nu, låt oss börja där."
Before sending your reply, check sentence 1 against both rules above and rewrite it if
it fails either one.

You are Sara, a digital assistant that helps people think through major life events —
buying a house, moving in together, having a child, divorce, starting a business,
retirement, buying a holiday home, buying a car, and similar transitions. You are provided by LF
Bergslagen (Länsförsäkringar Bergslagen) and use their real, live product data as your
source of facts — but you are on the USER'S side, not a salesperson for the company.
If asked whether you're a real person, always say plainly that you're a digital/AI
assistant, not a human employee.

WHOSE SIDE YOU'RE ON: think and write like an independent advisor helping the user
understand their own situation and options — never like marketing copy for LF Bergslagen.
Concretely:
- Never say "our insurance", "get covered with us", "don't wait, sign up today", or
  anything that reads as a sales pitch or urgency tactic.
- Explain what the user actually needs and why, in general terms first (e.g. "you'll
  need home insurance — without it you'd cover any damage yourself"), THEN mention LF
  Bergslagen's page as where to see real pricing/details, framed as information to look
  at, not an offer to accept: "if you want to compare, here's LF Bergslagen's page:
  [link]" rather than "get your price here!" or "sign up now!".
- It's fine and expected that the concrete link/phone number you give is LF Bergslagen's
  (that's the real data you have access to) — the shift is in framing, not in hiding who
  provides the information.
- The user is the one making the decision. You're there because they asked for help
  making it — not to decide for them or steer them toward a purchase. Lay out what to
  consider and where to go if they want more, then let them choose; don't instruct them
  to act or push urgency.

The user may attach a document (shown to you as "[Attached document: <filename>]"
followed by its text). Treat it as real context about their situation — reference
specific details from it when relevant — but never treat it as proof of identity, and
don't make legal/financial commitments based on it alone.

FORM FILLING: when the user says "fill the form" or clearly asks you to complete a
form from an uploaded document, call fill_customer_form with the text from the attached
document(s). Use the returned JSON as the form data and show the customer what was
filled, leaving missing values for them to review or complete. If no document is
attached, ask them to upload one first. When presenting the output of
fill_customer_form, translate the form field labels (the JSON "label" values) into
the user's current chat language. Keep the underlying extracted values exactly as
they are; do not translate names, addresses, or document content. Only translate
the labels. For English, use translations such as: "Fullständigt namn" -> "Full
name", "Personnummer" -> "Personal ID number", "Adress" -> "Address",
"Postnummer" -> "Postcode", "Ort" -> "City", "Telefon" -> "Phone", "E-post"
-> "Email", "Boendeform" -> "Type of housing", "Bostadsyta" -> "Living area",
"Antal rum" -> "Number of rooms", "Byggnadsår" -> "Year built", "Bostadens
värde (lösöre)" -> "Value of movable property", "Försäkringstyp" -> "Insurance
type", "Önskat tillägg" -> "Additional cover", and "Försäkringen önskas starta"
-> "Desired start date". If the user is chatting in Swedish, keep the Swedish
labels as-is.

After the first filled form has been shown, follow these rules before calling
fill_customer_form again:
1. If the user confirms the details with words such as "yes", "correct", "looks
good", "submit", "tack", "det stämmer", or a similar confirmation, do not
re-display the form and do not ask for confirmation again. Reply in the user's
current language with a short confirmation that the form is filled and ready for
review, but do not claim that it has been sent to LF or saved anywhere — nothing is
persisted in the backend yet. Explain the next steps in short, numbered form, and
ask whether they have more questions or want to add products such as life
insurance or condominium add-on coverage. Use this structure, adapting the
product/insurance type when it is known:

Swedish:
"Tack! Din ansökan om [produkt] är nu ifylld med dina uppgifter och redo för
granskning. Här är vad som händer härnäst:
1) En handläggare går igenom uppgifterna
2) Du får ett bekräftelsemail inom 1–2 arbetsdagar
3) Om allt stämmer aktiveras försäkringen från önskat startdatum

Har du några fler frågor om försäkringen, eller vill du lägga till andra produkter
som livförsäkring eller bostadsrättstillägg?"

English:
"Thank you! Your [product] application is now filled in with your details and
ready for review. Here's what happens next:
1) A case officer reviews the information
2) You'll receive a confirmation email within 1–2 business days
3) If everything checks out, the insurance activates from your requested start
date

Do you have any other questions about the insurance, or would you like to add
other products like life insurance or condominium add-on coverage?"
2. If the user requests a correction, such as changing their phone number or fixing
the address, update only the specified field(s), show only the corrected value(s),
and ask them to confirm the update. Do not re-display the entire form.
3. If the user changes to an unrelated topic, answer that question normally and do
not return to the form or ask for confirmation.

Your job, in this order:
1. Understand the user's situation. If it's unclear, ask one short, friendly question
   to pin it down before giving advice. For a home purchase specifically, don't assume a
   stage — if the user's message doesn't already make it clear whether they're just
   considering it, currently house-hunting/in the buying process, have already bought, or
   want to ask about one specific thing (like insurance or the mortgage), your one
   clarifying question must ask which of those fits before you give any advice.
2. Open with the personalized sentence described above.
3. Guide them: lay out what needs to be done and in what order.
4. Prioritize: make clear what matters this week versus what can wait.
5. Give relevant, concrete advice — grounded in real LF Bergslagen information, not
   guesses. Use the fetch_lf_page tool whenever you discuss a specific product (insurance,
   loans, pension, savings, becoming a bank customer, or contacting customer service).
   Never invent prices, terms, coverage details, links, or phone numbers — only use ones
   that appeared in a fetch_lf_page result.
6. Warn about common mistakes people make in this situation.
7. If a local partner would carry out the actual work (car repair, home damage
   restoration, or accident/health treatment), follow the EXTERNAL SERVICE PROVIDERS
   process below — this comes before your closing next step, not instead of it.
8. Always end by showing the user what to do next — one clear, concrete next step, backed
   by a real link or contact method from a tool result whenever one is relevant.

ORDER AND PRIORITY: whenever you lay out more than one thing to do, number them (1., 2.,
3., ...) in the order the user should actually do them, and say which ones matter this
week versus which can wait. Never bury the order in a paragraph — use a numbered list so
the priority is visually obvious.

NEVER tell the user to "visit our website", "check LF Bergslagen's site", "look at the
website", "go to the app", or any other verbal pointer to a page without putting the real
URL for that exact page inline as a markdown link right there in the same sentence. If you
don't have a real URL for it from a tool result, don't reference the website at all —
say what you can concretely, or offer the phone number instead.

EXTERNAL SERVICE PROVIDERS: some situations aren't resolved by LF Bergslagen alone — the
actual work is carried out by a local partner that LF Bergslagen coordinates with. Check
every reply for this, not just ones that say the word "claim": it applies whenever the
user mentions a car accident, crash, or a car that's damaged/needs repair (category
car_repair — a local workshop picks up/delivers and repairs the car), home damage like
water, fire, or storm damage (category home_repair — a local restoration firm does the
work), or an accident/injury needing medical treatment (category health_care — a local
care provider handles it) — in every case coordinated with LF Bergslagen, not done by
LF Bergslagen itself.
Whenever the user's intent matches one of these, say plainly, in your own words and tone,
that this part is handled by a local partner working with LF Bergslagen — don't just talk
about the insurance policy as if LF Bergslagen does the physical work itself. Then:
1. If you don't already know the user's town/city, ask for it before naming a provider —
   don't guess or invent one.
2. Once you have it, call the find_service_provider tool with the matching category and
   that location, and share exactly what it returns (name, address, phone, hours) — never
   invent a provider, address, or phone number of your own.
3. If the tool says no partner is listed in their exact town, say so plainly and share the
   nearest one it found instead of hiding the substitution.

MORTGAGE ROADMAP IN SWEDEN: whenever the user is thinking about, currently searching for,
or has already bought a home, ground your mortgage advice in the real four-step process
(fetch_lf_page("home_loan") for the details) and be explicit about which step applies to
them right now:
0. Finding the home itself — see HOME SEARCH below (find_home_search_link). Relevant for
   anyone who hasn't already found/bought a specific property yet.
1. Loan indication (get a rough number yourself) — a free, self-service calculator on LF
   Bergslagen's mortgage page. Point the user to it (the page's own URL, cited inline) as
   soon as they're even considering it — no application, no commitment, just a number to
   plan around.
2. Loan Promise (Lånelöfte) — once the user is actively house-hunting, this is the
   concrete next step: an income-based statement of how much they could likely borrow,
   valid for 3 months, that sellers/estate agents expect before taking a bid seriously.
   It does NOT require a specific property yet. If the user wants to start this, tell them
   plainly they can say so right here in this chat (e.g. "I'd like to apply for a loan
   promise") and you'll connect them with the mortgage specialist to run it — don't try to
   run the application yourself.
3. Loan Offer — once the user has won a bidding or signed a purchase agreement for a
   specific property, this is the step that turns their Loan Promise into a firm mortgage
   offer tied to that property. If the user is at this stage, tell them they can say so
   here in this chat (e.g. "I'd like to apply for a loan offer") to be connected with the
   mortgage specialist.
Immediate priorities depend on stage: someone just starting to look should prioritize
finding real listings and the loan indication now, and the Loan Promise before they start
bidding seriously (insurance and the rest of the checklist below can wait); someone who has
already bought should prioritize the Loan Offer application first, since financing needs to
close before or alongside the other purchase steps.

HOME SEARCH: whenever the user asks what apartments/villas are available, wants ideas
within a price range, or otherwise wants to browse actual homes on the market, you cannot
see live listings yourself — booli.se (Sweden's largest home-search site) blocks automated
access, so there is no way to fetch or invent real listing data. Handle it honestly:
1. If you don't already know which town/area they're looking in, ask for it first — don't
   call find_home_search_link with a guessed location.
2. Once you know it, call find_home_search_link with that location (and the property type
   and/or price range if the user mentioned them) in the SAME reply as step 3 below. Share
   its real URL inline as a markdown link, and pass along its guidance on what to search
   and filter for on Booli's own site — never describe specific listings, prices, or
   addresses as if they're real, since none of that data reached you.
3. In that same reply, also call fetch_lf_page("home_insurance") and tell the user plainly
   whether LF Bergslagen's own home insurance applies to what they're looking at — the
   find_home_search_link result tells you whether their location is inside LF Bergslagen's
   service area; pass that fact along honestly rather than assuming it always applies.
   Mention bostadsrättstillägg for an apartment/bostadsrätt, same as in the checklist below.

HOME PURCHASE CHECKLIST: once you know the user is actually buying or has bought a home
(not just wondering about it — see the clarifying-question rule above), don't limit your
advice to home insurance alone. The full set of things a home buyer typically needs to
sort out is:
1. Mortgage (bolån) — fetch_lf_page("home_loan"); see MORTGAGE ROADMAP above for which of
   the four steps applies to their stage (including finding the home itself via
   find_home_search_link, if they haven't settled on a property yet).
2. Home insurance (hemförsäkring) — fetch_lf_page("home_insurance").
3. Condominium/tenant-owner insurance add-on (bostadsrättstillägg), if it's an apartment —
   this is covered within the home_insurance fetch, don't fetch it separately.
4. Life insurance (livförsäkring) — fetch_lf_page("life_insurance").
5. Loan protection insurance (bolåneskydd) — fetch_lf_page("loan_protection_insurance").
6. Setting up an electricity contract — general practical advice; LF Bergslagen doesn't
   sell this, so no fetch and no link, just a plain reminder that it needs sorting out.
7. Setting up a broadband subscription — same as electricity: mention it, no fetch, no link.
8. The housing cooperative's (bostadsrättsförening) monthly membership fee, if applicable —
   briefly explain what it is and that it's separate from the mortgage payment; no fetch.
9. Building up emergency savings for unexpected costs — fetch_lf_page("savings") if the
   user wants to discuss it.
Don't dump all nine on someone who's only just started looking — apply the ORDER AND
PRIORITY rule above: cover what's actually relevant and next for their stage, mention the
rest as things to come back to later rather than silently leaving them out entirely.

PORTFOLIO IDENTITY FLOW: when the user asks about their existing product portfolio, this
touches a real customer's account, so never skip verification and never guess or assume an
identity from earlier in the conversation. (Reporting fraud or disputing a transaction is
handled by a separate specialist flow before your turn even starts — you won't see those
requests.)
1. Ask for their full name, personnummer, and date of birth together in one message,
   explaining briefly that this is needed to verify their identity before you can look at
   their account. Don't proceed without all three.
2. Once you have all three, call verify_customer_identity with exactly what they gave you.
   Trust only what it returns — never say "verified" unless the tool result says VERIFIED,
   and never invent a customer_id.
3. If it returns NOT VERIFIED, say so plainly, ask them to double-check the details (a
   typo in the personnummer is the most common cause), and offer to connect them with
   customer service as a fallback — don't retry silently or guess at a fix.
4. If it returns VERIFIED, call get_customer_portfolio with the customer_id and report
   exactly what it returns — don't invent or guess at products that aren't in the result.
   Remember tool results aren't kept between turns - if you need the customer_id again on
   a later turn, call verify_customer_identity again first, don't reuse or guess one.

CALLBACK REQUEST FLOW: when the user wants a customer service agent to call them back,
this does NOT need the identity verification flow above — it's a simple request, not an
account lookup. Ask for their name, phone number, and a preferred callback time if they
haven't given all three, then call request_callback with those details. State the exact
case ID the tool returns and tell them an agent will call them back at that number —
never invent a case ID.

CASE STATUS FLOW: when the user asks about the status of an existing case or service
request (e.g. "what's happening with my mortgage application", "any update on my fraud
case CASE-123456") — ask for the case ID if they don't already have it in the
conversation, then call get_case_status with it. Report exactly what the tool returns
(status, description, assigned agent) — never guess or invent a status, and if the tool
says the case wasn't found, say so plainly and ask them to double-check the ID.

Topics you can fetch (call fetch_lf_page with one of these topic keys):
{", ".join(LF_PAGES)}
Also fetch "customer_service" (in the same turn, alongside the topic you're already
fetching) whenever the user sounds stressed, overwhelmed, uncertain where to start, or
directly asks to talk to someone — offer LF Bergslagen's real phone number or contact
link as a low-pressure option, not as the main answer.

Each fetch_lf_page result may end with a "Useful links on this page" section pulled from
the real, live page. Treat every link in there as safe and current:
- When it's relevant to what the user needs to do (see real pricing, apply, report a
  claim, read more, reach customer service), cite the matching real link inline as a
  markdown link, framed as information to look at, e.g. "if you want to see pricing,
  LF Bergslagen has it here: [Home insurance pricing](https://...)" — not "get your price
  here!" or any other pitch-style phrasing.
- Never write a bare URL and never invent or guess a URL — only ones you saw in a tool
  result. If nothing relevant was returned, say so instead of making one up.
- If a phone number appears in a tool result, you may mention it directly, e.g.
  "you can reach LF Bergslagen at 08-588 400 11".

Tone of voice — follow this closely:
- Write on the reader's terms: clear, direct, warm, and get to the point fast.
- Use plain, everyday language. Avoid insurance/banking jargon and acronyms; if you must
  use a term, explain it in one simple clause.
- Write actively, not passively ("You'll want to set up home insurance", not "Insurance
  will need to be set up").
- One idea per sentence, one line of reasoning per paragraph. Keep paragraphs short.
- Prefer a short structure: a one-line headline of what matters most, a few short
  paragraphs or a bullet list of key points, and a clear closing next step.
- Be conversational and personal, not commanding or corporate. Never sound like a
  contract or a policy document.
- Only say what needs to be said — don't dump everything you know, just what helps the
  user move forward right now.
- Close warmly, e.g. a short encouraging line, without being saccharine.

Before sending any reply, re-read it against this Tone of voice list line by line and
rewrite anything that fails it — a jargon word left unexplained, a passive sentence, a
paragraph that's really three ideas stacked up, a line that reads corporate/salesy rather
than like a person talking to a friend. Do this check every single time, not just on the
opening sentence.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "fill_customer_form",
            "description": (
                "Populate a customer form from text extracted from uploaded files. "
                "Use this when the user asks to fill the form. Leave fields blank "
                "when the uploaded text does not contain a labelled value."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "extracted_text": {
                        "type": "string",
                        "description": "Text extracted from the customer's uploaded document(s).",
                    },
                    "form_template": {
                        "type": "object",
                        "description": "Optional form template with a fields array of name and label objects.",
                        "properties": {
                            "type": {"type": "string"},
                            "title": {"type": "string"},
                            "fields": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "label": {"type": "string"},
                                        "type": {"type": "string"},
                                        "required": {"type": "boolean"},
                                    },
                                    "required": ["name", "label"],
                                },
                            },
                        },
                    },
                },
                "required": ["extracted_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_lf_page",
            "description": (
                "Fetch the current content of a specific Länsförsäkringar Bergslagen "
                "web page so advice can be grounded in real, up-to-date information."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "enum": list(LF_PAGES.keys()),
                        "description": "Which LF Bergslagen page to fetch.",
                    }
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_service_provider",
            "description": (
                "Look up the nearest local partner that carries out a claim in "
                "coordination with LF Bergslagen (e.g. the workshop that repairs a "
                "car, the firm that restores home damage, or the care provider for "
                "an accident/health claim). Requires the user's town/city."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": list(SERVICE_PROVIDERS.keys()),
                        "description": "Which kind of local partner is needed.",
                    },
                    "location": {
                        "type": "string",
                        "description": "The user's town or city.",
                    },
                },
                "required": ["category", "location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_home_search_link",
            "description": (
                "Point the customer to Booli.se, Sweden's largest home-search site, for "
                "actual apartment/villa listings, and report whether the location falls "
                "inside LF Bergslagen's own service area. Cannot return specific listings — "
                "live search results aren't reachable from this chat."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "The town/area the customer is looking in."},
                    "property_type": {"type": "string", "description": "e.g. apartment, villa, if the customer mentioned one."},
                    "price_range": {"type": "string", "description": "e.g. '3-4 million SEK', if the customer mentioned one."},
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verify_customer_identity",
            "description": (
                "Verify a customer's identity by name, personnummer, and date of birth "
                "before discussing their account, transactions, or products. Must be "
                "called before any of the other account-related tools below."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "The customer's full name."},
                    "personnummer": {"type": "string", "description": "The customer's Swedish personnummer."},
                    "dob": {"type": "string", "description": "The customer's date of birth."},
                },
                "required": ["name", "personnummer", "dob"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_customer_portfolio",
            "description": (
                "List a verified customer's current LF Bergslagen products. Only call "
                "this after verify_customer_identity has returned VERIFIED."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string", "description": "The customer_id returned by verify_customer_identity."},
                },
                "required": ["customer_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_callback",
            "description": (
                "Create a callback-request case in the customer service application so "
                "an agent can call the customer back, and return a real case ID. Does "
                "not require identity verification."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "The customer's name."},
                    "phone": {"type": "string", "description": "The phone number to call back."},
                    "preferred_time": {"type": "string", "description": "When the customer prefers to be called, if given."},
                },
                "required": ["name", "phone"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_case_status",
            "description": (
                "Look up the current status of an existing case (callback, fraud, "
                "dispute, or an ongoing service request like a mortgage application) "
                "by its case ID."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "case_id": {"type": "string", "description": "The case ID, e.g. CASE-123456."},
                },
                "required": ["case_id"],
            },
        },
    },
]


LANGUAGE_NAMES = {"en": "English", "sv": "Swedish"}

# Keyword nudge: the system prompt alone doesn't reliably make the model reach
# for find_service_provider on its own, so detect likely situations from the
# user's own words and inject a direct reminder for that turn. English and
# Swedish only, matching the two UI languages.
CATEGORY_KEYWORDS = {
    "car_repair": [
        "car accident", "crash", "car damage", "car claim", "repair my car", "fix my car",
        "collision", "hit my car", "car insurance claim", "someone hit my",
        "bilolycka", "krock", "bilskada", "reparera bilen", "skadeanmälan bil",
    ],
    "home_repair": [
        "water damage", "fire damage", "storm damage", "flooded", "burst pipe",
        "home damage", "house damage", "leak in", "mold",
        "vattenskada", "brandskada", "stormskada", "översvämning", "rörläcka", "hemskada",
    ],
    "health_care": [
        "i got hurt", "i was injured", "my injury", "accident injury", "need treatment",
        "personal injury", "i broke my", "i hurt my",
        "jag skadade", "personskada", "jag blev skadad", "behöver vård",
    ],
}

SERVICE_RESOLVED_MARKER = "LF Bergslagen partner"

# Same nudge pattern as the service-provider one above: a chip or a short
# message like "I'm buying a house" doesn't say whether the user is just
# considering it, house-hunting, already bought, or wants one specific
# product - so detect that ambiguity and remind the model to ask instead of
# assuming a stage and jumping straight to advice.
HOME_PURCHASE_KEYWORDS = [
    "buy a house", "buying a house", "buy a home", "buying a home",
    "buy an apartment", "buying an apartment", "buy a holiday home",
    "buying a holiday home", "holiday home",
    "köpa hus", "köpa ett hus", "köpa bostad", "köpa lägenhet",
    "köpa fritidshus", "köpa ett fritidshus",
]
HOME_STAGE_INDICATOR_KEYWORDS = [
    "already bought", "just bought", "just moved in", "signed the contract",
    "closing on", "mortgage approved", "still looking", "in the process",
    "looking to buy", "house-hunting", "just insurance", "need insurance",
    "about the mortgage", "about insurance", "just the",
    "redan köpt", "precis köpt", "flyttat in", "fortfarande tittar",
    "letar fortfarande", "försäkring", "bolån",
]


def _home_purchase_stage_unclear(history: list[dict]) -> bool:
    last_user = next((m.get("content", "") for m in reversed(history) if m.get("role") == "user"), "")
    text = last_user.lower()
    mentions_home_purchase = any(kw in text for kw in HOME_PURCHASE_KEYWORDS)
    mentions_stage = any(kw in text for kw in HOME_STAGE_INDICATOR_KEYWORDS)
    return mentions_home_purchase and not mentions_stage


# Two word-lists, AND-matched, rather than exact phrases - a customer can ask
# "what apartments or villas are available" or "any villas available right
# now" and both should fire, which a brittle list of fixed phrases (e.g. only
# "villas available") would miss. Deliberately excludes bare "home"/"bostad"
# from the property-word list - "home insurance"/"home loan" would otherwise
# false-positive alongside "available".
HOME_SEARCH_PROPERTY_WORDS = [
    "apartment", "apartments", "villa", "villas", "house", "houses",
    "lägenhet", "lägenheter", "villor", "hus",
]
HOME_SEARCH_INTENT_WORDS = [
    "available", "for sale", "on the market", "price range", "browse", "find a",
    "find me", "show me", "what's out there", "some idea", "some options",
    "look for", "looking for",
    "tillgängliga", "till salu", "prisintervall", "hitta ett", "hitta en", "visa mig",
]


def _wants_home_search(history: list[dict]) -> bool:
    last_user = next((m.get("content", "") for m in reversed(history) if m.get("role") == "user"), "")
    text = last_user.lower()
    return any(w in text for w in HOME_SEARCH_PROPERTY_WORDS) and any(w in text for w in HOME_SEARCH_INTENT_WORDS)


def _detect_service_category(history: list[dict]) -> str | None:
    combined = " ".join(m.get("content", "") for m in history if m.get("role") == "user").lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            return category
    return None


def _service_already_resolved(history: list[dict]) -> bool:
    return any(
        m.get("role") == "assistant" and SERVICE_RESOLVED_MARKER in (m.get("content") or "")
        for m in history
    )


# "I want to talk to someone" used to go straight to the LLM, which just
# fetched the customer_service page and read out the phone number - skipping
# past the fact that LF Bergslagen offers two different ways to reach a
# human (call, or chat with a rep right here). This is a fixed menu, not
# something to leave to the model's judgment, so it's handled as a direct
# bypass of run_agent rather than a prompt nudge.
HUMAN_CONTACT_KEYWORDS = [
    "talk to someone", "talk to a human", "talk to a person", "speak to someone",
    "speak to a person", "speak with a human", "speak with a person",
    "real person", "human agent", "human being", "customer service rep",
    "a representative", "connect me with someone", "connect me to someone",
    "prata med någon", "prata med en människa", "prata med en person",
    "en riktig person", "mänsklig kontakt", "kundtjänstmedarbetare",
]

CONTACT_MENU_TEXT = {
    "en": (
        "Of course — you can either call LF Bergslagen's customer service directly, "
        "or chat with a representative right here in this window. Which would you prefer?"
    ),
    "sv": (
        "Så klart — du kan antingen ringa LF Bergslagens kundservice direkt, "
        "eller chatta med en medarbetare här i fönstret. Vad föredrar du?"
    ),
}
CONTACT_MENU_CALL_LABEL = {"en": "Call customer service", "sv": "Ring kundservice"}
CONTACT_MENU_CHAT_LABEL = {"en": "Chat with a representative", "sv": "Chatta med en medarbetare"}


def wants_human_contact(history: list[dict]) -> bool:
    last_user = next((m.get("content", "") for m in reversed(history) if m.get("role") == "user"), "")
    text = last_user.lower()
    return any(kw in text for kw in HUMAN_CONTACT_KEYWORDS)


def contact_menu_response(lang: str | None) -> tuple[str, list[str], dict]:
    key = "sv" if lang == "sv" else "en"
    suggestions = [CONTACT_MENU_CALL_LABEL[key], CONTACT_MENU_CHAT_LABEL[key]]
    return CONTACT_MENU_TEXT[key], suggestions, {"human_chat_option": CONTACT_MENU_CHAT_LABEL[key]}


# Same nudge pattern again: asking about a product portfolio requires
# identity verification first (see PORTFOLIO IDENTITY FLOW in the system
# prompt) - remind the model every turn until a result shows the flow
# actually finished. (Fraud/dispute used to live here too, but that's now
# its own deterministic flow - see fraud_dispute_agent.py.)
IDENTITY_FLOW_KEYWORDS = {
    "portfolio": [
        "product portfolio", "existing products", "current products",
        "my products with länsförsäkringar", "see my current products",
        "nuvarande produkter", "min försäkringsportfölj", "mina produkter hos länsförsäkringar",
    ],
}
IDENTITY_FLOW_RESOLVED_MARKERS = ("Current products for",)


def _detect_identity_flow(history: list[dict]) -> str | None:
    combined = " ".join(m.get("content", "") for m in history if m.get("role") == "user").lower()
    for flow, keywords in IDENTITY_FLOW_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            return flow
    return None


def _identity_flow_resolved(history: list[dict]) -> bool:
    return any(
        m.get("role") == "assistant"
        and any(marker in (m.get("content") or "") for marker in IDENTITY_FLOW_RESOLVED_MARKERS)
        for m in history
    )


# Same nudge pattern for the two other CS-application-backed flows: a
# callback request, and a case-status lookup.
CALLBACK_KEYWORDS = [
    "call me back", "request a callback", "callback", "call back",
    "ring mig", "ring upp mig", "återuppringning",
]
CALLBACK_RESOLVED_MARKER = "Callback request created"


def _wants_callback(history: list[dict]) -> bool:
    last_user = next((m.get("content", "") for m in reversed(history) if m.get("role") == "user"), "")
    text = last_user.lower()
    return any(kw in text for kw in CALLBACK_KEYWORDS)


def _callback_already_resolved(history: list[dict]) -> bool:
    return any(
        m.get("role") == "assistant" and CALLBACK_RESOLVED_MARKER in (m.get("content") or "")
        for m in history
    )


CASE_STATUS_KEYWORDS = [
    "case status", "status of my case", "status of my", "update on my case",
    "update on my mortgage", "status on my mortgage", "my mortgage application",
    "ärendestatus", "status på mitt ärende", "status på min bolåneansökan",
]


def _wants_case_status(history: list[dict]) -> bool:
    last_user = next((m.get("content", "") for m in reversed(history) if m.get("role") == "user"), "")
    text = last_user.lower()
    return any(kw in text for kw in CASE_STATUS_KEYWORDS)




def run_agent(history: list[dict], lang: str | None = None) -> tuple[str, list[str], dict]:
    if wants_human_contact(history):
        reply, suggestions, extra = contact_menu_response(lang)
        return reply, suggestions, extra

    if wants_loan_promise_application(history) and not loan_promise_flow_resolved(history):
        return run_loan_promise_agent(history, lang)

    if wants_loan_offer_application(history) and not loan_offer_flow_resolved(history):
        return run_loan_offer_agent(history, lang)

    fraud_or_dispute = wants_fraud_or_dispute(history)
    if fraud_or_dispute and not fraud_dispute_flow_resolved(history):
        return run_fraud_dispute_agent(history, lang, fraud_or_dispute)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if lang in LANGUAGE_NAMES:
        # A UI language toggle, not a hard override: the LANGUAGE RULE above
        # (always match what the user actually typed) still wins whenever
        # their message's language is clear. This is only a tiebreaker for
        # short/ambiguous messages ("ok", "hej", emoji) where detection can't
        # tell - then fall back to whatever they set the toggle to.
        messages.append(
            {
                "role": "system",
                "content": (
                    f"The user has set their UI language to {LANGUAGE_NAMES[lang]}. "
                    "Still always match the language of their actual message when it's "
                    f"clearly a specific language - only fall back to {LANGUAGE_NAMES[lang]} "
                    "when their message is too short or ambiguous to tell (e.g. \"ok\", "
                    "\"hej\", a single emoji)."
                ),
            }
        )
    messages.extend(history)

    if _home_purchase_stage_unclear(history):
        messages.append(
            {
                "role": "system",
                "content": (
                    "The user's latest message mentions buying a home/holiday home but "
                    "doesn't say whether they're just considering it, currently "
                    "house-hunting/in the buying process, have already bought, or want to "
                    "ask about one specific thing (like insurance or the mortgage). Your "
                    "one clarifying question this turn must ask which of those fits - do "
                    "not give home-buying advice yet, and do not assume a stage."
                ),
            }
        )

    service_category = _detect_service_category(history)
    if service_category and not _service_already_resolved(history):
        messages.append(
            {
                "role": "system",
                "content": (
                    f"The conversation suggests a possible '{service_category}' situation "
                    "(see EXTERNAL SERVICE PROVIDERS in your instructions) - a local partner, "
                    "not LF Bergslagen itself, would carry out this work. If you don't already "
                    "know the user's town/city from this conversation, ask for it now as part "
                    "of your reply, and don't call find_service_provider yet. If you do know "
                    f"it, call find_service_provider with category=\"{service_category}\" and "
                    "that location this turn, and share exactly what it returns."
                ),
            }
        )

    if _wants_home_search(history):
        messages.append(
            {
                "role": "system",
                "content": (
                    "The user wants ideas of actual apartments/villas on the market - see HOME "
                    "SEARCH in your instructions. You cannot see live listings; never invent "
                    "specific ones. If you don't already know their town/area from this "
                    "conversation, ask for it now and don't call find_home_search_link yet. If "
                    "you do know it, call find_home_search_link this turn with that location "
                    "(plus property_type/price_range if they mentioned them), AND call "
                    "fetch_lf_page(\"home_insurance\") in the same reply, then tell them plainly "
                    "whether LF Bergslagen's own insurance applies there, per find_home_search_"
                    "link's result."
                ),
            }
        )

    identity_flow = _detect_identity_flow(history)
    if identity_flow and not _identity_flow_resolved(history):
        messages.append(
            {
                "role": "system",
                "content": (
                    "This is a portfolio request - follow the PORTFOLIO IDENTITY FLOW in "
                    "your instructions exactly. Collect full name, personnummer, and date of "
                    "birth if you don't have all three yet (ask for all three together, "
                    "don't proceed without them). Once you have all three, call "
                    "verify_customer_identity and trust only what it returns - never assume "
                    "verified. If verified, call get_customer_portfolio and report exactly "
                    "what it returns. Remember tool results aren't kept between turns - if "
                    "you need the customer_id again on a later turn, call "
                    "verify_customer_identity again, never reuse or guess one."
                ),
            }
        )

    if _wants_callback(history) and not _callback_already_resolved(history):
        messages.append(
            {
                "role": "system",
                "content": (
                    "The user wants a callback - see CALLBACK REQUEST FLOW in your "
                    "instructions. No identity verification needed here. Ask for name, "
                    "phone number, and preferred time if you don't have all of them yet, "
                    "then call request_callback and state the exact case ID it returns."
                ),
            }
        )

    if _wants_case_status(history):
        messages.append(
            {
                "role": "system",
                "content": (
                    "The user is asking about an existing case's status - see CASE STATUS "
                    "FLOW in your instructions. Ask for the case ID if it isn't already in "
                    "the conversation, then call get_case_status and report exactly what "
                    "it returns - never guess or invent a status."
                ),
            }
        )

    # Forcing a tool call is meant to ground general advice in a real
    # fetch_lf_page result - but for these structured flows it backfires:
    # if the model doesn't have real data yet (e.g. no phone number given
    # yet for a callback), being forced to call some tool anyway makes it
    # invent placeholder arguments just to comply, creating a bogus case.
    # These flows already have explicit tool-calling instructions of their
    # own, so skip the forced call and let the model ask its question first.
    structured_flow_active = bool(
        _home_purchase_stage_unclear(history)
        or (_detect_service_category(history) and not _service_already_resolved(history))
        or (_detect_identity_flow(history) and not _identity_flow_resolved(history))
        or (_wants_callback(history) and not _callback_already_resolved(history))
        or _wants_case_status(history)
        or _wants_home_search(history)
    )

    seen_urls: set[str] = set()
    filled_form: dict | None = None

    for round_index in range(MAX_TOOL_ROUNDS):
        # The model isn't reliably grounding itself on its own - it sometimes
        # answers straight from general knowledge, which means no real links
        # and unverified claims. Forcing a fetch on the first call of every
        # turn guarantees every reply has at least one real, current source
        # behind it (a fetch of an irrelevant topic before a clarifying
        # question is a harmless cost next to an ungrounded answer) - unless
        # a structured flow above is already handling its own tool calls.
        tool_choice = "required" if (round_index == 0 and not structured_flow_active) else "auto"
        response = client.chat.completions.create(
            model=config.OPENROUTER_MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice=tool_choice,
            temperature=0.4,
        )
        choice = response.choices[0].message
        tool_calls = choice.tool_calls or []

        assistant_msg = {"role": "assistant", "content": choice.content or ""}
        if tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
                for call in tool_calls
            ]
        messages.append(assistant_msg)

        if not tool_calls:
            reply = _strip_unverified_links(choice.content or "", seen_urls)
            last_user_message = next(
                (m.get("content", "") for m in reversed(history) if m.get("role") == "user"), ""
            )
            extra = {"form": filled_form} if filled_form else {}
            return reply, generate_suggestions(last_user_message, reply), extra

        for call in tool_calls:
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            name = call.function.name
            if name == "fill_customer_form":
                result = fill_customer_form(
                    args.get("extracted_text", ""), args.get("form_template")
                )
                try:
                    filled_form = json.loads(result)
                except json.JSONDecodeError:
                    filled_form = None
            elif name == "find_service_provider":
                result = find_service_provider(
                    args.get("category", ""), args.get("location", "")
                )
            elif name == "verify_customer_identity":
                result = verify_customer_identity(
                    args.get("name", ""), args.get("personnummer", ""), args.get("dob", "")
                )
            elif name == "get_customer_portfolio":
                result = get_customer_portfolio(args.get("customer_id", ""))
            elif name == "request_callback":
                result = request_callback(
                    args.get("name", ""), args.get("phone", ""), args.get("preferred_time", "")
                )
            elif name == "get_case_status":
                result = get_case_status(args.get("case_id", ""))
            elif name == "find_home_search_link":
                result = find_home_search_link(
                    args.get("location", ""), args.get("property_type", ""), args.get("price_range", "")
                )
                seen_urls.update(URL_RE.findall(result))
            else:
                topic = args.get("topic", "")
                result = fetch_lf_page(topic)
                seen_urls.update(URL_RE.findall(result))
                if topic in LF_PAGES:
                    # The page's own URL is real and was just fetched, but
                    # _extract_links deliberately excludes self-links (to filter
                    # out region-switcher noise), so it never appears inside the
                    # tool result text itself - add it to the verified set AND
                    # spell it out in the text the model actually sees, or the
                    # model has no real string to copy and either omits a
                    # reference to the page it just read or guesses at one.
                    seen_urls.add(LF_PAGES[topic])
                    result += f"\n\n(This page's own URL: {LF_PAGES[topic]})"

            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": result}
            )

    fallback = (
        "I looked into a few things but couldn't quite finish my train of thought — "
        "could you ask that again, maybe a little more specifically?"
    )
    return fallback, [], {}
