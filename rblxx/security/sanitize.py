"""Input validation & escaping.

Everything the client renders goes through the JSON API and is inserted with
textContent on the front-end, but we still normalise and bound-check here so
that stored data can never contain control characters or absurd payloads.
"""
from __future__ import annotations

import re
import unicodedata

from .. import config

USERNAME_RX = re.compile(config.USERNAME_RE)
_CONTROL_RX = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WS_RX = re.compile(r"[ \t  -​]+")

# Words are matched on a normalised, de-leeted form of the message.
_PROFANITY = {
    "fuck", "shit", "bitch", "asshole", "cunt", "nigger", "faggot", "retard",
    "whore", "slut", "rape", "dick", "cock", "pussy",
}
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s",
                       "7": "t", "@": "a", "$": "s", "!": "i"})


class ValidationError(ValueError):
    """Raised with a user-presentable message."""


def clean_text(value, *, max_len: int = 500, allow_newlines: bool = False) -> str:
    if value is None:
        return ""
    text = str(value)
    text = unicodedata.normalize("NFC", text)
    text = _CONTROL_RX.sub("", text)
    if allow_newlines:
        text = re.sub(r"\r\n?", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        lines = [_WS_RX.sub(" ", ln).strip() for ln in text.split("\n")]
        text = "\n".join(lines).strip()
    else:
        text = _WS_RX.sub(" ", text.replace("\n", " ").replace("\r", " ")).strip()
    return text[:max_len]


def validate_username(value: str) -> str:
    name = clean_text(value, max_len=20)
    if not USERNAME_RX.match(name):
        raise ValidationError(
            "Usernames are 3-20 characters: letters, numbers and underscores.")
    if name.lower() in {"admin", "administrator", "moderator", "rblxx",
                        "system", "root", "null", "undefined", "guest"}:
        raise ValidationError("That username is reserved.")
    return name


def validate_password(value: str) -> str:
    pw = str(value or "")
    if len(pw) < config.MIN_PASSWORD_LEN:
        raise ValidationError(
            f"Password must be at least {config.MIN_PASSWORD_LEN} characters.")
    if len(pw) > config.MAX_PASSWORD_LEN:
        raise ValidationError("Password is too long.")
    if pw.lower() in {"password", "123456", "qwerty", "letmein", "roblox"}:
        raise ValidationError("Please choose a less common password.")
    return pw


def validate_hex_color(value, default: str = "#a3a2a5") -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", text):
        return text.lower()
    if re.fullmatch(r"[0-9a-fA-F]{6}", text):
        return "#" + text.lower()
    return default


def filter_chat(text: str) -> str:
    """Classic-style hash filtering of blocked words."""
    def repl(match):
        return "#" * len(match.group(0))

    out = text
    lowered = text.lower().translate(_LEET)
    for word in _PROFANITY:
        for m in re.finditer(re.escape(word), lowered):
            start, end = m.span()
            out = out[:start] + "#" * (end - start) + out[end:]
    return out


def looks_like_spam(text: str) -> bool:
    if len(text) < 6:
        return False
    letters = [c for c in text if c.isalpha()]
    if letters and sum(1 for c in letters if c.isupper()) / len(letters) > 0.85 \
            and len(letters) > 14:
        return True
    if re.search(r"(.)\1{9,}", text):
        return True
    return False
