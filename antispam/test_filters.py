# -*- coding: utf-8 -*-
"""
안티스팸 필터 테스트
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from antispam.filters import check_message

# 테스트 케이스
test_cases = [
    # (메시지, 기대값_is_spam, 설명)
    (
        "설 연휴 해외로 72만 명…가장 많이 찾은 곳은 '일본' - https://n.news.naver.com/article/243/0000093137",
        False,
        "네이버 뉴스 공유 (정상)"
    ),
    (
        "미국 CPI 발표 https://finance.naver.com/news/news_read.naver?article_id=0005150288",
        False,
        "네이버 금융 뉴스 (정상)"
    ),
    (
        "엔비디아 실적 분석 https://www.youtube.com/watch?v=abc123",
        False,
        "유튜브 링크 (정상)"
    ),
    (
        "비트코인 차트 분석 https://www.tradingview.com/chart/BTCUSD/",
        False,
        "TradingView 링크 (정상)"
    ),
    (
        "무료 시그널 받으세요! t.me/free_signals_korea",
        True,
        "스팸: 텔레그램 채널 홍보 + 무료 시그널"
    ),
    (
        "일당 100만 보장! 카톡 오픈채팅 참여 open.kakao.com/o/abc123",
        True,
        "스팸: 수익 보장 + 카톡 오픈채팅"
    ),
    (
        "카지노 사이트 추천합니다",
        True,
        "스팸: 하드밴 키워드 (카지노)"
    ),
    (
        "bit.ly/get-rich-quick",
        True,
        "스팸: 단축 URL (의심 패턴)"
    ),
]


async def run_tests():
    print("=" * 80)
    print("안티스팸 필터 테스트")
    print("=" * 80)

    passed = 0
    failed = 0

    for i, (text, expected_spam, desc) in enumerate(test_cases, 1):
        is_spam, method, details = await check_message(text)

        status = "✅ PASS" if is_spam == expected_spam else "❌ FAIL"
        if is_spam == expected_spam:
            passed += 1
        else:
            failed += 1

        print(f"\n[테스트 {i}] {status}")
        print(f"설명: {desc}")
        print(f"메시지: {text[:100]}...")
        print(f"기대: {'스팸' if expected_spam else '정상'} / 결과: {'스팸' if is_spam else '정상'}")
        if is_spam:
            print(f"판별 방법: {method}, 상세: {details}")

    print("\n" + "=" * 80)
    print(f"결과: {passed}개 통과, {failed}개 실패 (총 {len(test_cases)}개)")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_tests())
