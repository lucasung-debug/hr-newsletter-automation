# CLAUDE.md

**Stack:** Python 단일 파일 · Gemini 2.0 Flash · Naver 뉴스 API · Gmail SMTP · feedparser
**실행:** GitHub Actions — 매주 수요일 UTC 23:00 (KST 수요일 08:00~09:00)

## Key Files

- `newsletter_bot.py` — 전체 로직 (885줄, 13개 섹션, Phase 1 전면 개편 예정)
- `.github/workflows/main.yml` — 스케줄 + 환경변수 설정

## Required Env Vars

- `GEMINI_API_KEY` — AI 분석
- `GMAIL_APP_PASSWORD` — Gmail 발신 + IMAP 수신
- `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` — 뉴스 수집
- `RECIPIENT_EMAILS` — 수신자 콤마 구분 (기본: tjdaudwo21@otokirm.com)
- `BOT_MODE` — `newsletter` (기본) 또는 `weekend_request`
- `NEWS_COLLECTION_DAYS` — 수집 창 일수 (기본: 7)
- `INDUSTRY_PROFILE` — 산업 프로파일 (기본: FOOD_MFG)
- `GEMINI_DEEP_MODEL` — 비즈니스 리포트 모델 (기본: gemini-2.0-flash)

## 목표 Flow (Phase 1 — 4-Panel Weekly)

```
[매주 화요일 UTC 23:00 GitHub Actions 실행]

Panel A (국제 MACRO):  Naver(글로벌 키워드, 7일)
Panel B (한국 MICRO):  Naver(한국 키워드, 7일) + 공공기관 RSS만
Panel C (산업·회사):   Naver(산업 키워드, 7일)
  ↓ 관련도 필터 + 패널 간 교차 중복 제거
각 패널 top-3 → Gemini 6단계 분석
  ↓ 8초 딜레이 (패널 간)
Panel D (비즈니스 리포트): 3축 통합 BCG/Goldman 프롬프트
  ↓ 품질 게이트
JSON 저장(data/reports/) → 이메일 발송
```

## 현재 Flow (기존, Phase 1 이전)

```
뉴스 수집(Naver, 2일) → 관련도 필터 → 교차 중복 제거
→ Gemini 분석(MACRO / HR) → 심층 리포트
→ 품질 게이트 → 회사 소식 → HTML 생성 → Gmail 발송
```

## 4-Panel 구조 (Phase 1 목표)

| Panel | 역할 | Gemini 역할 | 색상 |
|-------|------|------------|------|
| A | 국제 MACRO — 글로벌 정치·경제·원자재 | Goldman Sachs 글로벌 리서치 | #1d4ed8 딥블루 |
| B | 한국 MICRO — 경제·노동·산업 규제 | BCG Korea 시니어 컨설턴트 | #15803d 딥그린 |
| C | 산업·회사 — 경쟁사·HR·수출·ESG | 오뚜기라면 HR 전략 애널리스트 | #c2410c 주황 |
| D | 비즈니스 리포트 — 3축 통합 전략 | BCG/Goldman 30년 경력 컨설턴트 | #7c3aed 보라 |

## 6단계 기사 분석 스키마 (Phase 1 목표)

```json
{
  "signal_strength": "High|Medium|Low",
  "fact": "수치 포함 2~3문장",
  "so_what": "그래서 오뚜기라면에 뭐가 달라지는가? — 1문장",
  "business_impact": "재무·운영·인력 영향",
  "strategic_options": [
    {"option": "A. 선제 대응", "action": "...", "tradeoff": "..."},
    {"option": "B. 관망", "action": "...", "tradeoff": "..."}
  ],
  "decision_point": "○○까지 ○○ 결정. 미결 시 ○○."
}
```

## 비즈니스 리포트(Panel D) 스키마 (Phase 1 목표)

```json
{
  "bluf": ["문장1", "문장2", "문장3"],
  "direction": "Converging|Diverging|Ambiguous",
  "direction_reason": "1문장",
  "causal_narrative": "A→B→C 3층 인과 서사",
  "key_variable": "핵심 변수명",
  "risks": [{"risk": "...", "likelihood": "High|Medium", "impact": "High|Medium"}],
  "decision_point": "기한 + 미결 시 리스크",
  "watch_list": ["지표1", "지표2"]
}
```

## Key Patterns

- **회사 컨텍스트:** `COMPANY_CONTEXT` 전역 상수 — 모든 Gemini 프롬프트에 자동 주입
- **Gemini 재시도:** 실패 시 간소화 프롬프트로 2차 시도, 이후 스마트 폴백
- **품질 게이트:** real_panels ≥2 → full / 1 → full+경고 / fallback → light / 없음 → 중단
- **Rate limit 보호:** 패널 간 8초 딜레이, 비즈니스 리포트 전 10초 대기
- **RSS 편향 원칙:** 공공기관(고용노동부, 안전보건공단)만 RSS 명시. 상업 언론은 Naver 검색으로 다원화
- **산업 프로파일:** `INDUSTRY_PROFILE` 환경변수로 키워드·관련도 용어 자동 선택 (현재: FOOD_MFG)
- **토요일 모드:** `BOT_MODE=weekend_request` → 회사소식 요청 메일 → 다음 주 IMAP 회신 확인

## Constraints (하지 말 것)

- `COMPANY_CONTEXT` 수정 시 모든 Gemini 프롬프트 영향 반드시 확인
- `SENDER_EMAIL` 하드코딩 변경 금지 (Gmail SMTP 인증과 연동)
- 환경변수를 코드에 직접 작성 금지 — `os.environ.get()` 만 사용
- 상업 언론 RSS URL 하드코딩 금지 — Naver 검색 키워드로 대체
- 뉴스에 없는 사실·수치 Gemini 생성 금지 — 추정 시 "(추정)" 명시

## 코딩 기준

- 새 함수 추가 시 기존 섹션 번호 체계(1~13) 유지, 신규는 14+ 부여
- 모든 외부 API 호출은 timeout + try/except 필수
- 로그: `logger.info/warning/error` 사용, 수집 건수와 필터 결과 반드시 출력
- HTML 이메일: 인라인 스타일만, JavaScript/CSS 파일 참조 금지 (Gmail 차단)
- JSON 파싱 실패 시 `extract_json_from_text()` 헬퍼 사용 (brace-depth 방식)

## Compact Instructions

When compacting, always preserve:
- 수정 중인 함수명과 섹션 번호 (1~13)
- 변경된 Gemini 프롬프트 내용 요약
- 품질 게이트 / 폴백 로직 변경사항
- 현재 Phase 진행 상태 (Phase 1 구현 중 / 완료 / Phase 2 시작)

Drop:
- newsletter_bot.py 전체 코드 읽기 결과
- 반복된 API 응답 로그
