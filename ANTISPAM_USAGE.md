# Antispam Bot 사용법

## 신고 기능 (`/신고` 명령어)

### 개요
- 유저가 `/신고` 명령어로 의심스러운 메시지를 신고하면, **GPT-4o-mini**와 **Claude Haiku**가 동시 검증
- **두 AI 모두 스팸이라고 판단해야만** 자동 밴 처리
- 한쪽이라도 정상이라고 판단하면 밴하지 않음

### 사용법

1. **스팸 의심 메시지에 답장**으로 `/신고` 입력
   ```
   [스팸 메시지]
      └─ /신고  (답장으로 입력)
   ```

2. 봇이 GPT와 Claude를 통해 자동 검증
   - 검증 중: "🔍 GPT와 Claude가 동시 검증 중입니다..."
   - 스팸 판정: "✅ GPT와 Claude 모두 스팸으로 판정하여 밴 처리되었습니다."
   - 정상 판정: "❌ GPT 또는 Claude가 스팸이 아니라고 판단했습니다."

### 설정 방법

1. `.env` 파일에 Anthropic API 키 추가:
   ```bash
   # Anthropic (Claude Haiku 이중 검증용)
   ANTHROPIC_API_KEY=sk-ant-api03-...
   ```

2. API 키 확인:
   - OpenAI API: https://platform.openai.com/api-keys
   - Anthropic API: https://console.anthropic.com/settings/keys

3. 봇 실행:
   ```bash
   cd projects/telegram_bot
   python antispam_bot.py
   ```

### 검증 로직

1. **자동 스팸 필터** (기존 기능 유지):
   - 러시아어/동남아어 닉네임 → 즉시 밴
   - 하드밴 키워드 (카지노/토토) → 즉시 밴
   - 의심 패턴 (외부 링크) → GPT만 검증 → 스팸이면 밴

2. **유저 신고 (`/신고`)** (신규):
   - GPT-4o-mini 검증
   - Claude Haiku 검증
   - **둘 다 스팸 판정해야만 밴**
   - 로그에 신고자/피신고자 정보 기록

### 관리자 명령어

- `/spam_add <키워드>` - 하드밴 키워드 추가
- `/spam_remove <키워드>` - 하드밴 키워드 제거
- `/spam_list` - 블랙리스트 조회
- `/unban <user_id>` - 밴 해제
- `/신고` - 이중 검증 스팸 신고 (모든 유저 사용 가능)

### 로그 예시

```
# 신고 성공 (밴 처리)
USER REPORT BAN: user_name (id=123456) by reporter_name (id=789012)
details=['gpt:SPAM', 'claude:SPAM']

# 신고 실패 (정상 판정)
USER REPORT REJECTED: user_name (id=123456) by reporter_name (id=789012)
reason=dual_validation_failed
```

### 주의사항

- 관리자와 봇은 신고할 수 없음
- 답장 없이 `/신고`만 입력하면 작동하지 않음
- API 키가 없으면 해당 검증기가 비활성화됨 (Claude 키 없으면 GPT만, OpenAI 키 없으면 Claude만)
