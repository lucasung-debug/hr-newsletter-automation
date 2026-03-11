# 코드 개선 검증 계획 (Panel A/B/C/D 정상성 + Panel E 신설)

**브랜치:** `claude/api-stability-cVIha`
**커밋:** Sprint 1 & Sprint 3 — Naver API 안정성 + Panel E (AI 업무활용) 신설
**검증 일자:** 2026-03-11 (다음 주 수요일 실행)

---

## 1️⃣ Panel A 검증 — 국제 MACRO (글로벌 정치·경제·원자재)

### 수집 단계
```
✓ Naver 뉴스 API 호출 성공 (timeout=30초)
✓ 기사 건수: [뉴스레터 로그] "Panel A: N건 fetched" 확인
✓ 에러 로깅: HTTP 상태 코드 (429/403/500) 구분 기록 여부
```

### 필터 단계
```
✓ 관련도 필터 후 기사 수: [로그] "Panel A: N건" (감소 확인)
✓ 관련도 키워드: 글로벌, 국제, 환율, 원자재, 수출, 관세 등
```

### AI 분석
```
✓ 분석 완료: [로그] "PANEL_A 분석 완료: M건" (M ≤ 3)
✓ 신호강도: High/Medium/Low 분포
✓ 폴백 여부: a_is_fallback=False (정상 분석 시)
```

### 이메일 렌더링
```
✓ Panel A 카드 표시: "국제 MACRO — 글로벌 정치·경제·원자재"
✓ 색상: 딥블루 #1d4ed8
✓ 기사별 6단계 분석 카드 (signal_strength, fact, so_what, business_impact 등)
✓ "원문 확인이 필요합니다" 폴백 문구 없음
```

---

## 2️⃣ Panel B 검증 — 한국 MICRO (경제·노동·산업규제) ⚠️ Priority

**배경:** 2026-03-11 발송본에서 fallback 콘텐츠 다수 발견.
**목표:** Panel B가 매주 정상 AI 분석 결과를 제공하도록 보장.

### 수집 단계
```
✓ Naver API: [로그] "Panel B: N건 fetched" (이전: 불명)
✓ RSS 피드 (고용노동부, 안전보건공단): [로그] "RSS 수집" 건수 확인
✓ 합계: Panel B 총 수집 건수 = Naver + RSS
✓ 에러 로그: 429 rate limit 여부, 403 인증 실패 여부
```

### 필터 단계
```
✓ 관련도 필터 후: [로그] "Panel B: N건" (충분한 기사 존재 확인)
✓ 최소 기사 수: 0건 이상 (0건이면 analyze_panel() 호출 안 됨 → fallback 트리거)
```

### AI 분석 (⭐ 핵심)
```
✓ 분석 완료 로그: "PANEL_B 분석 완료: M건"
  또는
  ⚠️ "스마트 폴백 (PANEL_B)" 메시지 출력 시 → root cause 확인 필요

✓ 가능한 원인 (로그에서 확인):
  1. "Gemini 429 rate limit" — Panel A 이후 8초는 부족, rate limit 재발생
  2. "필터 후: Panel B 0건" — 관련도 필터가 너무 엄격
  3. "GEMINI_DEEP_MODEL" — 모델명 불일치 (워크플로우 vs 코드)
```

### 이메일 렌더링
```
✓ Panel B 카드 표시: "한국 MICRO — 경제·노동·산업규제"
✓ 색상: 딥그린 #15803d
✓ 기사별 정상 6단계 분석 (NO "원문 확인이 필요합니다" 문구)
```

**Panel B 통과 기준:**
- b_is_fallback = False (로그 확인)
- 이메일에서 "원문 확인이 필요합니다" 없음

---

## 3️⃣ Panel C 검증 — 산업·회사 (경쟁사·HR·수출·ESG)

### 수집 ~ AI 분석
```
✓ 수집 → 필터 → AI 분석 정상 진행
✓ c_is_fallback = False
✓ 로그: "PANEL_C 분석 완료: M건"
```

### 이메일
```
✓ Panel C 카드 표시
✓ 색상: 주황 #c2410c
✓ 정상 분석 콘텐츠 (NO 폴백)
```

---

## 4️⃣ Panel D 검증 — 비즈니스 리포트 (3축 통합 전략)

**핵심:** Panel D는 Panel A/B/C 데이터만 사용. Panel E 추가되어도 영향 없음.

### 생성 조건
```
✓ Panel A/B/C 총 기사 수 ≥ 3건 → generate_business_report() 호출
✓ 10초 대기 후 Gemini 호출
```

### 리포트 구조
```
✓ BLUF (Bottom Line Up Front): 3문장
✓ Direction: Converging / Diverging / Ambiguous
✓ Causal Narrative: A→B→C 3층 인과
✓ Key Variable: 핵심 변수명
✓ Risks: 최대 3개 (likelihood/impact: High/Medium)
✓ Decision Point: 기한 + 미결 시 리스크
✓ Watch List: 모니터링 지표 2~3개
```

### 이메일
```
✓ Panel D 헤더: "비즈니스 리포트 / 3축 통합 전략"
✓ 색상: 보라 #7c3aed
✓ BLUF 항목 리스트 렌더링
✓ Direction 배지 표시
✓ Risks 테이블 (3열)
✓ Watch List 태그 표시
```

---

## 5️⃣ Panel E 검증 (신규) — AI & 업무혁신

