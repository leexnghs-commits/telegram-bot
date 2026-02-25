# -*- coding: utf-8 -*-
"""
Telegram ↔ Claude Code Bot

Receives messages from Telegram, runs `claude -p` CLI, returns results.
Uses Telethon in bot mode.
"""
import sys
import io
import os
import asyncio
import tempfile
from pathlib import Path

os.environ["PYTHONUNBUFFERED"] = "1"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
sys.path.insert(0, str(Path(__file__).parent))

from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeFilename

from config import (
    BOT_TOKEN, ALLOWED_USER_IDS,
    TELEGRAM_API_ID, TELEGRAM_API_HASH,
    PROJECT_ROOT, CONTEXT_DIRS, DEFAULT_MODEL,
)
from claude_executor import run_claude, run_codex
from anti_spam import should_auto_kick

# ─── State ──────────────────────────────────────────────
# Active tasks: {user_id: asyncio.Task}
active_tasks: dict[int, asyncio.Task] = {}

TELEGRAM_MAX_MSG = 4096
LARGE_TEXT_LIMIT = 40000

MODEL_PREFIXES = {
    "!opus": "opus",
    "!sonnet": "sonnet",
    "!haiku": "haiku",
}

CODEX_PREFIX = "!codex"

HELP_TEXT = """**Claude Code Telegram Bot**

일반 메시지 → project98/ 루트에서 Claude(Sonnet) 실행
`@nepcon 메시지` → nepcon_auto/ 에서 실행
`@breadth 메시지` → market_breadth/ 에서 실행

**모델 전환 (Claude)**
`!opus 메시지` → Opus
`!sonnet 메시지` → Sonnet (기본값)
`!haiku 메시지` → Haiku

**Codex (GPT 5.3)**
`!codex 메시지` → OpenAI Codex로 실행

조합 가능: `!codex @nepcon 데이터 검증해`

**명령어**
/cancel — 실행 중인 작업 취소
/myid — 내 Telegram ID 확인
/help — 이 도움말
"""


def is_allowed(user_id: int) -> bool:
    if not ALLOWED_USER_IDS:
        return True  # no whitelist = allow all (for initial /myid setup)
    return user_id in ALLOWED_USER_IDS


def parse_message(text: str) -> tuple[str, Path, str | None, bool]:
    """Parse model/codex prefix and @context prefix.
    Returns (prompt, cwd, model, use_codex)."""
    model = None
    use_codex = False

    # Check !codex prefix first
    if text.startswith(CODEX_PREFIX):
        text = text[len(CODEX_PREFIX):].strip()
        use_codex = True
    else:
        # Check Claude model prefix
        for prefix, mod in MODEL_PREFIXES.items():
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                model = mod
                break

    # Check context prefix
    for prefix, cwd in CONTEXT_DIRS.items():
        if text.startswith(prefix):
            prompt = text[len(prefix):].strip()
            return prompt, cwd, model, use_codex

    return text, PROJECT_ROOT, model, use_codex


async def send_long_text(event, text: str):
    """Send text, splitting if >4096 chars or sending as file if >40k."""
    if len(text) <= TELEGRAM_MAX_MSG:
        await event.respond(text)
        return

    if len(text) > LARGE_TEXT_LIMIT:
        # Send as .txt file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(text)
            tmp_path = Path(f.name)
        try:
            await event.respond(
                "결과가 너무 길어 파일로 전송합니다.",
                file=str(tmp_path),
            )
        finally:
            tmp_path.unlink(missing_ok=True)
        return

    # Split into chunks
    chunks = []
    while text:
        if len(text) <= TELEGRAM_MAX_MSG:
            chunks.append(text)
            break
        # Find last newline within limit
        cut = text.rfind("\n", 0, TELEGRAM_MAX_MSG)
        if cut == -1:
            cut = TELEGRAM_MAX_MSG
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")

    for i, chunk in enumerate(chunks):
        if chunk.strip():
            await event.respond(chunk)
            if i < len(chunks) - 1:
                await asyncio.sleep(0.3)


