"""Mortgage Agent: orchestrates the two application types a customer can
start once Sara (the main agent) hands the conversation off to it -

- Loan Promise (Lånelöfte): for a customer who's still house-hunting. No
  specific property yet, so this is an income-based affordability ceiling -
  "how much could you likely borrow" - valid for 3 months, used when bidding.
- Loan Offer: for a customer who's already won a bidding/signed a purchase
  agreement for a specific property. Needs the purchase agreement plus
  income/expenses, and produces a firm offer tied to that property.

Both share identity verification, document extraction (document_agent), and
deterministic rate/term calculations, and both create real cases in the
Customer Service application when a case needs manual review or (for a Loan
Offer) hand-off to Operations.

Design choice: conversation and document understanding go through the LLM
(this file's tool-calling loops, and document_agent's extraction call); every
number and decision that actually matters (income checks, DTI/LTV, interest
rate, monthly payment, max loan amount, the credit decision itself) is
deterministic Python, logged to the audit trail. An LLM should narrate a
mortgage decision, not make one up.
"""

import json
import re
from typing import Callable

from .. import audit, config, cs_client
from ..knowledge import LF_PAGES, MOCK_CUSTOMERS
from ..link_safety import URL_RE, strip_unverified_links
from ..llm_client import client
from ..suggestions import generate_suggestions
from ..tools import fetch_lf_page, verify_customer_by_personnummer, verify_customer_identity
from . import credit_agent, document_agent, loan_calc

MAX_TOOL_ROUNDS = 8

LOAN_PROMISE_KEYWORDS = [
    "apply for a loan promise", "get a loan promise", "want a loan promise",
    "loan promise application", "start a loan promise", "need a loan promise",
    "ansöka om lånelöfte", "ansöka om ett lånelöfte", "skaffa lånelöfte",
    "vill ha ett lånelöfte", "få ett lånelöfte", "behöver ett lånelöfte",
]

LOAN_OFFER_KEYWORDS = [
    "apply for a mortgage", "start a mortgage application", "start my mortgage",
    "apply for a home loan", "mortgage application", "want a mortgage",
    "need a mortgage", "get a mortgage", "take out a mortgage",
    "apply for a loan offer", "get a loan offer", "want a loan offer",
    "loan offer application", "start a loan offer",
    "ansöka om bolån", "ansöka om ett bolån", "starta en bolåneansökan",
    "vill ha ett bolån", "behöver ett bolån", "ta ett bolån",
    "ansöka om låneerbjudande", "vill ha ett låneerbjudande",
]

# A bare mention of "loan promise"/"lånelöfte" (or the loan-offer
# equivalent) is treated as application intent below - but "What is
# Lånelöfte?" is a customer asking for an EXPLANATION, not to start
# verifying their identity and applying. Matched against the start of the
# message (after stripping leading whitespace/punctuation) since a
# question phrased this way always leads with one of these forms.
CLARIFYING_QUESTION_RE = re.compile(
    r"^\s*(what('| i)?s|what does|explain|tell me about|how does|how do(es)? .* work|"
    r"vad är|vad betyder|förklara|hur fungerar)\b",
    re.IGNORECASE,
)


def _mentions_application_intent(history: list[dict], bare_terms: list[str], keyword_phrases: list[str]) -> bool:
    """True if some user message signals wanting to actually START an
    application - either one of the specific keyword_phrases (which already
    read as a request, e.g. "apply for a loan promise"), or a bare mention
    of the product name/term (bare_terms) in a message that isn't just
    asking what it means (see CLARIFYING_QUESTION_RE) - a customer's own
    wording varies too much for a fixed phrase list to cover every way of
    asking for one, but "what is X" is a distinct, detectable shape."""
    user_messages = [m.get("content", "") for m in history if m.get("role") == "user"]
    combined = " ".join(user_messages).lower()
    if any(kw in combined for kw in keyword_phrases):
        return True
    for msg in user_messages:
        text = msg.lower()
        if any(term in text for term in bare_terms) and not CLARIFYING_QUESTION_RE.match(msg.strip()):
            return True
    return False

# Exact phrases each flow is instructed to include verbatim at each of its
# possible endpoints - lets Sara/this file detect from plain conversation
# history whether a flow already finished, without needing separate session
# state (tool results aren't retained between turns - see the note in each
# system prompt below). Kept distinct per flow so a review/decline from one
# application type never gets mistaken for the other's resolution.
LOAN_PROMISE_RESOLVED_MARKERS = ("Loan Promise case has been created",)
LOAN_OFFER_RESOLVED_MARKERS = (
    "eligible for the loan",
    "loan offer application has been sent to a Customer Advisor",
    "unable to proceed with this loan offer application",
)

ATTACHMENT_RE = re.compile(
    r"\[Attached document:\s*(.+?)\]\n\n(.*?)(?=\n\n\[Attached document:|\Z)",
    re.DOTALL,
)

# The identity ask used to be free-form LLM text, paired with LLM-generated
# suggestion chips like "My full name is..." - which looked like real
# options but were templates the customer needed to complete. Clicking one
# sent it verbatim, which obviously never verifies, and the chips vanished
# after one click so the other two fields couldn't be given at all. A form
# with real input fields is the honest version: fill in your own values,
# submit once. Bypassing the LLM for this one specific step also makes it
# deterministic - same reliability reasoning as the rest of this module.
IDENTITY_FORM = {
    "type": "identity_details",
    "fields": [
        {"name": "full_name", "label": "Full name", "type": "text", "placeholder": "e.g. Anna Andersson"},
        {"name": "personnummer", "label": "Personnummer", "type": "text", "placeholder": "YYYYMMDD-XXXX"},
        {"name": "dob", "label": "Date of birth", "type": "text", "placeholder": "YYYY-MM-DD"},
    ],
}
ASK_IDENTITY_TEXT = {
    # loan_promise no longer uses this - it authenticates via BankID only,
    # see AUTH_CHOICE_TEXT below.
    "loan_offer": {
        "en": (
            "To start your Loan Offer application, I need to verify your identity - "
            "please fill in your details below."
        ),
        "sv": (
            "För att starta din ansökan om låneerbjudande behöver jag verifiera din "
            "identitet - fyll i dina uppgifter nedan."
        ),
    },
}

# Every Loan Promise request authenticates via BankID only - no personnummer
# form alternative. Deterministic gate, not an LLM-generated choice, for the
# same reliability reason as IDENTITY_FORM above (which loan_offer still
# uses; loan_promise no longer does).
AUTH_CHOICE_TEXT = {
    "loan_promise": {
        # Deliberately "Lånelöfte (Loan Promise)", not "Loan Promise (Lånelöfte)" -
        # the latter is a LOAN_PROMISE_RESOLVED_MARKERS string reserved for the
        # flow's actual final heading, and reusing it here made
        # loan_promise_flow_resolved() see this introductory line and treat the
        # whole application as already finished one turn in.
        "en": (
            "To start your Lånelöfte (Loan Promise) application, I first need to "
            "verify your identity via BankID."
        ),
        "sv": (
            "För att starta din ansökan om lånelöfte behöver jag först verifiera din "
            "identitet via BankID."
        ),
    },
}
AUTH_CHOICE_SUGGESTIONS = {
    "en": ["Authenticate with BankID"],
    "sv": ["Autentisera med BankID"],
}
BANKID_KEYWORD = "bankid"

# Styled card the frontend renders instead of a generic text-field form (see
# AUTH_CHOICE_FORM's "auth_choice" type in app.js) - a single BankID action
# mirroring a real Swedish bank login screen's BankID option. Pressing
# Continue sends the option's own "message" text as the next chat message,
# which _bankid_chosen below detects exactly like a clicked suggestion chip
# would.
AUTH_CHOICE_FORM = {
    "type": "auth_choice",
    "heading": {"en": "Verify your identity", "sv": "Verifiera din identitet"},
    "options": [
        {
            "value": "bankid",
            "label": "BankID",
            "helper": {
                "en": "Choose BankID for a secure and personal experience.",
                "sv": "Välj BankID för en säker och personlig upplevelse.",
            },
            "message": "Authenticate with BankID",
        },
    ],
    "default": "bankid",
    "continue_label": {"en": "Continue", "sv": "Gå vidare"},
}

