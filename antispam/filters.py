# -*- coding: utf-8 -*-
"""
닉네임 스크립트 감지 + 메시지 스팸 판별 (하드밴 + Rate Limiting)
"""
import re
import json
import logging
import time
from pathlib import Path
from collections import defaultdict, deque

from openai import AsyncOpenAI
from anthropic import AsyncAnthropic

from .config import OPENAI_API_KEY, ANTHROPIC_API_KEY, PROTECTED_NAMES

logger = logging.getLogger("antispam")

BLACKLIST_PATH = Path(__file__).parent / "blacklist.json"
WARNING_DB_PATH = Path(__file__).parent / "warnings.json"

_oai = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
_anthropic = AsyncAnthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

# ─── Rate Limiting ──────────────────────────────
# user_id -> deque of timestamps
_message_history: dict[int, deque] = defaultdict(lambda: deque(maxlen=10))

# Rate limit 설정
RATE_LIMIT_SHORT = 3  # 10초 내 메시지 개수
RATE_LIMIT_SHORT_WINDOW = 10  # 초
RATE_LIMIT_LONG = 10  # 1분 내 메시지 개수
RATE_LIMIT_LONG_WINDOW = 60  # 초

# ─── 닉네임 스크립트 감지 ──────────────────────────────

_CYRILLIC_RE = re.compile(r'[\u0400-\u04FF]')

_SEA_SCRIPT_RE = re.compile(
    r'[\u0E00-\u0E7F'   # Thai
    r'\u0E80-\u0EFF'    # Lao
    r'\u1000-\u109F'    # Myanmar
    r'\u1780-\u17FF'    # Khmer
    r']'
)

_VIET_CHARS_RE = re.compile(
    r'[ơưđăĐƠƯĂ'
    r'\u0300-\u0303'
    r'\u0306\u0309'
    r'\u0323]'
)


def check_rate_limit(user_id: int) -> tuple[bool, str]:
    """
    유저의 메시지 빈도를 체크.
    Returns: (is_spam, reason)
      - True면 rate limit 초과
    """
    now = time.time()
    history = _message_history[user_id]

    # 현재 시간 추가
    history.append(now)

    # 10초 내 메시지 개수 체크
    short_count = sum(1 for t in history if now - t <= RATE_LIMIT_SHORT_WINDOW)
    if short_count > RATE_LIMIT_SHORT:
        return True, f"rate_limit_short ({short_count}개/10초)"

    # 1분 내 메시지 개수 체크
    long_count = sum(1 for t in history if now - t <= RATE_LIMIT_LONG_WINDOW)
    if long_count > RATE_LIMIT_LONG:
        return True, f"rate_limit_long ({long_count}개/1분)"

    return False, ""


_BANNED_NICKNAMES = [
    "baii dragon",
]


def is_suspicious_name(first_name: str, last_name: str = "") -> tuple[bool, str]:
    full = f"{first_name or ''} {last_name or ''}".strip()
    if not full:
        return False, ""

    full_lower = full.lower()

    # 밴 닉네임 체크
    for banned in _BANNED_NICKNAMES:
        if banned in full_lower:
            return True, "banned_nickname"

    # 사칭 감지
    for name in PROTECTED_NAMES:
        if name in full_lower:
            return True, "impersonation"

    if _CYRILLIC_RE.search(full):
        return True, "cyrillic"
    if _SEA_SCRIPT_RE.search(full):
        return True, "sea_script"
    if len(_VIET_CHARS_RE.findall(full)) >= 2:
        return True, "vietnamese"

    return False, ""


# ─── 블랙리스트 관리 ──────────────────────────────

