#!/usr/bin/env python3
"""Shared Title IX / sexual-violence classifier definitions.

These definitions are copied verbatim from the original
``scripts/analyze_title_ix_sexual_violence.py`` run so that the 2026-only trend
analysis is directly comparable.  Both scripts import this module.

All patterns are case-insensitive, Unicode-aware word-boundary regexes.
"""

from __future__ import annotations

import re

PATTERNS = {
    # Title IX, including common OCR/keyboard variants.  "IX" alone is never
    # searched; it must follow "Title" / "Tit1e".
    "title_ix": r"\btit(?:le|1e|ie)\s*[:\-]?\s*(?:ix|9|i\s*x|lx|1x)\b",

    # Sexual violence / assault / rape family.
    "sexual_violence": r"\bsexual(?:ly)?[\s-]+violence\b|\bsex[\s-]+violence\b",
    "sexual_assault": r"\bsexual(?:ly)?[\s-]+assault(?:s|ed|ing|er|ers)?\b|\bsex[\s-]+assault(?:s|ed|ing|er|ers)?\b",
    "rape": r"\brap(?:e|es|ed|ing|ist|ists)\b",
    "sexual_abuse": r"\bsexual(?:ly)?[\s-]+abus(?:e|es|ed|ing|ive)\b|\bsex[\s-]+abus(?:e|es|ed|ing|ive)\b",
    "sexual_misconduct": r"\bsexual(?:ly)?[\s-]+misconduct\b",
    "molestation": r"\bmolest(?:ation|ations|ed|ing|er|ers|s)?\b",
    "groping": r"\bgrop(?:e|es|ed|ing|er|ers)\b",
    "indecent_assault": r"\bindecent[\s-]+assault(?:s|ed|ing)?\b",
    "nonconsensual_sex": r"\bnon[-\s]?consensual[\s-]+(?:sex|sexual|intercourse|contact|conduct|activity|activities)\b",
    "sexual_coercion": r"\bsexual(?:ly)?[\s-]+coerc(?:ion|ed|e|es|ing)\b|\bcoerc(?:ed|ing|ion)[\s-]+(?:sex|sexual)\b",
    "sexual_battery": r"\bsexual[\s-]+battery\b",

    # Sexual harassment is tracked separately from the core SV set.
    "sexual_harassment": r"\bsexual(?:ly)?[\s-]+harass(?:ment|ed|ing|es|er|ers)?\b|\bsex[-\s]?based[\s-]+harassment\b",

    # Related terms, reported separately.
    "domestic_violence": r"\bdomestic[\s-]+violence\b|\bdomestic[\s-]+abus(?:e|es|ed|ing)\b",
    "intimate_partner_violence": r"\bintimate[\s-]+partner[\s-]+violence\b|\bintimate[\s-]+partner[\s-]+abus(?:e|es|ed|ing)\b",
    "dating_violence": r"\b(?:teen[\s-]+)?dating[\s-]+violence\b",
    "stalking": r"\bstalk(?:ing|er|ers|ed)\b",
    "harassment_generic": r"\bharass(?:ment|ed|ing|es|er|ers)?\b",
    "sex_trafficking": r"\bsex[\s-]+trafficking\b",
    "sexual_exploitation": r"\bsexual[\s-]+exploitation\b",
    "sexual_consent": (
        r"\bsexual[\s-]+consent\b"
        r"|\bconsent[\s-]+(?:to|for)[\s-]+(?:sex|sexual(?:[\s-]+activity)?)\b"
        r"|\baffirmative[\s-]+consent\b(?=[^.\n]{0,80}\b(?:sex|sexual)\b)"
    ),
}

# Contexts in which a literal keyword hit is not evidence of sexual harm.
EXCLUSIONS = {
    "molestation": [
        r"\bbambi[\s-]+molesters?\b",
        r"\bmolest(?:ing)?[\s-]+(?:the[\s-]+)?alligators?\b",
        r"\bmolesting,\s+annoying\b",
    ],
    "groping": [
        r"\bgrop(?:e|es|ed|ing)[\s-]+(?:around|for)\b",
    ],
    "stalking": [
        r"\bstalking[\s-]+horse\b",
        r"\bstalker(?:\s*-\s*|\s+)?(?:esque|ish|y)\b",
    ],
}

CORE_SV_TERMS = [
    "sexual_violence", "sexual_assault", "rape", "sexual_abuse",
    "sexual_misconduct", "molestation", "groping", "indecent_assault",
    "nonconsensual_sex", "sexual_coercion", "sexual_battery",
]
CORE_PATTERNS = ["title_ix"] + CORE_SV_TERMS
STRICT_LITERAL = ["title_ix", "sexual_violence", "sexual_assault", "rape"]
HARASSMENT_PATTERNS = ["sexual_harassment"]
RELATED_PATTERNS = [
    "domestic_violence", "intimate_partner_violence", "dating_violence",
    "stalking", "harassment_generic", "sex_trafficking",
    "sexual_exploitation", "sexual_consent",
]

GROUP = {k: "core" for k in CORE_PATTERNS}
GROUP["sexual_harassment"] = "harassment"
for _k in RELATED_PATTERNS:
    GROUP[_k] = "related"

RX = {k: re.compile(p, re.I | re.U) for k, p in PATTERNS.items()}
EXRX = {k: [re.compile(p, re.I | re.U) for p in v] for k, v in EXCLUSIONS.items()}

# Narrow-ish athletics/equity vocabulary used only to split Title IX stories.
EQUITY_RX = re.compile(
    r"\bathlet(?:ic|ics|e|es)\b|\bsports?\b|\bteams?\b|\bcoach(?:es|ed|ing)?\b"
    r"|\bncaa\b|\bequity\b|\bequal[\s-]+opportunity\b|\bscholarships?\b"
    r"|\bwomen'?s[\s-]+(?:sports?|teams?|athletics)\b|\btransgender\b"
    r"|\bparticipation\b|\bcompliance\b|\bfunding\b",
    re.I | re.U,
)


def scan_text(text: str, rx_map=None, exrx_map=None):
    """Return (occurrence counts, first surviving context) per pattern."""
    rx_map = rx_map or RX
    exrx_map = exrx_map or EXRX
    counts, contexts = {}, {}
    for key, rx in rx_map.items():
        n = 0
        first = ""
        for m in rx.finditer(text):
            s = max(0, m.start() - 70)
            e = min(len(text), m.end() + 70)
            ctx = re.sub(r"\s+", " ", text[s:e]).strip()
            if any(x.search(ctx) for x in exrx_map.get(key, ())):
                continue
            n += 1
            if not first:
                first = ctx
        counts[key] = n
        contexts[key] = first
    return counts, contexts


def empty_counts():
    return {k: 0 for k in PATTERNS}


def empty_contexts():
    return {k: "" for k in PATTERNS}