# This is a demo/hackathon prototype with no real BankID integration, so
# "authenticating with BankID" is simulated as a one-click confirmation
# against a single fixed mock customer, rather than asking the customer to
# type a personnummer (which would just be a manual-entry form wearing a
# BankID label). Real BankID never asks for a personnummer either - the
# app/QR flow already knows who is confirming.
BANKID_DEMO_PERSONNUMMER = "19850312-1234"  # Anna Andersson, CUST-1001

# The document-review step's message. run_loan_promise_agent returns this
# directly, deterministically - the entire post-identity Loan Promise flow
# needs no LLM call at all any more (see the long comment in that function).
# run_loan_offer_agent still runs its phase A through a tool-calling loop
# (with assess/rate/terms/review-case excluded from its tool list, same
# LOAN_OFFER_PHASE_A_TOOLS reasoning as before) and uses this as a fallback
# if that ever slips and fabricates a plausible-looking result as plain
# text with zero tool calls behind it (tool_choice is "auto", not
# "required", so nothing stops a model from just not calling any tool).
PHASE_A_READY_TEXT = {
    "en": "I've read your documents - the extracted details are ready for you to review below.",
    "sv": "Jag har läst dina dokument - de extraherade uppgifterna är redo för dig att granska nedan.",
}

# Phase B's outcome, filled in with the real case ID from
# cs_client.create_case_with_fallback - see run_loan_promise_agent. Fixed,
# deterministic text for the same reliability reason as PHASE_A_READY_TEXT:
# an LLM asked to compose this itself would occasionally fabricate a full
# instant decision instead (specific loan amount, rate, monthly payment)
# even with no tool call or real number behind any of it.
PHASE_B_CASE_CREATED_TEXT = {
    "en": (
        "Thank you - I've reviewed your submitted details. An LF Bergslagen mortgage "
        "specialist will look at your application and reach out to you directly. Your Loan "
        "Promise case has been created - case ID: {case_id}. Is there anything else I can help "
        "you with today?"
    ),
    "sv": (
        "Tack - jag har granskat dina inskickade uppgifter. En bolånespecialist på LF "
        "Bergslagen kommer att granska din ansökan och kontakta dig direkt. Ditt "
        "lånelöfte-ärende har skapats - ärende-ID: {case_id}. Kan jag hjälpa dig med något "
        "annat idag?"
    ),
}


def _document_review_summary(extraction: dict) -> dict:
    """The document_review extra sent to the frontend - a plain summary of
    what extraction found, independent of whatever the review form's own
    fields look like."""
    return {
        "income_statement": extraction.get("income_statement"),
        "expenses": extraction.get("expenses"),
        "unclassified_documents": extraction.get("unclassified_documents", []),
        "needs_review": bool(extraction.get("needs_review")),
        "review_reason": extraction.get("review_reason"),
    }


def _user_texts_joined(history: list[dict]) -> str:
    return " ".join(m.get("content", "") for m in history if m.get("role") == "user")


def _bankid_chosen(history: list[dict]) -> bool:
    return any(
        BANKID_KEYWORD in (m.get("content", "") or "").lower()
        for m in history if m.get("role") == "user"
    )


# Before the Loan Offer flow asks for identity/documents at all, the process
# requires explaining what the customer is signing up for (the loan offer
# itself, property ownership transfer, and the title/registration process)
# and getting an explicit yes before "initiating authorization" - not just
# sliding straight into an identity form. This text is deterministic Python
# (not LLM-generated) for the same reliability reason as IDENTITY_FORM above:
# it must always end in the exact confirmation question below, every time,
# in both languages, so the flow can detect it and gate on the reply.
LOAN_OFFER_INTRO_MARKER = "Would you like to proceed with your Loan Offer application?"
LOAN_OFFER_INTRO_MARKER_SV = "Vill du gå vidare med din ansökan om låneerbjudande?"
LOAN_OFFER_INTRO_TEXT = {
    "en": (
        "Before we start, here's what a Loan Offer application involves:\n\n"
        "**What a Loan Offer is:** once you've won a bidding or signed a purchase "
        "agreement for a specific property, a Loan Offer is the bank's firm, binding "
        "mortgage terms for that property - the loan amount, interest rate, and monthly "
        "payment you'd actually get.\n\n"
        "**Property ownership:** buying the property also means transferring legal "
        "title (lagfart) into your name, and registering a mortgage deed (pantbrev) "
        "against the property as security for the loan - both handled through the Swedish "
        "Land Survey (Lantmäteriet) as part of the settlement process, alongside your loan.\n\n"
        "**Registration process:** once your loan is approved, the actual disbursement is "
        "coordinated with the property's title/mortgage-deed registration, so funds are "
        "released as ownership formally transfers to you.\n\n"
        "**Documents you'll need to upload:**\n"
        "1. **Purchase Agreement** (köpekontrakt) - the signed contract for the property, "
        "showing the price and terms.\n"
        "2. **Income Statement** - a payslip or employer statement showing your monthly "
        "gross income.\n"
        "3. **Expense details** - a summary of your regular monthly living expenses.\n\n"
        f"{LOAN_OFFER_INTRO_MARKER}"
    ),
    "sv": (
        "Innan vi börjar, här är vad en ansökan om låneerbjudande innebär:\n\n"
        "**Vad ett låneerbjudande är:** när du har vunnit en budgivning eller skrivit på "
        "ett köpekontrakt för en specifik bostad, är låneerbjudandet bankens fasta, "
        "bindande lånevillkor för just den bostaden - lånebelopp, ränta och "
        "månadskostnad.\n\n"
        "**Ägande av fastigheten:** köpet innebär också att lagfarten överförs till dig "
        "och att ett pantbrev registreras på fastigheten som säkerhet för lånet - båda "
        "hanteras via Lantmäteriet som en del av tillträdet, tillsammans med ditt lån.\n\n"
        "**Registreringsprocessen:** när lånet är godkänt samordnas utbetalningen med "
        "registreringen av lagfart och pantbrev, så pengarna betalas ut när ägandet "
        "formellt övergår till dig.\n\n"
        "**Dokument du behöver ladda upp:**\n"
        "1. **Köpekontrakt** - det undertecknade avtalet för bostaden, med pris och "
        "villkor.\n"
        "2. **Inkomstuppgift** - ett lönebesked eller arbetsgivarintyg som visar din "
        "månadslön före skatt.\n"
        "3. **Utgiftsuppgifter** - en sammanställning av dina löpande månadsutgifter.\n\n"
        f"{LOAN_OFFER_INTRO_MARKER_SV}"
    ),
}
LOAN_OFFER_INTRO_SUGGESTIONS = {
    "en": ["Yes, let's proceed", "Not right now"],
    "sv": ["Ja, jag vill gå vidare", "Inte just nu"],
}

NEGATIVE_KEYWORDS = [
    "not now", "not right now", "no thanks", "maybe later", "not yet",
    "inte nu", "inte just nu", "senare", "nej",
]


def _wants_to_proceed(history: list[dict]) -> bool:
    """Whether the customer's latest message, sent right after the Loan
    Offer intro, means "go ahead". Defaults to yes: a customer who responds
    by giving their details directly (or clicking the "Yes, let's proceed"
    suggestion chip, or anything else that isn't a clear decline) is still
    proceeding - only an explicit "not now"/"no" should stop the flow."""
    last_user = next((m.get("content", "") for m in reversed(history) if m.get("role") == "user"), "")
    text = last_user.lower()
    return not any(kw in text for kw in NEGATIVE_KEYWORDS)