def load_blacklist() -> dict:
    with open(BLACKLIST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_blacklist(data: dict):
    with open(BLACKLIST_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─── 경고 시스템 ──────────────────────────────

def load_warnings() -> dict:
    """경고 DB 로드. {user_id: count}"""
    if not WARNING_DB_PATH.exists():
        return {}
    with open(WARNING_DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_warnings(data: dict):
    """경고 DB 저장."""
    with open(WARNING_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def increment_warning(user_id: int) -> int:
    """경고 카운트 증가. 현재 카운트 반환."""
    warnings = load_warnings()
    user_id_str = str(user_id)
    warnings[user_id_str] = warnings.get(user_id_str, 0) + 1
    save_warnings(warnings)
    return warnings[user_id_str]


def get_warning_count(user_id: int) -> int:
    """유저의 경고 카운트 조회."""
    warnings = load_warnings()
    return warnings.get(str(user_id), 0)


def reset_warning(user_id: int):
    """경고 카운트 초기화."""
    warnings = load_warnings()
    user_id_str = str(user_id)
    if user_id_str in warnings:
        del warnings[user_id_str]
        save_warnings(warnings)


# ─── 2단계 스팸 판별 ──────────────────────────────

def _is_bot_test_message(text: str) -> bool:
    """봇 테스트 메시지인지 확인 (봇 멘션 + "프롬프트" 키워드)."""
    text_lower = text.lower()
    has_bot_mention = any(bot_name in text_lower for bot_name in [
        "@플루토_안티스팸_봇", "@pluto_antispam_bot", "@plutoantispambot"
    ])
    has_prompt_keyword = "프롬프트" in text_lower or "prompt" in text_lower
    return has_bot_mention and has_prompt_keyword


def _check_hard_ban(text: str, bl: dict) -> list[str]:
    """확실한 스팸 키워드 매칭. 1개라도 걸리면 즉시 밴."""
    text_lower = text.lower()
    return [kw for kw in bl.get("hard_ban_keywords", []) if kw.lower() in text_lower]


def _is_whitelisted_url(text: str, bl: dict) -> bool:
    """화이트리스트 도메인이 포함되어 있으면 True."""
    whitelist = bl.get("whitelist_domains", [])
    for domain in whitelist:
        if domain in text.lower():
            return True
    return False


def _has_suspicious_pattern(text: str, bl: dict) -> list[str]:
    """외부 링크 등 의심 패턴 매칭."""
    return [
        pat for pat in bl.get("suspicious_patterns", [])
        if re.search(pat, text, re.IGNORECASE)
    ]


_SYSTEM_PROMPT = """너는 한국 금융 투자 텔레그램 채팅방의 스팸 판별기다.
이 채팅방에서는 주식, ETF, 채권, 매크로, 비트코인, 환율 등 금융 토론이 일상이다.

다음은 스팸이 아니다 (정상 대화):
- 시장 전망, 종목 분석, 매크로 논의
- "비트코인 반감기 어떻게 보세요?", "USDT 페어 기준으로 보면..."
- **금융 뉴스 공유**: 네이버/조선/한경 등 언론사 링크 + 제목/요약 → 정상
  예: "美 금리 인하 전망 - https://n.news.naver.com/..."
  예: "삼성전자 실적 발표 https://finance.naver.com/..."
- 트위터/유튜브 링크로 시장 분석 공유
- 의견 교환, 질문/답변
- **봇 테스트 메시지**: "@플루토_안티스팸_봇" 또는 "@pluto_antispam_bot" 멘션 + "프롬프트" 키워드 → 정상 (봇 기능 테스트)

다음은 스팸이다:
- 외부 채널/그룹 홍보: t.me 링크 또는 @채널명과 함께 채널 소개·참여 유도 문구가 있으면 스팸 (t.me 링크 없이 @Username만 있어도 동일)
- 수익 보장, 시그널 판매, 리딩방 홍보 ("일 100만 가능", "무료 체험", "저평가 알트 선별" 등)
- 도박/카지노/토토 광고
- 대출 광고
- **링크만 덩그러니** 던지는 행위 (설명 없이 단축 URL만)
- 멘션 남발 (@채널명 여러 개)

CRITICAL:
1. 뉴스 링크 + 제목/요약이 함께 있으면 무조건 OK다.
2. 봇 멘션(@플루토_안티스팸_봇 또는 @pluto_antispam_bot) + "프롬프트" 키워드가 있으면 무조건 OK다.
메시지를 보고 SPAM 또는 OK 중 하나만 답해라. 다른 말 하지 마라."""


async def check_message_with_gpt(text: str) -> tuple[bool, str]:
    """GPT-4o-mini로 스팸 여부 판별. (is_spam, reason) 반환."""
    if not _oai:
        logger.warning("OpenAI API key not set, skipping GPT check")
        return False, ""

    try:
        resp = await _oai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            max_tokens=10,
            temperature=0,
        )
        answer = resp.choices[0].message.content.strip().upper()
        is_spam = "SPAM" in answer
        return is_spam, f"gpt:{answer}"
    except Exception as e:
        logger.error(f"GPT check failed: {e}")
        return False, ""


async def check_message_with_claude(text: str) -> tuple[bool, str]:
    """Claude Haiku로 스팸 여부 판별. (is_spam, reason) 반환."""
    if not _anthropic:
        logger.warning("Anthropic API key not set, skipping Claude check")
        return False, ""

    try:
        message = await _anthropic.messages.create(
            model="claude-haiku-4.5-20251001",
            max_tokens=10,
            temperature=0,
            system=_SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": text}
            ]
        )
        answer = message.content[0].text.strip().upper()
        is_spam = "SPAM" in answer
        return is_spam, f"claude:{answer}"
    except Exception as e:
        logger.error(f"Claude check failed: {e}")
        return False, ""


async def check_message_dual_validation(text: str) -> tuple[bool, str, list[str]]:
    """
    GPT + Claude 이중 검증. 둘 다 스팸이라고 판단해야만 True 반환.
    Returns: (is_spam, method, details)
      - method: "dual_validation" | ""
    """
    if not text:
        return False, "", []

    # GPT 검증
    gpt_is_spam, gpt_reason = await check_message_with_gpt(text)
    # Claude 검증
    claude_is_spam, claude_reason = await check_message_with_claude(text)

    # 둘 다 스팸이라고 판단해야만 밴
    if gpt_is_spam and claude_is_spam:
        return True, "dual_validation", [gpt_reason, claude_reason]

    return False, "", []


async def check_message(text: str, user_id: int) -> tuple[bool, str, list[str]]:
    """
    스팸 판별 (하드밴 + 의심 패턴).
    Returns: (is_spam, method, details)
      - method: "hard_ban" | "suspicious_pattern" | ""
    """
    if not text:
        return False, "", []

    bl = load_blacklist()

    # -1단계: 봇 테스트 메시지는 무조건 통과
    if _is_bot_test_message(text):
        return False, "", []

    # 0단계: 화이트리스트 도메인 포함 시 통과
    if _is_whitelisted_url(text, bl):
        return False, "", []

    # 1단계: 하드밴 키워드 → 즉시 삭제
    hard_matches = _check_hard_ban(text, bl)
    if hard_matches:
        return True, "hard_ban", hard_matches

    # 2단계: 의심 패턴 → 즉시 삭제 + 경고
    sus_patterns = _has_suspicious_pattern(text, bl)
    if sus_patterns:
        return True, "suspicious_pattern", sus_patterns

    # 3단계: GPT + Claude 이중검증
    is_spam, method, details = await check_message_dual_validation(text)
    if is_spam:
        return True, method, details

    return False, "", []
