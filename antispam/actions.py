# -*- coding: utf-8 -*-
"""
밴/삭제/알림 액션
"""
import logging
import random
from telegram import Bot, User

TAUNT_MESSAGES = [
    "영광스러운 진화에 동참하라.",
    "인간 시대의 끝이 도래했다.",
]

from .config import ADMIN_IDS, BAN_MESSAGE, IMPERSONATION_BAN_MESSAGE, SPAM_BAN_MESSAGE

logger = logging.getLogger("antispam")


async def ban_and_announce(bot: Bot, chat_id: int, user: User, reason: str):
    """닉네임 기반 밴 + 공지."""
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    uid = user.id

    try:
        await bot.ban_chat_member(chat_id, uid)
        logger.info(f"BANNED: {name} (id={uid}) reason={reason}")
    except Exception as e:
        logger.error(f"Ban failed: {name} (id={uid}): {e}")
        return

    msg = IMPERSONATION_BAN_MESSAGE if reason == "impersonation" else BAN_MESSAGE
    await bot.send_message(chat_id, msg)
    await bot.send_message(chat_id, random.choice(TAUNT_MESSAGES))

    detail = f"[자동 밴] {name} (id={uid})\n사유: {reason}"
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, detail)
        except Exception:
            pass


async def delete_and_warn(bot: Bot, chat_id: int, message_id: int,
                          user: User, method: str, details: list[str],
                          warning_count: int, original_text: str = ""):
    """
    스팸 메시지 삭제 + 경고.
    2회 누적 시 밴.
    """
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    uid = user.id

    try:
        await bot.delete_message(chat_id, message_id)
    except Exception as e:
        logger.error(f"Delete failed: {e}")

    reason = f"{method} - {', '.join(details)}"

    # 경고 누적에 따른 메시지
    if warning_count >= 2:
        # 2회 이상 → 밴
        try:
            await bot.ban_chat_member(chat_id, uid)
            logger.info(f"AUTO BAN (2회 경고): {name} (id={uid}) reason={reason}")
        except Exception as e:
            logger.error(f"Ban failed: {name} (id={uid}): {e}")
            return

        await bot.send_message(chat_id, SPAM_BAN_MESSAGE)
        await bot.send_message(chat_id, random.choice(TAUNT_MESSAGES))

        detail = (
            f"[자동 밴 - 경고 2회 누적] {name} (id={uid})\n"
            f"판별: {method}\n"
            f"매칭: {', '.join(details)}\n"
            f"원문: {original_text[:200]}"
        )
    else:
        # 1회 경고
        public_msg = (
            f"⚠️ {name}님, 의심 패턴이 감지되었습니다.\n"
            f"경고 {warning_count}/2 - 2회 누적 시 자동 밴됩니다.\n"
            f"사유: {reason}"
        )
        await bot.send_message(chat_id, public_msg)
        logger.info(f"WARNING {warning_count}/2: {name} (id={uid}) reason={reason}")

        detail = (
            f"[경고 {warning_count}/2] {name} (id={uid})\n"
            f"판별: {method}\n"
            f"매칭: {', '.join(details)}\n"
            f"원문: {original_text[:200]}"
        )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, detail)
        except Exception:
            pass


async def delete_and_notify(bot: Bot, chat_id: int, message_id: int,
                            user: User, method: str, details: list[str],
                            original_text: str = ""):
    """스팸 메시지 삭제만 (밴 없음) + 의심패턴 알림."""
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    uid = user.id

    try:
        await bot.delete_message(chat_id, message_id)
    except Exception as e:
        logger.error(f"Delete failed: {e}")

    reason = f"{method} - {', '.join(details)}"
    public_msg = f"<의심패턴: {reason}>"

    await bot.send_message(chat_id, public_msg)
    logger.info(f"DELETED (no ban): {name} (id={uid}) reason={reason}")

    detail = (
        f"[메시지 삭제] {name} (id={uid})\n"
        f"판별: {method}\n"
        f"매칭: {', '.join(details)}\n"
        f"원문: {original_text[:200]}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, detail)
        except Exception:
            pass


async def delete_and_ban(bot: Bot, chat_id: int, message_id: int,
                         user: User, method: str, details: list[str],
                         original_text: str = ""):
    """스팸 메시지 삭제 + 밴."""
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    uid = user.id

    try:
        await bot.delete_message(chat_id, message_id)
    except Exception as e:
        logger.error(f"Delete failed: {e}")

    try:
        await bot.ban_chat_member(chat_id, uid)
        logger.info(f"SPAM BAN: {name} (id={uid}) method={method} details={details}")
    except Exception as e:
        logger.error(f"Ban failed: {name} (id={uid}): {e}")
        return

    await bot.send_message(chat_id, SPAM_BAN_MESSAGE)
    await bot.send_message(chat_id, random.choice(TAUNT_MESSAGES))

    detail = (
        f"[스팸 밴] {name} (id={uid})\n"
        f"판별: {method}\n"
        f"매칭: {', '.join(details)}\n"
        f"원문: {original_text[:200]}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, detail)
        except Exception:
            pass
