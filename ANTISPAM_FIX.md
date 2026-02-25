# 안티스팸봇 오작동 수정 (2026-02-14)

## 문제 상황

```
[스팸 밴] Mts k (id=960425946)
판별: gpt
매칭: https?://[a-zA-Z0-9\-]+\.[a-z]{2,}\S*, gpt:SPAM
원문: 설 연휴 해외로 72만 명…가장 많이 찾은 곳은 '일본' - https://n.news.naver.com/article/243/0000093137
```

**정상적인 네이버 뉴스 공유가 스팸으로 오판되어 유저가 밴됨**

---

## 원인 분석

### 1. 과도하게 넓은 URL 패턴
`blacklist.json`의 `suspicious_patterns`에 있던 정규식:
```regex
https?://[a-zA-Z0-9\-]+\.[a-z]{2,}\S*
```
- **모든 URL**을 의심 패턴으로 잡음 (네이버, 유튜브, 모든 뉴스 사이트 포함)
- 이로 인해 정상 뉴스 공유도 GPT 판별로 넘어감

### 2. GPT 오판
- URL이 suspicious_patterns에 걸려 GPT로 넘어감
- GPT가 "링크 + 제목" 형태의 뉴스 공유를 스팸으로 잘못 판단
- 프롬프트에 "맥락 없이 링크만 던지는 행위"라는 모호한 규칙이 있었으나,
  실제로는 제목과 함께 있었음에도 GPT가 오판

### 3. 복구 수단 부재
- 잘못 밴된 유저를 쉽게 복구할 방법이 없었음

---

## 해결 방안

### ✅ 1. 화이트리스트 도메인 시스템 추가

**변경 파일**: `antispam/blacklist.json`

신뢰할 수 있는 뉴스/금융 도메인 리스트 추가:
```json
"whitelist_domains": [
  "naver.com", "news.naver.com", "n.news.naver.com", "finance.naver.com",
  "chosun.com", "joins.com", "hankyung.com", "mk.co.kr", "sedaily.com",
  "reuters.com", "bloomberg.com", "wsj.com", "ft.com", "cnbc.com",
  "tradingview.com", "coindesk.com", "cointelegraph.com",
  "x.com", "twitter.com", "youtube.com", "youtu.be",
  ...
]
```

**동작 방식**:
- 화이트리스트 도메인이 메시지에 포함되어 있으면 **모든 검사를 건너뛰고 통과**
- 하드밴 키워드보다 **먼저** 체크 (0단계)

---

### ✅ 2. URL 패턴 제거

**변경 파일**: `antispam/blacklist.json`

```diff
"suspicious_patterns": [
  "t\\.me/[a-zA-Z0-9_]+",
  "bit\\.ly/\\S+",
  "open\\.kakao\\.com/\\S+",
- "https?://[a-zA-Z0-9\\-]+\\.[a-z]{2,}\\S*",  ← 삭제
  "linktr\\.ee/\\S+",
  "@[a-zA-Z0-9_]{5,}"
]
```

- 일반 URL 패턴 제거
- **스팸 전용 채널/서비스**만 패턴으로 유지 (t.me, bit.ly, open.kakao.com 등)

---

### ✅ 3. GPT 프롬프트 강화

**변경 파일**: `antispam/filters.py`

추가된 가이드라인:
```
다음은 스팸이 아니다 (정상 대화):
- **금융 뉴스 공유**: 네이버/조선/한경 등 언론사 링크 + 제목/요약 → 정상
  예: "美 금리 인하 전망 - https://n.news.naver.com/..."
  예: "삼성전자 실적 발표 https://finance.naver.com/..."
- 트위터/유튜브 링크로 시장 분석 공유

CRITICAL: 뉴스 링크 + 제목/요약이 함께 있으면 무조건 OK다.
```

---

### ✅ 4. 밴 복구 명령어 추가

**변경 파일**: `antispam_bot.py`

새 관리자 명령어:
```bash
/unban <user_id>
```

**사용 예시**:
```
/unban 960425946
```

**기능**:
- 잘못 밴된 유저를 즉시 밴 해제
- 로그에 기록 (누가, 누구를 언밴했는지)
- 단, 유저가 다시 입장하려면 **초대 링크를 통해 직접 재입장** 해야 함

---

## 변경 요약

| 파일 | 변경 내용 |
|------|----------|
| `blacklist.json` | • 화이트리스트 도메인 30개 추가<br>• 일반 URL 패턴 제거 |
| `filters.py` | • `_is_whitelisted_url()` 함수 추가<br>• `check_message()`에 0단계 화이트리스트 체크 추가<br>• GPT 프롬프트 강화 (뉴스 공유 명시) |
| `antispam_bot.py` | • `/unban` 명령어 추가<br>• `/spam_list`에 화이트리스트 표시 추가 |
| `test_filters.py` | • 테스트 스크립트 신규 작성 (8개 케이스) |

---

## 테스트

**실행 방법**:
```bash
cd projects/telegram_bot
python antispam/test_filters.py
```

**테스트 케이스**:
1. ✅ 네이버 뉴스 공유 → 정상
2. ✅ 네이버 금융 뉴스 → 정상
3. ✅ 유튜브 링크 → 정상
4. ✅ TradingView 차트 → 정상
5. ❌ 텔레그램 채널 홍보 + 무료 시그널 → 스팸
6. ❌ 수익 보장 + 카톡 오픈채팅 → 스팸
7. ❌ 카지노 키워드 → 스팸 (하드밴)
8. ❌ 단축 URL → 스팸

---

## 즉시 조치사항

### 1. 밴당한 유저 복구
```bash
# 텔레그램 그룹에서 관리자로 실행
/unban 960425946
```

### 2. 봇 재시작
```bash
cd projects/telegram_bot
python antispam_bot.py
```

### 3. 변경사항 확인
```bash
/spam_list
# → 화이트리스트 도메인 30개 표시 확인
```

---

## 추가 권장사항

### 1. 화이트리스트 도메인 추가
신뢰할 수 있는 금융/뉴스 사이트가 있다면 `blacklist.json`의 `whitelist_domains`에 추가:
```bash
# 직접 편집
nano projects/telegram_bot/antispam/blacklist.json

# 또는 유저에게 추천받아 추가
```

### 2. GPT 판별 로그 모니터링
- GPT가 오판한 케이스가 발견되면 프롬프트 개선
- `filters.py` 89-104번 라인의 `_SYSTEM_PROMPT` 수정

### 3. 테스트 케이스 지속 업데이트
- 새로운 오판 사례 발견 시 `test_filters.py`에 추가
- 회귀 방지

---

## 재발 방지 체크리스트

- [x] 화이트리스트 도메인 시스템 구축
- [x] 과도한 URL 패턴 제거
- [x] GPT 프롬프트에 뉴스 공유 케이스 명시
- [x] 밴 복구 명령어 추가
- [x] 테스트 스크립트 작성
- [ ] 봇 재시작 후 실제 운영 환경에서 검증
- [ ] 1주일 모니터링 후 추가 조정

---

## 문의사항
수정 후에도 오작동이 발생하면:
1. GPT 판별 로그 확인 (`logger.info`)
2. `/spam_list`로 현재 규칙 확인
3. 테스트 케이스 추가 후 재검증
