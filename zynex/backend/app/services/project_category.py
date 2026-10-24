"""Portfolio category of a project (GPS, IoT, Ticketing ...): chosen by the user; guessed from the project text when left empty."""
import re
from typing import Iterable, Optional

CATEGORIES = [
    "GPS & Tracking", "IoT & Telemetry", "Ticketing & Fare Collection", "Video & Surveillance",
    "GIS & Mapping", "Hardware & Devices", "Software & Platforms",
]
# first match wins, so the most specific kinds come first
_RULES = [
    ("Ticketing & Fare Collection", r"ticket|fare collection|\btoll\b|fastag|\bafc\b"),
    ("GPS & Tracking", r"\bgps\b|tracking|\bavl\b|\bvts\b|vehicle location|fleet"),
    ("Video & Surveillance", r"cctv|surveillance|\banpr\b|camera|video"),
    ("IoT & Telemetry", r"\biot\b|scada|telemetry|smart meter|\bmqtt\b|sensor|modbus|dlms"),
    ("GIS & Mapping", r"\bgis\b|postgis|mapping|geo-?spatial|survey"),
    ("Hardware & Devices", r"hardware|device|biometric|kiosk|e-?pos|installation of"),
]


def guess_category(name: str = "", description: Optional[str] = None, technologies: Optional[Iterable[str]] = None) -> str:
    """The project's name decides first (it says what was delivered); the description and technologies only when the name is silent."""
    for text in (name, description, " ".join(technologies or [])):
        t = (text or "").lower()
        hit = next((cat for cat, rx in _RULES if re.search(rx, t)), None)
        if hit:
            return hit
    return "Software & Platforms"
