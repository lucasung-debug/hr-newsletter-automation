# memory.md — 프로젝트 의사결정 기록

> 이 파일은 Claude와의 대화에서 결정된 주요 설계 사항을 기록합니다.
> 새 대화 세션 시작 시 컨텍스트 복구에 활용합니다.

---

## 현재 상태

- **현재 코드:** `newsletter_bot.py` Phase 1 완료 (Weekly, 4-Panel A/B/C/D, 1338줄)
- **진행 단계:** Phase 1 구현 완료 + Phase 2 세부계획 논의 완료 (2026-03-06)
- **브랜치:** `claude/enhance-news-collection-Nb047`
- **최신 커밋:** `raw_articles` JSON 저장 추가 (d5a5cb3)

---

## Phase 1 핵심 결정 사항

### 구조 변경
| 항목 | Before | After |
|------|--------|-------|
| 발송 주기 | 월~금 매일 | 매주 수요일 09:00 KST |
| 수집 창 | 최근 2일 | NEWS_COLLECTION_DAYS 환경변수 (기본 7일) |
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

### 비즈니스 리포트 분석 프레임워크
```
Layer 1 (Panel A): 이번 주 글로벌에서 무슨 일이?
Layer 2 (Panel B): 한국은 어떻게 반응했는가?
Layer 3 (Panel C): 오뚜기라면은 어디에 노출되었는가?
통합 질문: Converging(심화) / Diverging(상쇄) / Ambiguous?
```

---

## Phase 1 구현 완료 내역 (2026-03-06)

### 주요 변경사항
| 항목 | Before | After |
|------|--------|-------|
| 코드 규모 | 885줄 | 1338줄 |
| 패널 구조 | MACRO + HR 2패널 | Panel A/B/C/D 4패널 |
| 분석 스키마 | 4단계 | 6단계 (signal_strength/fact/so_what/business_impact/strategic_options/decision_point) |
| 비즈니스 리포트 | 통합 요약 | BLUF + Direction + Causal Narrative + Risks + Watch List |
| 수집 기간 | 2일 고정 | NEWS_COLLECTION_DAYS 환경변수 (기본 7일) |
| RSS | 없음 | 고용노동부·안전보건공단 RSS (Panel B) |
| JSON 저장 | 없음 | data/reports/YYYY-MM-DD.json + index.json |
| raw_articles | 없음 | Panel A/B/C 원본 기사 전체 저장 (AI 선정 전) |
| Gemini 모델 | 하드코딩 gemini-2.0-flash | GEMINI_DEEP_MODEL 환경변수 |

### 신규 함수 (섹션 14)
- `save_report_json(raw_a, raw_b, raw_c)` — JSON + raw_articles 저장, Phase 2 연동 준비

### JSON 저장 구조
```
data/reports/
├── YYYY-MM-DD.json   (raw_articles + 4-Panel AI 분석 전체)
└── index.json        (메타데이터 목록, 최신 52개)
```

---

## Phase 2 세부계획 (2026-03-06 논의 완료)

### 확정 스펙
| 항목 | 결정 |
|------|------|
| 레포 | `hr-intelligence-lab` (신규, 별도) |
| 도메인 | `hr-intelligence-lab.vercel.app` (Vercel 기본) |
| 디자인 | BCG/McKinsey 스타일 (화이트 + 패널 컬러 강조) |
| 공개 범위 | 비색인 (robots.txt: noindex) — URL 공유로만 접근 |
| 목적 | 개인 포트폴리오 + 실무 아카이브 + 기사 스크랩 창고 |

### 페이지 구조
| 경로 | 내용 |
|------|------|
| `/` | 최신 리포트 요약 + Direction 히스토리 |
| `/reports` | 주차별 아카이브 목록 |
| `/reports/[date]` | 4-Panel 전체 + 원본 기사 링크 |
| `/articles/[date]` | 기사 스크랩 창고 (패널 탭 + 키워드검색 + 링크복사) |
| `/about` | 소개 페이지 |
| `/rss.xml` | RSS 피드 → NotebookLM 소스 URL |

