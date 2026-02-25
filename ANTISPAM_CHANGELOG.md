# 안티스팸 봇 변경사항 (2026-02-14)

## 🎯 주요 변경사항

### 1. Rate Limiting 추가 (DDoS 방어)
- **목적**: AI 검수 제거로 인한 API 과부하 방지
- **로직**:
  - 10초 내 메시지 3개 이상 → 자동 밴
  - 1분 내 메시지 10개 이상 → 자동 밴
- **구현**: `filters.py:check_rate_limit()`
- **메모리 관리**: deque(maxlen=10)로 유저별 최근 10개 타임스탬프만 저장

### 2. 의심 패턴 즉시 삭제 + 경고 시스템
- **기존**: 의심 패턴 → GPT 검수 → 스팸이면 삭제
- **변경**: 의심 패턴 → 즉시 삭제 + 경고 누적
  - 1회 경고: 메시지 삭제 + 공개 경고 (⚠️ 경고 1/2)
  - 2회 경고: 메시지 삭제 + 자동 밴
- **구현**:
  - `filters.py`: `increment_warning()`, `get_warning_count()`, `reset_warning()`
  - `actions.py`: `delete_and_warn()`
  - `antispam/warnings.json`: 유저별 경고 카운트 저장

### 3. 유저 신고 시스템 단순화
- **기존**: `/신고` → GPT+Claude 이중 검증 → 둘 다 스팸이면 밴
- **변경**: `/신고` → 관리자에게 알림 전송 → 관리자 수동 처리
- **알림 내용**:
  - 신고자/신고 대상 정보
  - 원문 (500자 제한)
  - 채팅방 ID, 메시지 ID
  - 처리 명령어 안내

## 📋 새 명령어

### 관리자 명령어
```
/reset_warning <user_id>  - 유저의 경고 횟수 초기화
/check_warning <user_id>  - 유저의 경고 횟수 확인
/unban <user_id>          - 밴 해제 + 경고 초기화 (기존 명령어 개선)
```

### 일반 유저 명령어
```
/신고  - 답장한 메시지를 관리자에게 신고 (AI 검증 제거됨)
```

## 🔄 처리 흐름 변경

### Before (AI 검수 사용)
```
메시지 입력
  ↓
화이트리스트 체크
  ↓
하드밴 키워드 → 즉시 삭제
  ↓
의심 패턴 → GPT 검수 → 스팸이면 삭제
```

### After (AI 검수 제거)
```
메시지 입력
  ↓
Rate Limit 체크 → 초과 시 즉시 밴
  ↓
화이트리스트 체크
  ↓
하드밴 키워드 → 즉시 밴
  ↓
의심 패턴 → 즉시 삭제 + 경고 증가
  ↓
2회 누적 → 자동 밴
```

## 🗂️ 새 파일
- `antispam/warnings.json`: 유저별 경고 카운트 DB

## ⚙️ 설정 조정 가능 항목

`filters.py` 상단:
```python
RATE_LIMIT_SHORT = 3        # 10초 내 메시지 개수
RATE_LIMIT_SHORT_WINDOW = 10  # 초
RATE_LIMIT_LONG = 10        # 1분 내 메시지 개수
RATE_LIMIT_LONG_WINDOW = 60   # 초
```

## ⚠️ 주의사항

1. **Rate Limiting은 메모리에만 저장**: 봇 재시작 시 리셋됨 (정상 동작)
2. **경고는 파일에 영구 저장**: `warnings.json`에 저장되며 재시작 후에도 유지
3. **관리자는 모든 필터 무시**: `ADMIN_IDS` 목록의 유저는 Rate Limit 및 스팸 판별 대상 제외

## 🧪 테스트 체크리스트

- [ ] Rate Limiting: 10초 내 4개 메시지 전송 시 밴되는지 확인
- [ ] 경고 시스템: 의심 패턴 1회 → 경고, 2회 → 밴 확인
- [ ] 하드밴 키워드: 여전히 즉시 밴되는지 확인
- [ ] 유저 신고: 관리자에게 알림이 가는지 확인
- [ ] `/reset_warning`: 경고 초기화 확인
- [ ] `/check_warning`: 경고 조회 확인
- [ ] `/unban`: 밴 해제 + 경고 초기화 확인

## 💰 비용 절감 효과

### Before (AI 검수 사용)
- 의심 패턴당 GPT-4o-mini API 호출 1회 (약 $0.0001/call)
- 유저 신고당 GPT + Claude API 호출 2회 (약 $0.0003/report)
- 일 100건 의심 패턴 + 10건 신고 → 월 약 $4-5

### After (AI 검수 제거)
- **API 호출 0회**
- **월 비용 $0**

## 🚀 배포 방법

1. 기존 봇 중단
2. 코드 업데이트
3. `warnings.json` 파일이 생성되었는지 확인
4. 봇 재시작

```bash
cd projects/telegram_bot
python antispam_bot.py
```
