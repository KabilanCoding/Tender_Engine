"""Offline login captcha: a distorted SVG drawn on the server, the answer checked on the server.

No external service. The challenge id is a signed, 5-minute token that holds only an HMAC of the answer, so the answer
never reaches the browser; each challenge can be used once (kept in memory for its lifetime).
"""
import hashlib
import hmac
import random
import secrets
import time
from typing import Dict, Tuple

from jose import JWTError, jwt

from app.core.config import settings

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"          # no 0/O, 1/I: easy to read, still 32^5 combinations
_LENGTH = 5
_TTL_S = 300
_used: Dict[str, float] = {}


def _digest(answer: str, nonce: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), f"{nonce}:{answer.upper()}".encode(), hashlib.sha256).hexdigest()


def _svg(text: str) -> str:
    rnd = random.SystemRandom()
    w, h = 180, 56
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
             '<rect width="100%" height="100%" rx="10" fill="#eef4f9"/>']
    for _ in range(6):                                   # background noise curves
        parts.append(f'<path d="M{rnd.randint(0, 40)} {rnd.randint(5, h - 5)} Q {rnd.randint(40, 140)} {rnd.randint(0, h)} '
                     f'{rnd.randint(140, w)} {rnd.randint(5, h - 5)}" stroke="#{rnd.choice(["9ccbe6", "b7d9a8", "c3cfdc"])}" stroke-width="{rnd.uniform(1, 2.2):.1f}" fill="none"/>')
    for _ in range(40):                                  # speckles
        parts.append(f'<circle cx="{rnd.randint(0, w)}" cy="{rnd.randint(0, h)}" r="{rnd.uniform(0.6, 1.6):.1f}" fill="#9fb0c2"/>')
    x = 16
    for ch in text:
        y, rot, size = rnd.randint(34, 44), rnd.randint(-28, 28), rnd.randint(24, 30)
        color = rnd.choice(["#0f4a6e", "#1C78AB", "#2f5d24", "#3c5a86"])
        parts.append(f'<text x="{x}" y="{y}" font-family="Verdana,Arial,sans-serif" font-weight="700" font-size="{size}" fill="{color}" '
                     f'transform="rotate({rot} {x + 9} {y - 10}) skewX({rnd.randint(-12, 12)})">{ch}</text>')
        x += rnd.randint(28, 33)
    parts.append(f'<path d="M8 {rnd.randint(20, 38)} C 60 {rnd.randint(0, h)}, 120 {rnd.randint(0, h)}, {w - 8} {rnd.randint(20, 38)}" '
                 'stroke="#1C78AB" stroke-opacity="0.55" stroke-width="2" fill="none"/>')
    parts.append("</svg>")
    return "".join(parts)


def new_challenge() -> Tuple[str, str]:
    """(captcha_id, svg)."""
    answer = "".join(secrets.choice(_ALPHABET) for _ in range(_LENGTH))
    nonce = secrets.token_hex(8)
    cid = jwt.encode({"n": nonce, "d": _digest(answer, nonce), "exp": int(time.time()) + _TTL_S, "typ": "captcha"},
                     settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return cid, _svg(answer)


def verify(captcha_id: str, answer: str) -> bool:
    """True once per challenge when the answer matches (case-insensitive, spaces ignored)."""
    now = time.time()
    for k in [k for k, t in _used.items() if t < now]:
        _used.pop(k, None)
    try:
        data = jwt.decode(captcha_id or "", settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return False
    if data.get("typ") != "captcha" or data.get("n") in _used:
        return False
    _used[data["n"]] = float(data.get("exp", now + _TTL_S))     # spent, right or wrong: a new image is needed for the next try
    return hmac.compare_digest(_digest("".join((answer or "").split()), data["n"]), data.get("d", ""))
