import re
from datetime import datetime, date
from typing import Any, Optional, List

class Normalizer:
    """
    S8 Normaliser: Sanitizes string, numeric, date, certification, and boolean values
    for criteria comparison.
    """

    WORD_TO_NUM = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10
    }

    @classmethod
    def coerce_none(cls, v: Any) -> Optional[Any]:
        if v is None:
            return None
        if isinstance(v, str):
            cleaned = v.strip().lower()
            if cleaned in ("", "none", "null", "n/a", "not applicable", "nil", "na"):
                return None
        return v

    @classmethod
    def normalize_criteria(cls, criteria: List[Any]) -> List[Any]:
        for crit in criteria:
            if hasattr(crit, "value") and crit.value is not None:
                if isinstance(crit.value, str):
                    crit.value = crit.value.strip()
        return criteria

    @classmethod
    def normalize_string(cls, v: Any) -> Optional[str]:
        val = cls.coerce_none(v)
        if val is None:
            return None
        val_str = str(val).strip().lower()
        val_str = re.sub(r"\s+", " ", val_str)
        val_str = val_str.strip(".,;:\"'")
        return val_str if val_str else None

    _UNITS = {"crore": 1e7, "crores": 1e7, "cr": 1e7, "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5,
              "l": 1e5, "million": 1e6, "mn": 1e6, "billion": 1e9, "bn": 1e9, "thousand": 1e3, "k": 1e3}
    _WORD_UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                   "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
                   "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
    _WORD_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
                  "eighty": 80, "ninety": 90}
    _NUM_TOKEN = re.compile(r"(?<![\d,])(?<!\d\.)(\d[\d,]*(?:\.\d+)?)\s*(crores?|cr|lakhs?|lacs?|lac|l|million|mn|billion|bn|thousand|k)?\.?(?![a-z])")
    _FISCAL = re.compile(r"\b(?:f\.?y\.?\s*)?(?:19|20)\d{2}\s*[-–/]\s*\d{2,4}\b|\bf\.?y\.?\s*(?:19|20)\d{2}\b")

    @classmethod
    def _words_to_number(cls, text: str) -> Optional[float]:
        """'one hundred and fifty' -> 150, 'eighteen' -> 18; None when there is no number word."""
        total, current, seen = 0, 0, False
        for w in re.findall(r"[a-z]+", text):
            if w in cls._WORD_UNITS:
                current += cls._WORD_UNITS[w]; seen = True
            elif w in cls._WORD_TENS:
                current += cls._WORD_TENS[w]; seen = True
            elif w == "hundred" and seen:
                current = (current or 1) * 100
            elif w == "and" and seen:
                continue
            elif seen:
                break                  # first non-number word ends the number ("five crore", "ten years")
        total += current
        return float(total) if seen else None

    @classmethod
    def parse_numeric(cls, v: Any) -> Optional[float]:
        """Amount / count in a tender value: '1 Crore', 'Rs. 1 (one) Crores', 'INR 4,50,00,000/-', '50 Lakhs',
        'Rs. 1 Crore 50 Lakhs', 'ten crore', '5 years'.

        Returns None (cannot decide) for percentages ('30% of the estimated cost'), ranges and non-scalars,
        so a rule never compares the company with a meaningless threshold.
        """
        val = cls.coerce_none(v)
        if val is None or isinstance(val, (bool, dict, list, tuple, set)):
            return None
        if isinstance(val, (int, float)):
            return float(val)

        s = str(val).strip().lower()
        if re.search(r"%|\bper\s*cent|\bpercent", s):
            return None
        s = re.sub(r"\([^)]*\)", " ", s)                       # '(Rupees Ten Lakhs only)', '(one)', '(1.5 crore)'
        s = cls._FISCAL.sub(" ", s)                              # 'FY 2022-23' is a year, not an amount
        if re.search(r"\d\s*(?:–|—|\bto\b)\s*\d", s):
            return None                                          # '5 to 10 crore', '2–3 years': a range
        s = s.replace("₹", " ")

        tokens = []
        for m in cls._NUM_TOKEN.finditer(s):
            digits = m.group(1).replace(",", "").rstrip(".")
            try:
                num = float(digits)
            except ValueError:
                continue
            unit = (m.group(2) or "").lower()
            mult = cls._UNITS.get(unit, 1.0)
            if mult > 1 and num >= 1e5 and "," in m.group(1):
                mult = 1.0                                       # '10,00,000 lakhs' style restatement: digits win
            tokens.append((num, mult, m.start(), m.end()))

        if tokens:
            with_unit = [t for t in tokens if t[1] > 1]
            if not with_unit:
                return tokens[0][0]
            num, mult, _start, end = with_unit[0]
            value = num * mult
            for n2, m2, st2, en2 in with_unit[1:]:               # 'Rs. 1 Crore 50 Lakhs'
                if st2 - end <= 6 and m2 < mult:
                    value += n2 * m2
                    end, mult = en2, m2
                else:
                    break
            return value

        number = cls._words_to_number(s)                         # 'ten crore', 'eighteen lakhs'
        if number is None:
            return None
        unit = re.search(r"\b(crores?|cr|lakhs?|lacs?|lac|million|billion|thousand)\b", s)
        return number * (cls._UNITS[unit.group(1)] if unit else 1.0)

    _DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d.%m.%Y", "%d.%m.%y", "%d-%b-%Y", "%d-%B-%Y",
                     "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y", "%d %b, %Y", "%d %B, %Y")
    _MONTH_FORMATS = ("%B %Y", "%b %Y", "%m/%Y", "%m-%Y", "%b-%Y", "%B-%Y")

    @classmethod
    def parse_date(cls, v: Any) -> Optional[date]:
        """Dates as stored by people: '2027-03-31', '30.09.2025', '31-Mar-2027', 'March 2027' (month end), '2027'."""
        val = cls.coerce_none(v)
        if val is None:
            return None
        if isinstance(val, datetime):          # datetime is a subclass of date: check it first
            return val.date()
        if isinstance(val, date):
            return val

        val_str = re.sub(r"\s+", " ", str(val).strip()).replace("Sept", "Sep")
        for fmt in cls._DATE_FORMATS:
            try:
                return datetime.strptime(val_str, fmt).date()
            except ValueError:
                continue
        import calendar
        for fmt in cls._MONTH_FORMATS:
            try:
                d = datetime.strptime(val_str, fmt)
                return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])
            except ValueError:
                continue
        if re.fullmatch(r"(?:19|20)\d{2}", val_str):
            return date(int(val_str), 12, 31)
        return None

    @classmethod
    def normalize_cert(cls, v: Any) -> Optional[str]:
        val = cls.coerce_none(v)
        if val is None:
            return None
        val_str = str(val).strip().lower()
        # Remove year suffix e.g. "iso 9001:2015" -> "iso9001" or "iso 9001 2018" -> "iso9001"
        val_str = re.sub(r"[:\s]?(?:19|20)\d{2}", "", val_str)
        val_str = re.sub(r"\s+", "", val_str)
        return val_str

    @classmethod
    def parse_boolean(cls, v: Any) -> Optional[bool]:
        val = cls.coerce_none(v)
        if val is None:
            return None
        if isinstance(val, bool):
            return val
        val_str = str(val).strip().lower()
        if val_str in ("true", "1", "yes", "y"):
            return True
        if val_str in ("false", "0", "no", "n"):
            return False
        return None
