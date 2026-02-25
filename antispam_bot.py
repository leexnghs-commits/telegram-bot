# -*- coding: utf-8 -*-
"""
텔레그램 그룹 안티스팸 봇

1) 러시아어(키릴)/동남아어 닉네임 → 입장 즉시 밴
2) 하드밴 키워드 (카지노/토토 등) → 즉시 삭제+밴
3) 의심 패턴 (외부 링크) → GPT-4o-mini 판별 → 스팸이면 삭제+밴
"""
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)

from antispam.config import ANTISPAM_BOT_TOKEN, ADMIN_IDS, OPENAI_API_KEY
from antispam.filters import (
    is_suspicious_name,
    check_message,
    check_rate_limit,
    increment_warning,
    get_warning_count,
    reset_warning,
    load_blacklist,
    save_blacklist,
)
from antispam.actions import ban_and_announce, delete_and_ban, delete_and_warn, delete_and_notify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("antispam")


# ─── 신규 멤버 닉네임 검사 ──────────────────────────────

async def on_new_member(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.new_chat_members:
        return

    chat_id = update.message.chat_id
    for user in update.message.new_chat_members:
        if user.id == ctx.bot.id:
            continue
        suspicious, reason = is_suspicious_name(user.first_name, user.last_name)
        if suspicious:
            await ban_and_announce(ctx.bot, chat_id, user, reason)


# ─── 메시지 스팸 검사 ──────────────────────────────

def _extract_text(message) -> str:
    """메시지에서 텍스트 추출 (본문 or 캡션)."""
    return message.text or message.caption or ""


async def on_group_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.edited_message
    if not msg:
        return

    text = _extract_text(msg)
    if not text:
        return

    user = msg.from_user
    if not user:
        return
    if user.id in ADMIN_IDS or user.is_bot:
        return

    # 닉네임 기반 즉시 밴 (이미 입장한 유저 대응)
    suspicious, reason = is_suspicious_name(user.first_name, user.last_name)
    if suspicious and reason == "banned_nickname":
        try:
            await ctx.bot.delete_message(msg.chat_id, msg.message_id)
        except Exception:
            pass
        await ban_and_announce(ctx.bot, msg.chat_id, user, reason)
        return

    # Rate Limiting 체크
    is_rate_limited, rate_reason = check_rate_limit(user.id)
    if is_rate_limited:
        # Rate limit 초과 → 삭제만 (밴 없음)
        await delete_and_notify(
            ctx.bot,
            msg.chat_id,
            msg.message_id,
            user,
            "rate_limit",
            [rate_reason],
            text,
        )
        return

    # 스팸 판별
    is_spam, method, details = await check_message(text, user.id)
    if is_spam:
        if method == "hard_ban":
            # 하드밴 키워드 → 삭제만 (밴 없음)
            await delete_and_notify(
                ctx.bot,
                msg.chat_id,
                msg.message_id,
                user,
                method,
                details,
                text,
            )
        elif method == "suspicious_pattern":
            # 의심 패턴 → 삭제만 (밴 없음)
            await delete_and_notify(
                ctx.bot,
                msg.chat_id,
                msg.message_id,
                user,
                method,
                details,
                text,
            )
        elif method == "dual_validation":
            # GPT+Claude 이중검증 → 삭제만 (밴 없음)
            await delete_and_notify(
                ctx.bot,
                msg.chat_id,
                msg.message_id,
                user,
                method,
                details,
                text,
            )


# ─── 관리자 명령어 ──────────────────────────────

def admin_only(func):
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in ADMIN_IDS:
            return
        return await func(update, ctx)
    return wrapper


@admin_only
async def cmd_spam_add(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("사용법: /spam_add <키워드>")
        return
    keyword = " ".join(ctx.args)
    bl = load_blacklist()
    kw_list = bl.setdefault("hard_ban_keywords", [])
    if keyword not in kw_list:
        kw_list.append(keyword)
        save_blacklist(bl)
        await update.message.reply_text(f"추가: {keyword}")
    else:
        await update.message.reply_text(f"이미 존재: {keyword}")


@admin_only
async def cmd_spam_remove(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("사용법: /spam_remove <키워드>")
        return
    keyword = " ".join(ctx.args)
    bl = load_blacklist()
    kw_list = bl.get("hard_ban_keywords", [])
    if keyword in kw_list:
        kw_list.remove(keyword)
        save_blacklist(bl)
        await update.message.reply_text(f"제거: {keyword}")
    else:
        await update.message.reply_text(f"없음: {keyword}")


@admin_only
async def cmd_spam_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    bl = load_blacklist()
    keywords = bl.get("hard_ban_keywords", [])
    patterns = bl.get("suspicious_patterns", [])
    whitelist = bl.get("whitelist_domains", [])
    text = (
        f"하드밴 키워드 ({len(keywords)}개):\n"
        + (", ".join(keywords) or "(없음)")
        + f"\n\n의심 패턴 ({len(patterns)}개):\n"
        + ("\n".join(patterns) or "(없음)")
        + f"\n\n화이트리스트 도메인 ({len(whitelist)}개):\n"
        + (", ".join(whitelist[:10]) + ("..." if len(whitelist) > 10 else "") or "(없음)")
    )
    await update.message.reply_text(text)


@admin_only
async def cmd_unban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """사용법: /unban <user_id>"""
    if not ctx.args:
        await update.message.reply_text("사용법: /unban <user_id>\n예: /unban 960425946")
        return

    try:
        user_id = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("올바른 user_id를 입력하세요 (숫자)")
        return

    chat_id = update.message.chat_id

    try:
        await ctx.bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
        # 경고도 함께 초기화
        reset_warning(user_id)
        await update.message.reply_text(
            f"✅ User {user_id} 밴 해제 + 경고 초기화 완료\n(재입장은 유저가 직접 해야 함)"
        )
        logger.info(f"UNBANNED: user_id={user_id} by admin={update.effective_user.id}")
    except Exception as e:
        await update.message.reply_text(f"❌ 밴 해제 실패: {e}")
        logger.error(f"Unban failed: user_id={user_id}, error={e}")


@admin_only
async def cmd_reset_warning(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """사용법: /reset_warning <user_id>"""
    if not ctx.args:
        await update.message.reply_text("사용법: /reset_warning <user_id>\n예: /reset_warning 960425946")
        return

    try:
        user_id = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("올바른 user_id를 입력하세요 (숫자)")
        return

    reset_warning(user_id)
    await update.message.reply_text(f"✅ User {user_id}의 경고가 초기화되었습니다.")
    logger.info(f"WARNING RESET: user_id={user_id} by admin={update.effective_user.id}")


@admin_only
async def cmd_check_warning(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """사용법: /check_warning <user_id>"""
    if not ctx.args:
        await update.message.reply_text("사용법: /check_warning <user_id>\n예: /check_warning 960425946")
        return

    try:
        user_id = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("올바른 user_id를 입력하세요 (숫자)")
        return

    count = get_warning_count(user_id)
    await update.message.reply_text(f"ℹ️ User {user_id}의 경고 횟수: {count}/2")


async def cmd_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /신고 명령어 - 관리자에게 알림 전송.
    관리자가 수동으로 확인하여 처리.
    """
    msg = update.message
    if not msg:
        return

    # 답장 메시지가 있는지 확인
    if not msg.reply_to_message:
        await msg.reply_text("❌ 신고하려는 메시지에 답장으로 /신고 명령어를 사용하세요.")
        return

    reported_msg = msg.reply_to_message
    reported_user = reported_msg.from_user
    if not reported_user:
        await msg.reply_text("❌ 신고 대상 유저 정보를 찾을 수 없습니다.")
        return

    # 관리자나 봇은 신고 불가
    if reported_user.id in ADMIN_IDS or reported_user.is_bot:
        await msg.reply_text("❌ 관리자나 봇은 신고할 수 없습니다.")
        return

    # 메시지 텍스트 추출
    text = _extract_text(reported_msg)
    if not text:
        text = "(텍스트 없음 - 사진/영상/스티커 등)"

    # 신고자 정보
    reporter_name = f"{msg.from_user.first_name or ''} {msg.from_user.last_name or ''}".strip()
    reported_name = f"{reported_user.first_name or ''} {reported_user.last_name or ''}".strip()

    # 관리자에게 알림
    admin_msg = (
        f"🚨 [유저 신고 접수]\n\n"
        f"신고자: {reporter_name} (id={msg.from_user.id})\n"
        f"신고 대상: {reported_name} (id={reported_user.id})\n"
        f"메시지 ID: {reported_msg.message_id}\n"
        f"채팅방 ID: {msg.chat_id}\n\n"
        f"원문:\n{text[:500]}\n\n"
        f"처리 명령어:\n"
        f"/unban {reported_user.id} - 밴 해제\n"
        f"또는 텔레그램 채팅방에서 직접 밴/음소거 처리"
    )

    for admin_id in ADMIN_IDS:
        try:
            await ctx.bot.send_message(admin_id, admin_msg)
        except Exception as e:
            logger.error(f"Failed to send report to admin {admin_id}: {e}")

    # 신고자에게 확인 메시지
    await msg.reply_text("✅ 관리자에게 신고가 접수되었습니다. 검토 후 조치하겠습니다.")

    logger.info(
        f"USER REPORT: {reported_name} (id={reported_user.id}) "
        f"by {reporter_name} (id={msg.from_user.id})"
    )


# ─── 메인 ──────────────────────────────

def main():
    if not ANTISPAM_BOT_TOKEN:
        print("[ERROR] ANTISPAM_BOT_TOKEN이 .env에 없습니다.")
        print("@BotFather → /newbot → 토큰을 .env에 추가:")
        print("  ANTISPAM_BOT_TOKEN=your_token_here")
        sys.exit(1)

    if not OPENAI_API_KEY:
        print("[WARN] OPENAI_API_KEY 없음 — GPT 판별 비활성, 하드밴만 작동")

    app = ApplicationBuilder().token(ANTISPAM_BOT_TOKEN).build()

    _group = filters.ChatType.GROUP | filters.ChatType.SUPERGROUP

    app.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_member))
    # 텍스트 메시지
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & _group,
        on_group_message))
    # 사진/동영상/문서 + 캡션
    app.add_handler(MessageHandler(
        filters.CAPTION & _group,
        on_group_message))
    # 편집된 메시지 (텍스트 + 캡션)
    app.add_handler(MessageHandler(
        filters.UpdateType.EDITED_MESSAGE & _group,
        on_group_message))
    app.add_handler(CommandHandler("spam_add", cmd_spam_add))
    app.add_handler(CommandHandler("spam_remove", cmd_spam_remove))
    app.add_handler(CommandHandler("spam_list", cmd_spam_list))
    app.add_handler(CommandHandler("unban", cmd_unban))
    app.add_handler(CommandHandler("reset_warning", cmd_reset_warning))
    app.add_handler(CommandHandler("check_warning", cmd_check_warning))
    app.add_handler(CommandHandler("report", cmd_report))

    print("=" * 50)
    print("Antispam Bot Started")
    print(f"Admins: {ADMIN_IDS}")
    print(f"GPT: {'ON' if OPENAI_API_KEY else 'OFF (hard_ban only)'}")
    print("=" * 50)

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