### 데이터 연동 방식
```
newsletter_bot.py 실행
  → data/reports/YYYY-MM-DD.json 생성 (hr-newsletter-automation 커밋)
  → [추가 예정] GitHub API로 hr-intelligence-lab/public/data/에도 동기화
  → Vercel 자동 재빌드
```

### 미결: Phase 2 웹 방식 결정 필요
**레퍼런스:** https://github.com/kipeum86/web-content-designer

아직 결정 안 됨 — 두 가지 후보:

**Option A — Next.js + Vercel (원래 계획)**
- 별도 레포 `hr-intelligence-lab` 신규 생성
- Next.js 14 App Router + Tailwind + Recharts
- JSON 데이터 fetch → 동적 페이지 렌더링

**Option B — 자체 완결 HTML (web-content-designer 방식)**
- `newsletter_bot.py`가 매주 리포트 HTML 직접 생성
- `data/reports/YYYY-MM-DD.html` 저장 → GitHub 커밋
- GitHub Pages로 서빙 (`lucasung-debug.github.io/hr-newsletter-automation/...`)
- 별도 레포·서버 불필요, 구현 단순

**다음 세션에서 결정 후 진행**

---

## NotebookLM 연동 정리 (2026-03-06 확정)

### 역할 정의
- NotebookLM은 **자동화 파이프라인의 입력이 아닌 출력 저장소**
- Gemini API가 뉴스를 직접 분석 → 결과를 NotebookLM에 저장 (읽기·탐색용)
- NotebookLM 공개 API 없음 → 코드로 자동 연결 불가

### 즉시 연결 방법 (Phase 2 전에도 가능)
- 레포가 **public** → GitHub raw URL 직접 사용 가능
- `newsletter_bot.py`에 `data/reports/latest.md` 생성 기능 추가 예정
- NotebookLM 소스 URL: `https://raw.githubusercontent.com/lucasung-debug/hr-newsletter-automation/main/data/reports/latest.md`
- 매주 실행 시 `latest.md` 덮어쓰기 → NotebookLM에서 수동 새로고침

### 실제 활용 방식
| 역할 | 가능 여부 |
|------|----------|
| Gemini 분석의 입력 소스 | ❌ API 없음 |
| 수집 기사 개인 탐색/질문 | ✅ raw URL 소스로 |
| 생성된 리포트 누적 보관 | ✅ latest.md or RSS |
| "이번 주 패턴 찾아줘" 수동 질문 | ✅ NotebookLM UI |

---

## 전체 로드맵

```
Phase 1: 4-Panel 구조 + 주간 수집/발송 + BCG 품질 기준 적용 ✅ 완료
Phase 2: 웹 대시보드 (Option A: Next.js/Vercel OR Option B: HTML/GitHub Pages) — 미결
Phase 3: Signal 트렌드 차트 + 산업 프로파일 확장 + NotebookLM RSS 연동
```

---

## 다음 세션 시작 시 해야 할 것

1. **Phase 2 방식 최종 결정** — Option A (Next.js) vs Option B (HTML/GitHub Pages)
2. **`latest.md` 생성 기능 추가** — NotebookLM 즉시 연결 준비
3. **공공기관 RSS URL 동작 확인** — 고용노동부, 안전보건공단
4. **첫 수요일 발송 결과 검토** — 품질 게이트 임계값 조정

---

## 기술적 제약 및 기준

- HTML 이메일: 인라인 스타일만 (Gmail은 외부 CSS/JS 차단)
- Gemini 재시도: 실패 시 간소화 프롬프트 → 스마트 폴백
- 환경변수: 코드에 직접 작성 금지 (`os.environ.get()` 필수)
- RSS: 공공기관만 명시, 상업 언론은 Naver 검색으로
- 추정 수치: "(추정)" 명시 필수, 뉴스에 없는 사실 생성 금지

---

_최종 업데이트: 2026-03-06 (Phase 1 완료 + Phase 2 계획 논의 완료)_
