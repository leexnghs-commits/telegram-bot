# -*- coding: utf-8 -*-
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# Telegram Bot
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ALLOWED_USER_IDS = [
    int(uid.strip())
    for uid in os.getenv("ALLOWED_USER_IDS", "").split(",")
    if uid.strip()
]

# Claude CLI
CLAUDE_EXE = Path(os.getenv("CLAUDE_EXE", r"C:\Users\darks\.local\bin\claude.exe"))
CLAUDE_TIMEOUT = int(os.getenv("CLAUDE_TIMEOUT", "600"))  # seconds
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "claude-sonnet-4-6")  # claude-sonnet-4-6, claude-opus-4-6, claude-haiku-4-5-20251001
PROJECT_ROOT = Path(r"C:\Users\darks\project98")

# Codex CLI
CODEX_EXE = Path(os.getenv("CODEX_EXE", r"C:\Users\darks\AppData\Roaming\npm\codex.cmd"))
CODEX_TIMEOUT = int(os.getenv("CODEX_TIMEOUT", "600"))

# Context prefixes → working directories
CONTEXT_DIRS = {
    "@nepcon": PROJECT_ROOT / "projects" / "nepcon_auto",
    "@breadth": PROJECT_ROOT / "projects" / "market_breadth",
}

# Telegram API (for Telethon bot mode)
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