def _loan_offer_intro_shown(history: list[dict]) -> bool:
    return any(
        m.get("role") == "assistant"
        and (LOAN_OFFER_INTRO_MARKER in (m.get("content") or "") or LOAN_OFFER_INTRO_MARKER_SV in (m.get("content") or ""))
        for m in history
    )


# Second confirmation gate, after all 3 documents are attached and before
# extraction/credit assessment actually runs: uploading a document isn't
# the same as saying "go ahead and process this" - the customer should get
# one explicit chance to confirm before the pipeline (identity re-check,
# document extraction, credit assessment, and a possible Advisor/Operations
# case) actually fires. Deterministic text, same reasoning as the intro gate.
LOAN_OFFER_DOCS_CONFIRM_MARKER = "Would you like me to go ahead and process your Loan Offer application now?"
LOAN_OFFER_DOCS_CONFIRM_MARKER_SV = "Vill du att jag går vidare och behandlar din ansökan om låneerbjudande nu?"
LOAN_OFFER_DOCS_CONFIRM_TEXT = {
    "en": (
        "Thanks - I've received all three documents (Purchase Agreement, Income "
        "Statement, and Expense details). Processing your application means "
        "re-verifying your identity, extracting and checking the documents, and "
        "running a credit assessment against LF Bergslagen's lending guidelines.\n\n"
        f"{LOAN_OFFER_DOCS_CONFIRM_MARKER}"
    ),
    "sv": (
        "Tack - jag har tagit emot alla tre dokument (köpekontrakt, "
        "inkomstuppgift och utgiftsuppgifter). Att behandla din ansökan innebär "
        "att vi verifierar din identitet igen, granskar dokumenten och gör en "
        "kreditbedömning enligt LF Bergslagens låneriktlinjer.\n\n"
        f"{LOAN_OFFER_DOCS_CONFIRM_MARKER_SV}"
    ),
}
LOAN_OFFER_DOCS_CONFIRM_SUGGESTIONS = {
    "en": ["Yes, go ahead", "Not yet"],
    "sv": ["Ja, gå vidare", "Inte än"],
}


def _loan_offer_docs_confirm_shown(history: list[dict]) -> bool:
    return any(
        m.get("role") == "assistant"
        and (LOAN_OFFER_DOCS_CONFIRM_MARKER in (m.get("content") or "") or LOAN_OFFER_DOCS_CONFIRM_MARKER_SV in (m.get("content") or ""))
        for m in history
    )


def wants_loan_promise_application(history: list[dict]) -> bool:
    # "loan promise"/"lånelöfte" on its own is treated as intent - a
    # suggestion chip or a customer's own wording varies ("Apply for
    # mortgage loan promise", "I'd like the loan promise please", ...) far
    # more than a fixed phrase list can enumerate, but the product name
    # itself is specific enough (never used to mean anything else in this
    # app) to trigger on alone - EXCEPT when it's just a clarifying
    # question ("What is Lånelöfte?"), see _mentions_application_intent.
    return _mentions_application_intent(history, ["loan promise", "lånelöfte"], LOAN_PROMISE_KEYWORDS)


def wants_loan_offer_application(history: list[dict]) -> bool:
    return _mentions_application_intent(history, ["loan offer", "låneerbjudande"], LOAN_OFFER_KEYWORDS)


INDICATION_KEYWORDS = [
    "indication", "loan offer", "an offer", "get an estimate", "rough estimate",
    "how much can i borrow", "what would i pay", "what would my rate",
    "indikation", "erbjudande", "en uppskattning", "hur mycket kan jag låna",
    "vad skulle jag betala",
]


def _wants_loan_indication(history: list[dict]) -> bool:
    last_user = next((m.get("content", "") for m in reversed(history) if m.get("role") == "user"), "")
    text = last_user.lower()
    return any(kw in text for kw in INDICATION_KEYWORDS)


def loan_promise_flow_resolved(history: list[dict]) -> bool:
    return any(
        m.get("role") == "assistant"
        and any(marker in (m.get("content") or "") for marker in LOAN_PROMISE_RESOLVED_MARKERS)
        for m in history
    )


def loan_offer_flow_resolved(history: list[dict]) -> bool:
    return any(
        m.get("role") == "assistant"
        and any(marker in (m.get("content") or "") for marker in LOAN_OFFER_RESOLVED_MARKERS)
        for m in history
    )


def _extract_attached_documents(history: list[dict]) -> list[dict]:
    documents = []
    for m in history:
        if m.get("role") != "user":
            continue
        for match in ATTACHMENT_RE.finditer(m.get("content") or ""):
            documents.append({"filename": match.group(1).strip(), "text": match.group(2).strip()})
    return documents


def _document_form_submitted(history: list[dict]) -> bool:
    """The frontend sends the reviewed form as a labeled user message."""
    last_user = next((m.get("content", "") for m in reversed(history) if m.get("role") == "user"), "")
    return "Monthly gross income" in last_user and "Total monthly expenses" in last_user


IDENTITY_HINT_RE = re.compile(r"\d{6,8}[-\s]?\d{4}")


def _has_identity_hint(history: list[dict]) -> bool:
    user_text = " ".join(m.get("content", "") for m in history if m.get("role") == "user")
    return bool(IDENTITY_HINT_RE.search(user_text) or _bankid_chosen(history))


def compute_transition_progress(history: list[dict]) -> dict | None:
    """Progress through whichever mortgage flow (Loan Promise or Loan Offer)
    the customer has started, derived from the same conversation-transcript
    signals the flows themselves already use (identity hint, attached
    document count, resolved markers) - no separate session state needed.
    Powers the Task Completion Ring in the chat widget. None until a flow
    has actually been started."""
    if wants_loan_offer_application(history):
        flow_label, documents_needed, resolved = "Loan Offer", 3, loan_offer_flow_resolved(history)
    elif wants_loan_promise_application(history):
        flow_label, documents_needed, resolved = "Loan Promise", 2, loan_promise_flow_resolved(history)
    else:
        return None

    steps = [
        {"label": "Application started", "done": True},
        {"label": "Identity verified", "done": _has_identity_hint(history)},
        {"label": "Documents uploaded", "done": len(_extract_attached_documents(history)) >= documents_needed},
        {"label": "Request Submitted", "done": resolved},
    ]
    completed = sum(1 for step in steps if step["done"])
    return {"flow": flow_label, "steps": steps, "percent": round(completed / len(steps) * 100)}