async def send_files(event, files: list[Path]):
    """Send detected output files."""
    for f in files:
        ext = f.suffix.lower()
        if ext in ('.png', '.jpg', '.jpeg', '.gif'):
            # Send as inline photo
            await event.respond(file=str(f))
        else:
            # Send as document with filename
            await event.respond(
                file=str(f),
                attributes=[DocumentAttributeFilename(f.name)],
            )


async def handle_request(event, prompt: str, cwd: Path, model: str | None = None, use_codex: bool = False):
    """Run Claude or Codex and send results back."""
    user_id = event.sender_id
    engine = "codex" if use_codex else (model or DEFAULT_MODEL)

    # Send "processing" message
    processing_msg = await event.respond(f"처리 중... ({engine})")

    try:
        if use_codex:
            result = await run_codex(prompt, cwd=cwd)
        else:
            result = await run_claude(prompt, cwd=cwd, model=model)

        # Delete "processing" message
        try:
            await processing_msg.delete()
        except Exception:
            pass

        # Build response
        if result.timed_out:
            await event.respond("시간 초과 (10분). /cancel 후 재시도하세요.")
            return

        output = result.stdout.strip()
        if result.returncode != 0 and result.stderr:
            output += f"\n\n[stderr]\n{result.stderr.strip()}"

        if not output:
            output = "(빈 응답)"

        await send_long_text(event, output)

        # Send any generated files
        if result.files:
            await send_files(event, result.files)

    except asyncio.CancelledError:
        try:
            await processing_msg.delete()
        except Exception:
            pass
        await event.respond("작업이 취소되었습니다.")
    finally:
        active_tasks.pop(user_id, None)


def create_bot():
    bot = TelegramClient(
        str(Path(__file__).parent / "bot_session"),
        TELEGRAM_API_ID,
        TELEGRAM_API_HASH,
    )

    @bot.on(events.NewMessage(pattern="/myid"))
    async def cmd_myid(event):
        await event.respond(f"Your Telegram ID: `{event.sender_id}`")

    @bot.on(events.NewMessage(pattern="/help"))
    async def cmd_help(event):
        if not is_allowed(event.sender_id):
            return
        await event.respond(HELP_TEXT)

    @bot.on(events.NewMessage(pattern="/cancel"))
    async def cmd_cancel(event):
        if not is_allowed(event.sender_id):
            return
        task = active_tasks.get(event.sender_id)
        if task and not task.done():
            task.cancel()
            await event.respond("취소 요청 전송됨.")
        else:
            await event.respond("실행 중인 작업이 없습니다.")

    @bot.on(events.NewMessage)
    async def on_message(event):
        # Skip commands already handled
        if event.text and event.text.startswith("/"):
            return
        # Skip non-private messages
        if not event.is_private:
            return

        # Auto-kick spam users (before whitelist check)
        try:
            sender = await event.get_sender()
            should_kick, reason = should_auto_kick(sender)
            if should_kick:
                print(f"[AUTO-KICK] User {event.sender_id} ({sender.first_name}) - {reason}")
                await event.respond(f"스팸 감지: {reason}. 차단되었습니다.")
                # Block user (no need to kick in private chat, just ignore future messages)
                return
        except Exception as e:
            print(f"[WARNING] Auto-kick check failed: {e}")

        if not is_allowed(event.sender_id):
            return
        if not event.text or not event.text.strip():
            return

        user_id = event.sender_id

        # Check if already running
        existing = active_tasks.get(user_id)
        if existing and not existing.done():
            await event.respond("이전 작업이 아직 실행 중입니다. /cancel 로 취소하거나 완료를 기다려주세요.")
            return

        prompt, cwd, model, use_codex = parse_message(event.text.strip())
        if not prompt:
            return

        # Create async task
        task = asyncio.create_task(handle_request(event, prompt, cwd, model, use_codex))
        active_tasks[user_id] = task

    return bot


async def main():
    if not BOT_TOKEN:
        print("[ERROR] BOT_TOKEN이 설정되지 않았습니다. .env 파일을 확인하세요.")
        sys.exit(1)

    print("=" * 50)
    print("Claude Code Telegram Bot")
    print(f"Allowed users: {ALLOWED_USER_IDS or 'ALL (no whitelist)'}")
    print("=" * 50)

    bot = create_bot()
    await bot.start(bot_token=BOT_TOKEN)
    print("[OK] Bot started. Listening for messages...")
    await bot.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
