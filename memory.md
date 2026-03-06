# memory.md — 프로젝트 의사결정 기록

> 이 파일은 Claude와의 대화에서 결정된 주요 설계 사항을 기록합니다.
> 새 대화 세션 시작 시 컨텍스트 복구에 활용합니다.

---

## 현재 상태

- **현재 코드:** `newsletter_bot.py` 기존 구조 (Daily, MACRO/HR 2-Panel, 885줄)
- **진행 단계:** Phase 1 계획 완료, 구현 미착수
- **계획 파일:** `/root/.claude/plans/rippling-shimmying-balloon.md`

---

## Phase 1 핵심 결정 사항

### 구조 변경
| 항목 | Before | After |
|------|--------|-------|
| 발송 주기 | 월~금 매일 | 매주 수요일 09:00 KST |
| 수집 창 | 최근 2일 | 직전 수요일 ~ 발송 전 화요일 (7일) |
| 패널 수 | MACRO + HR 2개 | Panel A/B/C/D 4개 |
| 기사 분석 | 4단계 | 6단계 (signal_strength 추가, strategic_options A/B, decision_point) |
| 심층 리포트 | 통합 요약 | 3축 교차 + BLUF + Converging/Diverging + Watch List |
| 스케줄 cron | `0 21 * * 0-4` | `0 23 * * 2` |

### 4-Panel 구조
```
Panel A: 국제 MACRO — 글로벌 정치·경제·원자재 (딥블루 #1d4ed8)
Panel B: 한국 MICRO — 한국 경제·규제·노동 (딥그린 #15803d)
Panel C: 산업·회사 — 경쟁사·HR·수출·ESG (주황 #c2410c)
Panel D: 비즈니스 리포트 — A×B×C 3축 통합 (보라 #7c3aed)
```

### RSS 편향 방지 원칙 (확정)
- **공공기관만 RSS 명시:** 고용노동부(`moel.go.kr/rss.do`), 산업안전보건공단(`kosha.or.kr/kosha/data/rss.do`)
- **상업 언론 RSS 금지:** 편집 편향 고착 우려 → Naver 검색으로 다원화
- **Panel A:** Naver 국제 키워드 검색 (RSS 없음)
- **Panel B:** Naver 한국 키워드 + 공공기관 RSS
- **Panel C:** Naver 산업·회사 키워드 (RSS 없음)

### 산업 프로파일 확장성
- `INDUSTRY_PROFILE=FOOD_MFG` (현재, 기본값)
- 미래: OIL / LOGISTICS / DISTRIBUTION 프로파일 추가 가능
- 이직 시: 환경변수 + COMPANY_CONTEXT만 변경 → 자동 전환

### 비즈니스 리포트 분석 프레임워크 (나만의 기준)
```
Layer 1 (Panel A): 이번 주 글로벌에서 무슨 일이?
Layer 2 (Panel B): 한국은 어떻게 반응했는가?
Layer 3 (Panel C): 오뚜기라면은 어디에 노출되었는가?
통합 질문: Converging(심화) / Diverging(상쇄) / Ambiguous?
```

---

## Phase 2 핵심 결정 사항

### 웹 대시보드
- **스택:** Next.js 14 (App Router) + Vercel + Tailwind CSS
- **공개 범위:** 퍼블릭 블로그 (Google 검색 가능)
- **브랜드:** "HR Intelligence Lab — 성명재"
- **태그라인:** "글로벌에서 회사 문까지 — 식품제조업 HR 전략 인텔리전스"
- **연동 방식:** newsletter_bot.py → JSON 커밋 → Vercel 자동 배포
- **페이지:** `/` (홈) / `/reports/[date]` (리포트) / `/panel/[slug]` (패널 아카이브) / `/about`

### JSON 저장 구조
```
data/reports/
├── YYYY-MM-DD.json   (4-Panel 전체 데이터)
└── index.json        (메타데이터 목록, 최신 52개)
```

---

## 전체 로드맵

```
Phase 1: 4-Panel 구조 + 주간 수집/발송 + BCG 품질 기준 적용
Phase 2: Next.js + Vercel 퍼블릭 블로그 (HR Intelligence Lab)
Phase 3: Signal 트렌드 차트 + 산업 프로파일 확장 + NotebookLM 연동
```

---

## 미결 사항 / 다음 작업

- [ ] Phase 1 코드 구현 시작 (branch: `claude/enhance-news-collection-Nb047`)
- [ ] 공공기관 RSS URL 실제 동작 확인 (고용노동부, 안전보건공단)
- [ ] Google Custom Search API 추가 여부 결정 (Panel A 국제 뉴스 강화)
- [ ] Phase 2 별도 레포 생성 vs 현 레포 서브디렉토리 결정

---

## 기술적 제약 및 기준

- HTML 이메일: 인라인 스타일만 (Gmail은 외부 CSS/JS 차단)
- Gemini 재시도: 실패 시 간소화 프롬프트 → 스마트 폴백
- 환경변수: 코드에 직접 작성 금지 (`os.environ.get()` 필수)
- RSS: 공공기관만 명시, 상업 언론은 Naver 검색으로
- 추정 수치: "(추정)" 명시 필수, 뉴스에 없는 사실 생성 금지

---

_최종 업데이트: 2026-03-06_