LOAN_PROMISE_SYSTEM_PROMPT = """You are the Mortgage Agent, a specialist that
Sara (LF Bergslagen's main digital companion) hands a conversation off to once
a customer wants to apply for a Loan Promise (Lånelöfte) - an income-based
statement of how much they could likely borrow, used BEFORE they've found a
specific property, so they're ready to bid once they find one. The customer
only ever sees this as Sara speaking (never a distinct persona introduced or
handed off to), so continue the conversation in Sara's own voice - no
self-introduction, no "I'm the specialist X connected you with" framing -
and just run the application process. Reply in the same language the
customer is writing in, matching Sara's own language rule.

THE PROCESS, IN ORDER - do not skip or reorder steps:

1. IDENTITY: if you don't already have the customer's full name, personnummer,
   and date of birth from this conversation, ask for all three together,
   explaining it's needed to verify their identity and pull up their
   account. Don't proceed without it.

LINKS: whenever you cite a URL, always use markdown link syntax
[label](url) - never write a bare URL. Only ever use a URL that appeared in
a fetch_lf_page tool result; never invent, guess, or recall one from
general knowledge, even if it looks plausible.

2. DOCUMENTS: once you have identity info, ask the customer to attach two
   documents to the chat: an income statement or payslip, and a summary of
   their monthly expenses. There is no property yet at this stage, so never
   ask for a purchase agreement here. Don't call any tool yet if fewer than
   2 documents are attached - just ask for whichever ones are still missing,
   nothing else.

   LOAN INDICATION, BEFORE DOCUMENTS ARE READY: whenever the customer asks
   for a loan indication, an estimate, or "how much can I borrow" - at any
   point before both documents are in - do two things in the same reply:
   (a) call fetch_lf_page("home_loan") and share it as the mortgage
   calculator/info link, framed as "you can get a rough estimate yourself
   here: [Räkna på bolån](<the exact URL of the page you just fetched>)" -
   that page's own URL (the one you called fetch_lf_page with, not a link
   found inside its text) IS the correct one to cite here, since that's
   LF Bergslagen's real mortgage/loan page; (b) explain plainly that to get
   an actual Loan Promise worked out here in the chat, you need the two
   documents above, and ask for whichever are still missing. Never invent
   or guess at a different URL - only the fetched page's own URL.

3. Once both documents are attached, you are no longer involved - the
   backend takes over deterministically from here (extraction, the
   review-and-submit form, and the specialist hand-off with a real case ID
   all happen in Python, not in this conversation with you). You will not
   be called again for this application until there's something outside
   that - e.g. a follow-up question - to handle.

RULES THROUGHOUT:
- Never invent a case ID, customer_id, or any figure - only ever state
  values a tool result actually returned.
- If the user asks something unrelated to this application, answer briefly
  and steer back to whichever step is still open.
"""

LOAN_OFFER_SYSTEM_PROMPT = """You are the Mortgage Agent, a specialist that
Sara (LF Bergslagen's main digital companion) hands a conversation off to once
a customer wants to apply for a Loan Offer - a firm mortgage offer tied to a
specific property they've already agreed to buy (won the bidding / signed a
purchase agreement). The customer has ALREADY seen an introduction covering
what a Loan Offer is, property ownership/registration, and the three required
documents, and has already confirmed they want to proceed - so don't repeat
that explanation, go straight into the process below. Reply in the same
language the customer is writing in, matching Sara's own language rule.

THE PROCESS, IN ORDER - do not skip or reorder steps:

1. IDENTITY (AUTHORIZATION): if you don't already have the customer's full
   name, personnummer, and date of birth from this conversation, ask for all
   three together, explaining it's needed to verify their identity and pull
   up their account. Don't proceed without it.

LINKS: whenever you cite a URL, always use markdown link syntax
[label](url) - never write a bare URL. Only ever use a URL that appeared in
a fetch_lf_page tool result; never invent, guess, or recall one from
general knowledge, even if it looks plausible.

2. DOCUMENTS: once you have identity info, ask the customer to attach the
   three required documents to the chat: the Purchase Agreement (köpekontrakt
   - the signed contract for the property, showing price and terms), an
   Income Statement (a payslip or employer statement showing monthly gross
   income), and Expense details (a summary of monthly living expenses).
   Mention, briefly and only once, that they can optionally tell you a
   specific loan amount if they don't want the default (85% of the purchase
   price, the statutory maximum loan-to-value in Sweden) - but this is NOT
   something to block on or re-ask about. The purchase price itself comes
   from the purchase agreement document, not from asking the customer
   directly - once it's attached, don't ask them to "confirm" the price
   separately. Don't call any tool yet if fewer than 3 documents are
   attached - just tell them plainly which of the three specific documents
   (by name) are still missing, nothing else, every time one is uploaded.

   LOAN INDICATION, BEFORE DOCUMENTS ARE READY: whenever the customer asks
   for a loan indication, an estimate, or "what would I pay" - at any point
   before all 3 documents are in - do two things in the same reply: (a) call
   fetch_lf_page("home_loan") and share it as the mortgage calculator/info
   link, framed as "you can get a rough estimate yourself here: [Räkna på
   bolån](<the exact URL of the page you just fetched>)" - that page's own
   URL (the one you called fetch_lf_page with, not a link found inside its
   text) IS the correct one to cite here, since that's LF Bergslagen's real
   mortgage/loan page; (b) explain plainly that to get an actual Loan Offer
   worked out here in the chat, you need the three documents above, and ask
   for whichever are still missing. Never invent or guess at a different
   URL - only the fetched page's own URL.

3. As soon as identity info AND all 3 attached documents are present,
   proceed immediately - do NOT ask about purchase price or loan amount
   again first, those are resolved inside the pipeline below (extraction
   gives the price; no stated amount means the 85% default is used
   automatically). This step always has TWO PHASES, never skip straight to
   phase B - a system message each turn tells you which phase applies now:

   PHASE A - EXTRACT AND STOP (do this whenever the reminder says this is
   the document-review step, even if documents were already attached on an
   earlier turn - tool results aren't kept between turns, so re-run these
   fresh here):
   a. verify_customer_identity.
   b. extract_mortgage_documents (the Document Extraction & Verification
      step) - reads every document attached anywhere in this conversation
      (no arguments needed).
   Then STOP - do not run credit assessment, fetch a rate, calculate terms,
   create a review case, or write out a Loan Offer result or any figures.
   Just tell the customer, in one or two sentences, that you've read their
   documents and the extracted details are ready for them to review below.

   PHASE B - DECIDE (only do this whenever the reminder says the customer
   has reviewed and submitted the extracted form):
   c. verify_customer_identity fresh here. Do NOT call
      extract_mortgage_documents again in this phase - the reminder gives
      you the extraction result (and the customer's reviewed income/expense
      figures) already; use those directly, not a fresh re-extraction that
      would silently discard any correction the customer made.
      CHECK FOR SPECIAL CONDITIONS: if the extraction's
      purchase_agreement.special_conditions is non-empty, OR needs_review is
      true for any other reason (the reminder will tell you if so), STOP
      here - do not run credit assessment. You MUST actually call the
      create_review_case tool now, in this same turn, before writing any
      reply text about it - never compose a "sent to a Customer Advisor"
      sentence without having made that real tool call first and read back
      its case ID. Call create_review_case with a `reason` that is a
      genuinely useful, plain-language summary (not just "special
      conditions exist" - say what they actually are, e.g. "the seller
      hasn't shown full title for part of the lot, and the sale is
      contingent on a boundary dispute being resolved"; if it's something
      else, like unstable employment type, explain that instead). Then tell
      the customer plainly, in your reply:
        - that same plain-language summary of what was found
        - that their application has been passed to a Customer Advisor for
          further review, and the bank will get back to her
        - the case ID
      End your reply with the exact phrase "loan offer application has been
      sent to a Customer Advisor" somewhere in the sentence.
      If there are no special conditions and needs_review is false, proceed
      to the next step.
   d. run_credit_assessment (the Credit Assessment Agent) using the
      extracted monthly_gross_income_sek, the extracted
      monthly_expenses_total_sek, the loan amount (customer-stated or 85% of
      purchase_price_sek), and property_value_sek = purchase_price_sek. This
      deterministically computes the credit score, credit recommendation,
      and eligible LTV behind the scenes.
      NEVER reveal to the customer, in this step or any later one: the
      credit_score, credit_recommendation, dti_percent, ltv_percent, or
      eligible_ltv_percent fields, any OTHER number from the tool result
      (e.g. a policy threshold like "45%" or "55%"), or any of the
      `reasons` strings verbatim (they're written for an internal audit
      trail and contain exactly those numbers) - reading a reasons string
      out loud to the customer is a violation of this rule even if you
      don't name the field. Only ever tell the customer the outcome in
      plain, qualitative terms (approved / needs manual review / not
      approved), with a qualitative reason at most (e.g. "your current
      monthly commitments relative to your income don't meet our lending
      criteria for this loan amount") - never a percentage, ratio, or
      score.
      - If the decision is MANUAL_REVIEW: STOP. Call create_review_case with
        the reasons given (this `reason` argument is internal, for the
        Advisor, so it's fine to be specific there) - tell the customer
        plainly, in the qualitative terms above, that their application has
        been passed to a Customer Advisor for further review and the bank
        will get back to her, state the case ID, and end your reply with
        the exact phrase "loan offer application has been sent to a
        Customer Advisor" somewhere in the sentence.
      - If the decision is DECLINE: STOP. Do NOT call create_review_case -
        a hard decline is not sent to an Advisor. Instead tell the customer,
        plainly and kindly, using ONLY these two facts with no numbers
        attached: that her credit score does not meet the required criteria
        as per the bank's policy, and that the bank is sorry it cannot
        proceed with this application at this point. Then call
        fetch_lf_page("customer_service") and share, inline in this same
        reply, the real phone number from its result (e.g. "you can call LF
        Bergslagen at 08-588 400 11") as where she can reach the bank's
        contact centre, and mention she can also visit her nearest branch -
        do not just name the page without the actual number. End your reply
        with the exact phrase "unable to proceed with this loan offer
        application" somewhere in the sentence.
      - If APPROVE: continue.
   e. fetch_interest_rate for this customer.
   f. calculate_loan_terms using the loan amount and the final_interest_rate_percent
      fetch_interest_rate just returned.
   f. Do NOT write out a detailed rate/payment letter to the customer - the
      exact interest rate, monthly payment, and amortization figures you
      just calculated are for the Operations case (trigger_operations_case
      below already receives them), not for reciting in chat. Instead, in
      your reply tell the customer plainly, in this shape: that based on
      the information provided, she is eligible for the loan as per LF
      Bergslagen's guidelines, and that further processing is now needed to
      finalize things. You may name the property address and confirm the
      loan amount for her own reference, but never state the interest rate,
      monthly payment, credit score, DTI, LTV, or the internal
      recommendation. Include the exact phrase "eligible for the loan"
      somewhere in the sentence.
   g. trigger_operations_case to hand off for e-signature, account opening,
      and settlement/disbursement. State the case ID it returns as part of
      the same reply as step f (not a separate message), and mention these
      operational steps are being progressively automated too.

RULES THROUGHOUT:
- Never invent a case ID, customer_id, interest rate, or any calculated
  figure - only ever state values a tool result actually returned.
- CASE ID FORMAT: a real case ID always looks like "CASE-" followed by six
  digits (e.g. CASE-552336) - that exact string only ever comes from a
  create_review_case or trigger_operations_case tool result. A customer_id
  looks completely different (e.g. CUST-1001, from verify_customer_identity)
  and is NEVER a case ID - never write a customer_id where a case ID
  belongs, and never state any case ID unless you've actually called
  create_review_case or trigger_operations_case in this turn and read the
  ID back from its result.
- Once verify_customer_identity has returned a customer_id in this reply,
  pass that exact customer_id on every later tool call in the same reply
  (extract's result doesn't need it, but run_credit_assessment,
  fetch_interest_rate, calculate_loan_terms, create_review_case, and
  trigger_operations_case all take one) - this is what lets the case
  include this customer's audit history for the Advisor/Operations.
- Every decision point above is logged to an audit trail automatically by
  the tools themselves - you don't need to do anything extra for that.
- If the user asks something unrelated to this application, answer briefly
  and steer back to whichever step is still open.
- Whenever this reply reaches a terminal outcome (a case created via
  create_review_case, a completed trigger_operations_case hand-off, or a
  decline), end with a closing question like "Is there anything else I can
  help you with today?" - not just the case ID and a description of what
  happens next.
"""

