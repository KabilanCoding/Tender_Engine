"""Words that tell a tender from other documents, and an eligibility section from boilerplate, in the Indian languages
tenders are written in (besides English). The pipeline's English wording rules ('average', 'similar work', 'team')
cannot read these, so `is_latin` lets those rules step aside and the engine fall back to 'check manually' instead of
guessing."""
import re
import unicodedata
from typing import List

# plain substrings (no \b: these scripts do not separate words the way Latin does)
TENDER_TERMS: List[str] = [
    "निविदा", "ई-निविदा", "बोली दस्तावेज", "बोलीदाता", "निविदाकार", "पात्रता मानदंड", "अग्रिम धन", "बयाना राशि",   # Hindi, Marathi, Nepali
    "ஒப்பந்தப்புள்ளி", "டெண்டர்", "ஒப்பந்ததாரர்", "தகுதி நிபந்தனை", "வைப்புத்தொகை",                              # Tamil
    "టెండర్", "బిడ్డర్", "అర్హత ప్రమాణాలు",                                                                    # Telugu
    "ಟೆಂಡರ್", "ಅರ್ಹತಾ ಮಾನದಂಡ",                                                                                  # Kannada
    "ടെൻഡർ", "ബിഡ്ഡർ", "യോഗ്യതാ മാനദണ്ഡം",                                                                      # Malayalam
    "দরপত্র", "টেন্ডার", "টেণ্ডাৰ",                                                                             # Bengali, Assamese
    "ટેન્ડર", "બિડર", "ਟੈਂਡਰ", "ਬੋਲੀਕਾਰ", "ଟେଣ୍ଡର", "ٹینڈر",                                                      # Gujarati, Punjabi, Odia, Urdu
]

# words that mark eligibility / qualification text (prefilter score)
ELIGIBILITY_TERMS: List[str] = [
    "पात्रता", "योग्यता", "अनुभव", "वार्षिक आय", "कारोबार",                       # Hindi, Marathi, Nepali, Sanskrit
    "வருவாய்", "தகுதி", "அனுபவம்", "விற்றுமுதல்",                               # Tamil
    "అర్హత", "అనుభవం", "టర్నోవర్", "ಅರ್ಹತೆ", "ಅನುಭವ", "ವಹಿವಾಟು",                 # Telugu, Kannada
    "യോഗ്യത", "അനുഭവം", "വിറ്റുവരവ്",                                           # Malayalam
    "যোগ্যতা", "অভিজ্ঞতা", "টার্নওভার", "લાયકાત", "અનુભવ", "ટર્નઓવર",              # Bengali/Assamese, Gujarati
    "ਯੋਗਤਾ", "ਤਜਰਬਾ", "ଯୋଗ୍ୟତା", "ଅଭିଜ୍ଞତା", "اہلیت", "تجربہ",                     # Punjabi, Odia, Urdu
]

# a line that is an eligibility heading in one of those languages (short, no sentence punctuation)
HEADING_WORDS: List[str] = ["पात्रता", "योग्यता", "தகுதி", "అర్హత", "ಅರ್ಹತೆ", "യോഗ്യത", "যোগ্যতা", "લાયકાત", "ਯੋਗਤਾ", "ଯୋଗ୍ୟତା", "اہلیت"]

_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)


def latin_ratio(text: str) -> float:
    """Share of the letters in `text` that are Latin-script (1.0 for English, 0.0 for Hindi, Tamil, Urdu...)."""
    letters = [c for c in str(text or "") if _LETTER.match(c)]
    if not letters:
        return 1.0
    return sum(1 for c in letters if "LATIN" in unicodedata.name(c, "")) / len(letters)


def is_latin(text: str) -> bool:
    """True when the English wording rules of the pipeline can read `text`."""
    return latin_ratio(text) >= 0.6


def count_terms(text: str, terms: List[str]) -> int:
    low = str(text or "").lower()
    return sum(1 for t in terms if t.lower() in low)