### 수집 단계
```
✓ Panel E 키워드: 생성형AI, ChatGPT, HR 디지털, AI 자동화 등
✓ [로그] "Panel E: N건 fetched" 출력
```

### 필터 단계
```
✓ 관련도 필터: AI, 업무자동화, HR-Tech, 생산성 용어 매칭
✓ [로그] "필터 후: Panel E N건"
```

### AI 분석
```
✓ Step 6-B 실행: Panel C 이후 8초 대기
✓ [로그] "PANEL_E 분석 완료: M건"
✓ e_is_fallback = False (정상 시)
✓ 분석 스키마: signal_strength, fact, so_what, business_impact 등
  ("so_what": "오뚜기라면 경영지원/HR 실무에 어떻게 적용 가능한가?")
```

### HTML 렌더링
```
✓ Panel E 카드 헤더: "PANEL E — AI & 업무혁신 / 생성형AI, HR-Tech, 업무자동화"
✓ 색상: 청록 #0e7490
✓ 위치: Panel C ↔ Panel D 사이 (실무 연결성 유지)
✓ 기사 카드: 6단계 분석 정상 표시
```

---

## 6️⃣ 종합 검증 체크리스트

### 로그 검증
```
[Newsletter Summary]
  Panel A: X fetched → X in newsletter (fallback=False)
  Panel B: Y fetched → Y in newsletter (fallback=False)  ⭐
  Panel C: Z fetched → Z in newsletter (fallback=False)
  Panel E: W fetched → W in newsletter (fallback=False)  ⭐
  Business report: 생성됨
  Edition: full
  Warnings: none 또는 [경고 내용]
```

### 이메일 렌더링
```
1. 헤더: WEEKLY HR STRATEGIC INTELLIGENCE (또는 Light edition)
2. Panel A: 딥블루 헤더 + 기사 카드 (폴백 없음)
3. Panel B: 딥그린 헤더 + 기사 카드 (폴백 없음) ⭐
4. Panel C: 주황 헤더 + 기사 카드 (폴백 없음)
5. Panel E: 청록 헤더 + 기사 카드 (폴백 없음) ⭐
6. Panel D: 보라 헤더 + BLUF/Direction/Narrative/Risks/Watch List
7. 회사 소식: [회신 또는 신제품 뉴스]
8. 푸터: 고지문
```

### 에러 시나리오
```
❌ Panel B fallback 발생 시:
   → [로그] "스마트 폴백 (PANEL_B)" 메시지에서 원인 확인
   → GitHub Actions 실시간 로그에서 "Gemini 429" / "HTTP 4xx" / "필터 후 Panel B 0건" 확인
   → 해당 원인에 맞는 Sprint 1-A/1-B/1-C 개선 적용

❌ Panel E 렌더링 실패:
   → 색상 코드 또는 헤더 HTML 확인
   → JSON 저장 panel_e 필드 확인
```

---

## 실행 절차

### 1. GitHub Actions 수동 실행 (2026-03-12 ~ 2026-03-13)
```bash
# GitHub UI: Actions → main.yml → "Run workflow" (Manual dispatch)
# 또는 CLI (로컬):
gh workflow run main.yml -f "mode=newsletter"
```

### 2. 로그 검토
```
GitHub Actions: [Logs] 탭에서 다음 검색:
- "Panel B" — B 수집/필터/분석 단계 추적
- "429" — rate limit 여부 확인
- "분석 완료" — 4개 패널 모두 완료 확인
- "Newsletter Summary" — 최종 요약 로그
```

### 3. 이메일 확인
**수신 확인:** `tjdaudwo21@otokirm.com` (또는 RECIPIENT_EMAILS)

**검증 항목:**
- [ ] Panel A 정상 분석 (색상 blue, 기사 카드 3개 이하)
- [ ] Panel B 정상 분석 (색상 green, "원문 확인" 문구 없음) ⭐
- [ ] Panel C 정상 분석 (색상 orange, 기사 카드)
- [ ] Panel E 신규 패널 (색상 teal, 기사 카드) ⭐
- [ ] Panel D 리포트 정상 (BLUF/Direction/Narrative/Risks)
- [ ] 회사 소식 섹션
- [ ] 폴백 문구 ("원문 확인이 필요합니다") 없음

---

## 검증 통과 기준

✅ **통과:**
- Panel A/B/C/D 모두 fallback=False
- Panel E 신규 패널 포함, fallback=False
- 이메일 렌더링: 5개 패널 정상 표시
- 로그: Gemini 429/403 에러 없음 (또는 재시도 후 성공)
- Quality Gate: Edition = "full" (경고 없음)

❌ **실패:**
- Panel B fallback 재발생 → Sprint 1-A/1-B 개선 재검토
- Panel E 렌더링 오류 → HTML 코드 확인
- Rate limit 반복 → 패널 간 딜레이 연장 고려

---

## 다음 단계 (Phase 1.2+)

1. **Panel B 안정성 모니터링** — 향후 4주 로그 기록
2. **Sprint 2 (안정성 강화)** — 이메일 발송 예외처리, IMAP 타임아웃 추가
3. **Panel E 성숙도 향상** — AI 기술 실무 적용 패턴 반복 학습
4. **웹 대시보드** (Phase 2) — 5-Panel 데이터 시각화

---

_검증 계획: 2026-03-11 작성_
_대상: 경영지원팀, C-Level, 부서장 (뉴스레터 독자)_