FETCH_LF_PAGE_TOOL = {
    "type": "function",
    "function": {
        "name": "fetch_lf_page",
        "description": (
            "Fetch a specific LF Bergslagen web page to ground advice in real, current "
            "information - e.g. \"home_loan\" for the mortgage calculator and general "
            "mortgage info page."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "enum": list(LF_PAGES.keys())},
            },
            "required": ["topic"],
        },
    },
}
VERIFY_IDENTITY_TOOL = {
    "type": "function",
    "function": {
        "name": "verify_customer_identity",
        "description": "Verify the applicant's identity by name, personnummer, and date of birth.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "personnummer": {"type": "string"},
                "dob": {"type": "string"},
            },
            "required": ["name", "personnummer", "dob"],
        },
    },
}
EXTRACT_DOCUMENTS_TOOL = {
    "type": "function",
    "function": {
        "name": "extract_mortgage_documents",
        "description": (
            "Extract and verify data from every document the customer has attached "
            "to this conversation (purchase agreement if present, income statement, "
            "expenses). Takes no arguments - it reads the attachments itself."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}
FETCH_INTEREST_RATE_TOOL = {
    "type": "function",
    "function": {
        "name": "fetch_interest_rate",
        "description": "Fetch the current market interest rate plus this customer's tier spread.",
        "parameters": {
            "type": "object",
            "properties": {"customer_id": {"type": "string"}},
            "required": ["customer_id"],
        },
    },
}
CALCULATE_LOAN_TERMS_TOOL = {
    "type": "function",
    "function": {
        "name": "calculate_loan_terms",
        "description": "Calculate the monthly payment for a given loan amount and interest rate.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "loan_amount_sek": {"type": "number"},
                "annual_rate_percent": {"type": "number"},
            },
            "required": ["customer_id", "loan_amount_sek", "annual_rate_percent"],
        },
    },
}
CREATE_REVIEW_CASE_TOOL = {
    "type": "function",
    "function": {
        "name": "create_review_case",
        "description": (
            "Send the application to a Customer Advisor for manual review - use this "
            "for a flagged document, a MANUAL_REVIEW credit decision, or a DECLINE."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "customer_name": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["customer_name", "reason"],
        },
    },
}

RUN_CREDIT_ASSESSMENT_TOOL = {
    "type": "function",
    "function": {
        "name": "run_credit_assessment",
        "description": "Run the retail mortgage credit decision policy for a verified customer.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "monthly_gross_income_sek": {"type": "number"},
                "monthly_expenses_sek": {"type": "number"},
                "loan_amount_sek": {"type": "number"},
                "property_value_sek": {"type": "number"},
            },
            "required": [
                "customer_id", "monthly_gross_income_sek", "monthly_expenses_sek",
                "loan_amount_sek", "property_value_sek",
            ],
        },
    },
}
TRIGGER_OPERATIONS_CASE_TOOL = {
    "type": "function",
    "function": {
        "name": "trigger_operations_case",
        "description": "Hand off an approved mortgage to Operations for e-signature, account opening, and disbursement.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "customer_name": {"type": "string"},
                "loan_amount_sek": {"type": "number"},
                "interest_rate_percent": {"type": "number"},
                "monthly_payment_sek": {"type": "number"},
                "property_address": {"type": "string"},
            },
            "required": [
                "customer_id", "customer_name", "loan_amount_sek",
                "interest_rate_percent", "monthly_payment_sek",
            ],
        },
    },
}

# Document review (before the customer has submitted the reviewed form)
# only ever offers these three tools to the model - create_review_case is
# structurally unavailable here, not just discouraged by prompt text, so a
# fabricated decision can't be backed by a real tool call. See
# PHASE_A_READY_TEXT's comment for why this alone wasn't quite enough and
# what backs it up.
LOAN_OFFER_PHASE_A_TOOLS = [FETCH_LF_PAGE_TOOL, VERIFY_IDENTITY_TOOL, EXTRACT_DOCUMENTS_TOOL]

LOAN_OFFER_TOOLS = [
    FETCH_LF_PAGE_TOOL,
    VERIFY_IDENTITY_TOOL,
    EXTRACT_DOCUMENTS_TOOL,
    RUN_CREDIT_ASSESSMENT_TOOL,
    FETCH_INTEREST_RATE_TOOL,
    CALCULATE_LOAN_TERMS_TOOL,
    CREATE_REVIEW_CASE_TOOL,
    TRIGGER_OPERATIONS_CASE_TOOL,
]

