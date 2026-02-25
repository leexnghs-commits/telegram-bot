# -*- coding: utf-8 -*-
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# 안티스팸 봇 토큰
ANTISPAM_BOT_TOKEN = os.getenv("ANTISPAM_BOT_TOKEN", "")

# OpenAI API (GPT-4o-mini)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Anthropic API (Claude Haiku)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# 관리자 ID
ADMIN_IDS = [
    int(uid.strip())
    for uid in os.getenv("ANTISPAM_ADMIN_IDS", "1201674020").split(",")
    if uid.strip()
]

# 밴 알림 메시지
BAN_MESSAGE = "로씨아와 응우옌은 스팸으로 간주하여 광고를 올리건 말건 알 바 없고 일단 썰어버립니다."
IMPERSONATION_BAN_MESSAGE = "사칭은 보나마나 광고일거라 일단 썰고 시작 byGPT 봇"
SPAM_BAN_MESSAGE = "스팸 메시지 감지. 썰어버립니다."

# 사칭 감지 대상 닉네임 (소문자로 비교)
PROTECTED_NAMES = ["pluto research", "플루토리서치", "플루토 리서치", "plutoresearch"]
