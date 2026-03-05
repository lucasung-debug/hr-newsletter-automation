# CLAUDE.md

**Stack:** Python 단일 파일 · Gemini 2.0 Flash · Naver 뉴스 API · Gmail SMTP
**실행:** GitHub Actions 자동 스케줄 (월~금 뉴스레터, 토 회사소식 요청)

## Key Files

- `newsletter_bot.py` — 전체 로직 (885줄, 13개 섹션)

## Required Env Vars

- `GEMINI_API_KEY` — AI 분석
- `GMAIL_APP_PASSWORD` — Gmail 발신 + IMAP 수신
- `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` — 뉴스 수집
- `RECIPIENT_EMAILS` — 수신자 콤마 구분 (기본: tjdaudwo21@otokirm.com)
- `BOT_MODE` — `newsletter` (기본) 또는 `weekend_request`

## Flow

```
뉴스 수집(Naver) → 관련도 필터 → 교차 중복 제거
→ Gemini 분석(MACRO / HR) → 심층 리포트
→ 품질 게이트 → 회사 소식 → HTML 생성 → Gmail 발송
```

## Key Patterns

- **회사 컨텍스트:** `COMPANY_CONTEXT` 전역 상수 — 모든 Gemini 프롬프트에 자동 주입
- **Gemini 재시도:** 실패 시 간소화 프롬프트로 2차 시도, 이후 스마트 폴백
- **품질 게이트:** real 2개↑ → full / 1개 → full+경고 / 0개 → light / 없으면 발송 중단
- **Rate limit 보호:** MACRO→HR 8초 딜레이, 심층 리포트 전 10초 대기
- **토요일 모드:** `BOT_MODE=weekend_request` → 회사소식 요청 메일 → 다음 주 IMAP 회신 확인

## Constraints (하지 말 것)

- `COMPANY_CONTEXT` 수정 시 모든 Gemini 프롬프트 영향 반드시 확인
- `SENDER_EMAIL` 하드코딩 변경 금지 (Gmail SMTP 인증과 연동)
- 환경변수를 코드에 직접 작성 금지 — `os.environ.get()` 만 사용

## Compact Instructions

When compacting, always preserve:
- 수정 중인 함수명과 섹션 번호 (1~13)
- 변경된 Gemini 프롬프트 내용 요약
- 품질 게이트 / 폴백 로직 변경사항

Drop:
- newsletter_bot.py 전체 코드 읽기 결과
- 반복된 API 응답 로그