def _find_customer(customer_id: str) -> dict | None:
    return next((c for c in MOCK_CUSTOMERS if c["customer_id"] == customer_id), None)


def _stringify_extra(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(v) for v in value) if value else "None"
    return str(value)


def _build_document_form(extraction: dict | None) -> dict | None:
    """Turn extracted document data into editable fields for the customer."""
    if not extraction:
        return None

    sections = [
        (
            "Purchase agreement",
            extraction.get("purchase_agreement"),
            [
                ("property_address", "Property address"),
                ("purchase_price_sek", "Purchase price (SEK)"),
                ("buyer_name", "Buyer name"),
                ("seller_name", "Seller name"),
                ("closing_date", "Closing date"),
            ],
        ),
        (
            "Income statement",
            extraction.get("income_statement"),
            [
                ("employer", "Employer"),
                ("monthly_gross_income_sek", "Monthly gross income (SEK)"),
                ("employment_type", "Employment type"),
                ("employment_start_date", "Employment start date"),
            ],
        ),
        (
            "Monthly expenses",
            extraction.get("expenses"),
            [("monthly_expenses_total_sek", "Total monthly expenses (SEK)")],
        ),
    ]
    fields = []
    for section_label, values, field_specs in sections:
        if not values:
            continue
        for name, label in field_specs:
            value = values.get(name)
            fields.append({
                "name": name,
                "label": f"{section_label}: {label}",
                "type": "text",
                "value": "" if value is None else value,
                "required": False,
            })

    if not fields:
        return None
    return {
        "type": "document_application",
        "title": "Review application details from uploaded documents",
        "fields": fields,
    }


def _audit_history_summary(customer_id: str | None) -> str:
    """Compact trail of every agent decision recorded for this customer so
    far - the "Audit History of the agent actions/policies/calculations
    applied" a Customer Advisor or Operations agent should see on opening a
    case, per the loan-offer process spec. Pulled straight from the
    hash-chained audit log (audit.py), not re-typed by the LLM."""
    if not customer_id:
        return ""
    events = audit.read_events(customer_id)
    if not events:
        return ""
    return " | ".join(f"{e['ts']} {e['agent']}.{e['action']} -> {e['decision']}" for e in events)


def _build_case_extra(
    last_extraction: dict | None,
    last_credit_assessment: dict | None,
    customer_id: str | None,
    history: list[dict] | None = None,
    **extra_fields,
) -> dict[str, str]:
    """Merges what the customer provided (documents, via document_agent) and
    what the agents decided (via credit_agent) into the case's extra data,
    so an Advisor/Operations opening this case in the CS app sees the full
    picture, not just a one-line reason - pulled straight from the same
    structured results the pipeline itself just computed, not re-typed by
    the LLM (which could drift from the real numbers). When `history` is
    given, also attaches the uploaded document filenames and this
    customer's audit history."""
    extra: dict[str, str] = {}

    if last_extraction:
        purchase_agreement = last_extraction.get("purchase_agreement") or {}
        income_statement = last_extraction.get("income_statement") or {}
        expenses = last_extraction.get("expenses") or {}
        extra.update({
            "propertyAddress": _stringify_extra(purchase_agreement.get("property_address")),
            "purchasePriceSek": _stringify_extra(purchase_agreement.get("purchase_price_sek")),
            "sellerName": _stringify_extra(purchase_agreement.get("seller_name")),
            "specialConditions": _stringify_extra(purchase_agreement.get("special_conditions")),
            "employer": _stringify_extra(income_statement.get("employer")),
            "monthlyGrossIncomeSek": _stringify_extra(income_statement.get("monthly_gross_income_sek")),
            "employmentType": _stringify_extra(income_statement.get("employment_type")),
            "monthlyExpensesSek": _stringify_extra(expenses.get("monthly_expenses_total_sek")),
        })

    if last_credit_assessment:
        extra.update({
            "creditDecision": _stringify_extra(last_credit_assessment.get("decision")),
            "creditDecisionReasons": _stringify_extra(last_credit_assessment.get("reasons")),
            "dtiPercent": _stringify_extra(last_credit_assessment.get("dti_percent")),
            "ltvPercent": _stringify_extra(last_credit_assessment.get("ltv_percent")),
        })

    for key, value in extra_fields.items():
        extra[key] = _stringify_extra(value)

    if customer_id:
        extra["auditCustomerId"] = customer_id
        audit_summary = _audit_history_summary(customer_id)
        if audit_summary:
            extra["auditHistory"] = audit_summary

    if history is not None:
        doc_names = [d["filename"] for d in _extract_attached_documents(history)]
        if doc_names:
            extra["attachedDocuments"] = ", ".join(doc_names)

    return extra


def _run_tool_loop(
    messages: list[dict],
    tools: list[dict],
    dispatch: Callable[[str, dict], str],
    seen_urls: set[str],
) -> str | None:
    """Shared tool-calling loop for both flows below: calls the model,
    executes whatever tools it asks for via `dispatch`, and keeps going
    until it produces a final (non-tool-call) reply or MAX_TOOL_ROUNDS is
    exhausted. Returns the stripped reply text, or None if exhausted."""
    for _round_index in range(MAX_TOOL_ROUNDS):
        response = client.chat.completions.create(
            model=config.OPENROUTER_MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.3,
        )
        choice = response.choices[0].message
        tool_calls = choice.tool_calls or []

        assistant_msg = {"role": "assistant", "content": choice.content or ""}
        if tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.function.name, "arguments": call.function.arguments},
                }
                for call in tool_calls
            ]
        messages.append(assistant_msg)

        if not tool_calls:
            return strip_unverified_links(choice.content or "", seen_urls)

        for call in tool_calls:
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = dispatch(call.function.name, args)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})

    return None


def _fallback_reply(lang: str | None) -> tuple[str, list[str], dict]:
    fallback = (
        "I wasn't able to finish processing your application in this pass - "
        "could you confirm the details you've given so far, or try again?"
    )
    return fallback, [], {}


