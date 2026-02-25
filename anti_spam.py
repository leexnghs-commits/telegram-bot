# -*- coding: utf-8 -*-
"""
Anti-spam module for Telegram bot
Automatically kicks/bans users matching specific patterns.
"""
import re
from telethon.tl.types import User


# ─── Detection Rules ────────────────────────────────────

def has_southeast_asian_chars(text: str) -> bool:
    """Detect Southeast Asian scripts (Thai, Myanmar, Khmer, Lao, etc.)"""
    if not text:
        return False
    # Thai: 0E00-0E7F, Myanmar: 1000-109F, Khmer: 1780-17FF, Lao: 0E80-0EFF
    pattern = r'[\u0E00-\u0E7F\u1000-\u109F\u1780-\u17FF\u0E80-\u0EFF]'
    return bool(re.search(pattern, text))


def has_russian_chars(text: str) -> bool:
    """Detect Russian Cyrillic characters."""
    if not text:
        return False
    # Cyrillic range: 0400-04FF
    pattern = r'[\u0400-\u04FF]'
    return bool(re.search(pattern, text))


def is_pluto_impersonator(text: str) -> bool:
    """Detect 'pluto research' impersonation in any form."""
    if not text:
        return False
    # Case-insensitive search for pluto/research variants
    text_lower = text.lower()
    pluto_variants = ['pluto', 'plutô', 'рluto', 'ρluto']  # Common spoofing
    research_variants = ['research', 'rеsearch', 'resеarch']  # Cyrillic lookalikes

    has_pluto = any(v in text_lower for v in pluto_variants)
    has_research = any(v in text_lower for v in research_variants)

    return has_pluto and has_research


def should_auto_kick(user: User) -> tuple[bool, str]:
    """
    Check if user should be auto-kicked.
    Returns (should_kick: bool, reason: str)
    """
    # Build full name
    full_name = ""
    if user.first_name:
        full_name += user.first_name
    if user.last_name:
        full_name += " " + user.last_name

    username = user.username or ""

    # Check all text fields
    all_text = f"{full_name} {username}".strip()

    # Rule 1: Southeast Asian scripts
    if has_southeast_asian_chars(all_text):
        return True, "동남아 문자 감지"

    # Rule 2: Russian Cyrillic
    if has_russian_chars(all_text):
        return True, "러시아어 문자 감지"

    # Rule 3: Pluto Research impersonation
    if is_pluto_impersonator(all_text):
        return True, "Pluto Research 사칭 감지"

    return False, ""


# ─── Test cases ─────────────────────────────────────────

if __name__ == "__main__":
    # Test Southeast Asian
    assert has_southeast_asian_chars("สวัสดี") == True  # Thai
    assert has_southeast_asian_chars("မင်္ဂလာပါ") == True  # Myanmar
    assert has_southeast_asian_chars("안녕하세요") == False  # Korean is safe

    # Test Russian
    assert has_russian_chars("Привет") == True
    assert has_russian_chars("Hello") == False

    # Test Pluto impersonation
    assert is_pluto_impersonator("Pluto Research") == True
    assert is_pluto_impersonator("PLUTO research") == True
    assert is_pluto_impersonator("pluto") == False  # Only "pluto" without "research"
    assert is_pluto_impersonator("research") == False
    assert is_pluto_impersonator("My name is John") == False

    print("All tests passed ✓")