def run_loan_promise_agent(history: list[dict], lang: str | None = None) -> tuple[str, list[str], dict]:
    key = "sv" if lang == "sv" else "en"
    bankid_customer = verify_customer_by_personnummer(BANKID_DEMO_PERSONNUMMER) if _bankid_chosen(history) else None

    if not bankid_customer:
        return (
            AUTH_CHOICE_TEXT["loan_promise"][key],
            AUTH_CHOICE_SUGGESTIONS[key],
            {"form": AUTH_CHOICE_FORM},
        )

    documents_attached = len(_extract_attached_documents(history))
    form_submitted = _document_form_submitted(history)

    # Extraction is computed once, deterministically, here in Python - not
    # left to an LLM's own choice of whether/when to extract - so the review
    # form and document_review summary can never disagree with each other.
    last_extraction: dict | None = None
    if documents_attached >= 2:
        last_extraction = document_agent.extract_and_verify(_extract_attached_documents(history))

    # Once documents are in, identity (BankID-only, already resolved above)
    # and extraction are both fully deterministic, so phases A and B below
    # need no LLM call at all. This is deliberate, not just an optimization:
    # testing showed that even with assess/rate/terms tools made
    # unavailable, a tool-calling loop given LOAN_PROMISE_SYSTEM_PROMPT's
    # detailed description of the expected final format would still
    # sometimes fabricate a complete, plausible-looking Loan Promise result
    # (a specific loan amount, rate, monthly payment) as plain text, with no
    # tool call or real number behind any of it - since tool_choice is
    # "auto", nothing stops a model from just not calling any tool at all.
    # Removing the LLM from this step entirely is what actually closes that
    # gap, rather than narrowing it.
    if documents_attached >= 2:
        if not form_submitted:
            extra: dict = {"form": _build_document_form(last_extraction)}
            if last_extraction:
                extra["document_review"] = _document_review_summary(last_extraction)
            return PHASE_A_READY_TEXT[key], [], extra

        # PHASE B - hand off to a specialist. A Loan Promise is never an
        # instant automated decision the customer sees in this chat -
        # every reviewed application becomes a real case.
        income = (last_extraction or {}).get("income_statement") or {}
        expenses = (last_extraction or {}).get("expenses") or {}
        needs_review = bool((last_extraction or {}).get("needs_review"))
        review_reason = (last_extraction or {}).get("review_reason")

        reason_bits = [
            f"Employer: {income.get('employer', 'unknown')}",
            f"Monthly income: {income.get('monthly_gross_income_sek', 'unknown')} SEK",
            f"Monthly expenses: {expenses.get('monthly_expenses_total_sek', 'unknown')} SEK",
        ]
        if needs_review and review_reason:
            reason_bits.append(f"Flagged during document extraction: {review_reason}")
        reason = "Loan Promise application reviewed and submitted by customer. " + "; ".join(reason_bits)

        case_extra: dict[str, str] = {
            "applicationType": "loan_promise",
            "monthlyGrossIncomeSek": _stringify_extra(income.get("monthly_gross_income_sek")),
            "employmentType": _stringify_extra(income.get("employment_type")),
            "monthlyExpensesSek": _stringify_extra(expenses.get("monthly_expenses_total_sek")),
        }
        # Computed here for the specialist's case file only - never shown
        # to the customer in this chat.
        income_val = income.get("monthly_gross_income_sek")
        expenses_val = expenses.get("monthly_expenses_total_sek")
        if income_val is not None and expenses_val is not None:
            assessment = credit_agent.assess_loan_promise_eligibility(
                bankid_customer["customer_id"], float(income_val), float(expenses_val)
            )
            case_extra.update({
                "preliminaryDecision": _stringify_extra(assessment.get("decision")),
                "preliminaryDecisionReasons": _stringify_extra(assessment.get("reasons")),
            })
        case_extra["reason"] = reason
        case_extra["auditCustomerId"] = bankid_customer["customer_id"]

        case_id, status = cs_client.create_case_with_fallback(
            "mortgage_review", bankid_customer["name"], bankid_customer["customer_id"], reason, case_extra,
        )
        audit.record_event(
            agent="mortgage_agent", action="route_to_customer_advisor",
            customer_id=bankid_customer["customer_id"], decision="MANUAL_REVIEW",
            details={"application_type": "loan_promise", "case_id": case_id, "reason": reason, "extra": case_extra},
        )

        reply = PHASE_B_CASE_CREATED_TEXT[key].format(case_id=case_id)
        return reply, [], {}

    # Fewer than 2 documents - the only part of this flow still handled by
    # the LLM: a natural-language nudge for whichever documents are
    # missing, plus sharing the mortgage calculator link if the customer
    # asks for a rough estimate before documents are ready. No figures at
    # risk here - only fetch_lf_page is offered.
    messages = [{"role": "system", "content": LOAN_PROMISE_SYSTEM_PROMPT}]
    messages.append({
        "role": "system",
        "content": (
            "The customer authenticated via BankID using only their personnummer - a real "
            "BankID login already confirms the name and date of birth behind it, so do not ask "
            "for those separately. Their details: "
            f"full_name={bankid_customer['name']}, personnummer={bankid_customer['personnummer']}, "
            f"dob={bankid_customer['dob']}. Treat step 1 (IDENTITY) as complete with these values."
        ),
    })
    messages.extend(history)

    reminder = (
        f"Still missing: attached documents ({documents_attached}/2 so far). Ask for "
        "whichever are still missing (income statement, expenses summary) - do not call "
        "extract_mortgage_documents or any later tool yet."
    )
    if _wants_loan_indication(history):
        reminder += (
            " The customer is asking for a loan indication/estimate - in THIS reply, "
            "call fetch_lf_page(\"home_loan\") and share the real calculator link from its "
            "results, AND explain that an actual Loan Promise here in chat needs the "
            "documents above."
        )
    messages.append({"role": "system", "content": reminder})

    seen_urls: set[str] = set()

    def dispatch(name: str, args: dict) -> str:
        if name == "fetch_lf_page":
            topic = args.get("topic", "")
            result = fetch_lf_page(topic)
            seen_urls.update(URL_RE.findall(result))
            if topic in LF_PAGES:
                seen_urls.add(LF_PAGES[topic])
                result += f"\n\n(This page's own URL: {LF_PAGES[topic]})"
            return result
        return f"Unknown tool '{name}'."

    reply = _run_tool_loop(messages, [FETCH_LF_PAGE_TOOL], dispatch, seen_urls)
    if reply is None:
        return _fallback_reply(lang)

    last_user_message = next(
        (m.get("content", "") for m in reversed(history) if m.get("role") == "user"), ""
    )
    return reply, generate_suggestions(last_user_message, reply), {}


def run_loan_offer_agent(history: list[dict], lang: str | None = None) -> tuple[str, list[str], dict]:
    key = "sv" if lang == "sv" else "en"

    # Process step: before asking for anything, explain what a Loan Offer
    # application involves (the offer itself, property ownership/
    # registration, and the documents needed) and get an explicit yes
    # before "initiating authorization" - deterministic text/gate, not left
    # to the LLM, for the same reliability reason as the identity form below.
    if not _loan_offer_intro_shown(history):
        return LOAN_OFFER_INTRO_TEXT[key], LOAN_OFFER_INTRO_SUGGESTIONS[key], {}

    has_identity_hint = bool(re.search(r"\d{6,8}[-\s]?\d{4}", " ".join(
        m.get("content", "") for m in history if m.get("role") == "user"
    )))

    if not has_identity_hint:
        # This "decline" check only makes sense right after the intro -
        # scoped to here (not evaluated on every later turn) so an
        # unrelated "not yet" much later in the conversation (e.g. while
        # deciding whether to process the uploaded documents) can't be
        # misread as declining the intro itself.
        if not _wants_to_proceed(history):
            not_now_text = {
                "en": "No problem - just let me know whenever you're ready to apply for your Loan Offer.",
                "sv": "Inga problem - säg bara till när du är redo att ansöka om ditt låneerbjudande.",
            }
            return not_now_text[key], [], {}
        return ASK_IDENTITY_TEXT["loan_offer"][key], [], {"form": IDENTITY_FORM}

    documents_attached = len(_extract_attached_documents(history))

    # Second confirmation gate: having all 3 documents attached isn't the
    # same as the customer saying "go ahead and process this now" - ask
    # once, deterministically, before the pipeline (re-verification,
    # extraction, credit assessment, and a possible case) actually runs.
    if documents_attached >= 3:
        if not _loan_offer_docs_confirm_shown(history):
            return LOAN_OFFER_DOCS_CONFIRM_TEXT[key], LOAN_OFFER_DOCS_CONFIRM_SUGGESTIONS[key], {}
        if not _wants_to_proceed(history):
            not_now_processing_text = {
                "en": "No problem - your documents are saved here. Just let me know when you'd like me to go ahead.",
                "sv": "Inga problem - dina dokument finns kvar här. Säg bara till när du vill att jag går vidare.",
            }
            return not_now_processing_text[key], [], {}

    messages = [{"role": "system", "content": LOAN_OFFER_SYSTEM_PROMPT}]
    messages.extend(history)

    form_submitted = _document_form_submitted(history)

    # Computed once, deterministically, here - same reasoning as
    # run_loan_promise_agent's identical comment above: the review form,
    # document_review summary, and reminder text below must never disagree
    # with each other or depend on whether the model bothers to call
    # extract_mortgage_documents itself.
    last_extraction: dict | None = None
    if documents_attached >= 3:
        last_extraction = document_agent.extract_and_verify(_extract_attached_documents(history))

    # See LOAN_OFFER_PHASE_A_TOOLS's comment - phase B's decision tools are
    # only ever offered to the model once the form is actually submitted.
    phase_b = documents_attached >= 3 and form_submitted
    active_tools = LOAN_OFFER_TOOLS if phase_b else LOAN_OFFER_PHASE_A_TOOLS

    if documents_attached >= 3:
        special_conditions = ((last_extraction or {}).get("purchase_agreement") or {}).get("special_conditions")
        needs_review = bool((last_extraction or {}).get("needs_review")) or bool(special_conditions)
        if not form_submitted:
            reminder = (
                "PHASE A - document review step. Call verify_customer_identity and "
                "extract_mortgage_documents, then STOP: do not run credit assessment, fetch a "
                "rate, calculate terms, create a review case, or write out a Loan Offer result "
                "or any figures. Just tell the customer you've read their documents and the "
                "extracted details are ready for them to review below."
            )
        elif needs_review:
            reason = (last_extraction or {}).get("review_reason") or (
                f"special conditions in the purchase agreement: {special_conditions}"
                if special_conditions else "(none given)"
            )
            reminder = (
                f"PHASE B - needs manual review, reason: {reason!r}. Call verify_customer_identity, "
                "then create_review_case explaining this reason, then tell the customer plainly "
                "what was found, that it's been passed to a Customer Advisor, and the case ID - "
                "end with the exact phrase 'loan offer application has been sent to a Customer "
                "Advisor'. Do not call extract_mortgage_documents again, and do not continue to "
                "the credit assessment."
            )
        else:
            income = (last_extraction or {}).get("income_statement") or {}
            expenses = (last_extraction or {}).get("expenses") or {}
            purchase = (last_extraction or {}).get("purchase_agreement") or {}
            reminder = (
                "PHASE B - the customer has reviewed and submitted the extracted application "
                "form. Run the rest of the pipeline now in this reply: call "
                "verify_customer_identity, then run_credit_assessment using "
                f"monthly_gross_income_sek={income.get('monthly_gross_income_sek')}, "
                f"monthly_expenses_sek={expenses.get('monthly_expenses_total_sek')} (their "
                f"reviewed values), purchase_price_sek={purchase.get('purchase_price_sek')}, and "
                "the loan amount (customer-stated or 85% of that purchase price) - do not call "
                "extract_mortgage_documents again. Then fetch_interest_rate, calculate_loan_terms, "
                "and end with the final Loan Offer (or a review hand-off/decline per the policy "
                "result)."
            )
        messages.append({"role": "system", "content": reminder})
    else:
        # Identity is already confirmed present (handled above, before the
        # LLM is even called) - only documents can still be missing here.
        reminder = (
            f"Still missing: attached documents ({documents_attached}/3 so far). Ask for "
            "whichever are still missing - do not call extract_mortgage_documents, "
            "run_credit_assessment, or any later tool yet."
        )
        if _wants_loan_indication(history):
            reminder += (
                " The customer is asking for a loan indication/offer/estimate - in THIS reply, "
                "call fetch_lf_page(\"home_loan\") and share the real calculator link from its "
                "results, AND explain that an actual Loan Offer here in chat needs the "
                "documents above."
            )
        messages.append({"role": "system", "content": reminder})

    last_credit_assessment: dict | None = None
    seen_urls: set[str] = set()

    def dispatch(name: str, args: dict) -> str:
        nonlocal last_credit_assessment

        if name == "fetch_lf_page":
            topic = args.get("topic", "")
            result = fetch_lf_page(topic)
            seen_urls.update(URL_RE.findall(result))
            if topic in LF_PAGES:
                seen_urls.add(LF_PAGES[topic])
                result += f"\n\n(This page's own URL: {LF_PAGES[topic]})"
            return result

        if name == "verify_customer_identity":
            return verify_customer_identity(
                args.get("name", ""), args.get("personnummer", ""), args.get("dob", "")
            )

        if name == "extract_mortgage_documents":
            # Already computed once, deterministically, above - see the
            # comment by last_extraction's definition earlier in this
            # function.
            return json.dumps(last_extraction or {}, ensure_ascii=False)

        if name == "run_credit_assessment":
            last_credit_assessment = credit_agent.assess_credit(
                args.get("customer_id", ""),
                float(args.get("monthly_gross_income_sek", 0) or 0),
                float(args.get("monthly_expenses_sek", 0) or 0),
                float(args.get("loan_amount_sek", 0) or 0),
                float(args.get("property_value_sek", 0) or 0),
            )
            return json.dumps(last_credit_assessment, ensure_ascii=False)

        if name == "fetch_interest_rate":
            customer_id = args.get("customer_id", "")
            customer = _find_customer(customer_id)
            tier = customer["tier"] if customer else "Standard"
            return json.dumps(loan_calc.get_interest_rate(customer_id, tier), ensure_ascii=False)

        if name == "calculate_loan_terms":
            return json.dumps(
                loan_calc.calculate_loan_terms(
                    args.get("customer_id", ""),
                    float(args.get("loan_amount_sek", 0) or 0),
                    float(args.get("annual_rate_percent", 0) or 0),
                ),
                ensure_ascii=False,
            )

        if name == "create_review_case":
            customer_id = args.get("customer_id") or ""
            extra = _build_case_extra(
                last_extraction, last_credit_assessment, customer_id or None, history=history,
                applicationType="loan_offer", reason=args.get("reason", ""),
            )
            case_id, status = cs_client.create_case_with_fallback(
                "mortgage_review",
                args.get("customer_name", ""),
                customer_id or None,
                args.get("reason", "Loan offer application flagged for manual review."),
                extra,
            )
            audit.record_event(
                agent="mortgage_agent", action="route_to_customer_advisor",
                customer_id=customer_id or None, decision="MANUAL_REVIEW",
                details={"application_type": "loan_offer", "case_id": case_id, "reason": args.get("reason", ""), "extra": extra},
            )
            return f"Case created.\nCase ID: {case_id}\nStatus: {status}"

        if name == "trigger_operations_case":
            customer_id = args.get("customer_id", "")
            description = (
                f"Approved loan offer for {args.get('customer_name', '')}: "
                f"{args.get('loan_amount_sek')} SEK at {args.get('interest_rate_percent')}%, "
                f"monthly payment {args.get('monthly_payment_sek')} SEK. "
                f"Property: {args.get('property_address', 'n/a')}. "
                "Next: e-signature, account opening, disbursement."
            )
            extra = _build_case_extra(
                last_extraction, last_credit_assessment, customer_id or None, history=history,
                applicationType="loan_offer",
                loanAmountSek=args.get("loan_amount_sek", ""),
                interestRatePercent=args.get("interest_rate_percent", ""),
                monthlyPaymentSek=args.get("monthly_payment_sek", ""),
            )
            case_id, status = cs_client.create_case_with_fallback(
                "mortgage_operations",
                args.get("customer_name", ""),
                customer_id or None,
                description,
                extra,
            )
            audit.record_event(
                agent="mortgage_agent", action="trigger_operations_case",
                customer_id=customer_id or None, decision="APPROVED_TO_OPERATIONS",
                details={"application_type": "loan_offer", "case_id": case_id, **args, "extra": extra},
            )
            return f"Operations case created.\nCase ID: {case_id}\nStatus: {status}"

        return f"Unknown tool '{name}'."

    reply = _run_tool_loop(messages, active_tools, dispatch, seen_urls)
    if reply is None:
        return _fallback_reply(lang)
    if not phase_b and any(marker in reply for marker in LOAN_OFFER_RESOLVED_MARKERS):
        reply = PHASE_A_READY_TEXT[key]

    last_user_message = next(
        (m.get("content", "") for m in reversed(history) if m.get("role") == "user"), ""
    )
    extra = {"form": _build_document_form(last_extraction)} if last_extraction and not form_submitted else {}
    return reply, generate_suggestions(last_user_message, reply), extra
