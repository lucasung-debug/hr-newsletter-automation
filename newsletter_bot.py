import requests
import json
import datetime
import smtplib
import imaplib
import email as email_lib
import os
import re
import time
import logging
from email.utils import parsedate_to_datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ============================================================
# 로깅 설정
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("hr_brief")

# ============================================================
# 회사 컨텍스트 (전역 상수)
# ============================================================
COMPANY_CONTEXT = """오뚜기라면(OTOKI RAMYON) — 식품제조업
- 제품: 라면, 프리믹스류
- 수출시장: 베트남, 미국
- 모회사: OTOKI 오뚜기
- 근무형태: 2조 2교대 (주야간 교대근무)
- HR 이슈: 주52시간제, 임금피크제, 교대근무 관리, 윤리경영/ESG, 산업안전"""

SENDER_EMAIL = "proposition97@gmail.com"

# ============================================================
# 1. 유틸리티 함수
# ============================================================
def clean_html(raw_html):
    return re.sub(r'<.*?>|&quot;|&apos;|&gt;|&lt;|&amp;', '', raw_html).strip()


def extract_json_from_text(text):
    """AI 응답에서 JSON 추출 — markdown fence 제거 + brace-depth counting."""
    try:
        text = re.sub(r'```(?:json)?\s*', '', text).strip()
        # 직접 파싱 시도
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # brace-depth 방식으로 outermost {} 추출
        depth = 0
        start = None
        for i, ch in enumerate(text):
            if ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start is not None:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        start = None
        return None
    except Exception:
        return None


def _title_words(title):
    """제목에서 2글자 이상 단어 추출 (한글+영문+숫자). 따옴표/특수문자 제거."""
    title = re.sub(r'["\'\u201c\u201d\u2018\u2019\u300c\u300d\u3010\u3011\[\]()…·]', ' ', title)
    stopwords = set("은는이가을를의에서도로와과한다된로써까지만부터")
    words = set(re.findall(r'[가-힣A-Za-z0-9]{2,}', title))
    return {w for w in words if w not in stopwords}


def is_near_duplicate(new_title, seen_titles, threshold=0.4):
    """제목 단어 40% 이상 겹치면 중복 판정."""
    new_words = _title_words(new_title)
    if not new_words:
        return False
    for seen_t in seen_titles:
        seen_words = _title_words(seen_t)
        if not seen_words:
            continue
        overlap = len(new_words & seen_words)
        similarity = overlap / min(len(new_words), len(seen_words))
        if similarity > threshold:
            return True
    return False


# ============================================================
# 2. Gemini API 호출 (재시도 + 튜플 반환)
# ============================================================
def call_gemini(api_key, prompt, max_retries=3):
    """Gemini API 호출. 성공 시 (텍스트, None), 실패 시 (None, 에러유형)."""
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    last_error = "unknown"
    for attempt in range(max_retries):
        try:
            res = requests.post(
                api_url,
                headers={'Content-Type': 'application/json'},
                data=json.dumps({
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.2,
                        "maxOutputTokens": 4096
                    }
                }),
                timeout=90
            )
            if res.status_code == 429:
                wait = 15 * (attempt + 1)
                logger.warning(f"Gemini 429 rate limit (시도 {attempt + 1}), {wait}초 대기...")
                time.sleep(wait)
                last_error = "rate_limit"
                continue
            if res.status_code != 200:
                logger.error(f"Gemini HTTP {res.status_code} (시도 {attempt + 1}): {res.text[:300]}")
                last_error = f"http_{res.status_code}"
                time.sleep(5 * (attempt + 1))
                continue
            body = res.json()
            candidates = body.get('candidates')
            if not candidates:
                block_reason = body.get('promptFeedback', {}).get('blockReason', '')
                if block_reason:
                    logger.error(f"Gemini 차단: {block_reason}")
                    last_error = f"blocked_{block_reason}"
                else:
                    logger.warning(f"Gemini candidates 없음 (시도 {attempt + 1})")
                    last_error = "no_candidates"
                time.sleep(5)
                continue
            return candidates[0]['content']['parts'][0]['text'], None
        except requests.exceptions.Timeout:
            logger.error(f"Gemini 타임아웃 (시도 {attempt + 1})")
            last_error = "timeout"
        except Exception as e:
            logger.error(f"Gemini 오류 (시도 {attempt + 1}): {e}")
            last_error = str(e)
        time.sleep(5 * (attempt + 1))
    return None, last_error


# ============================================================
# 3. 고정 키워드 (복합 검색어로 정밀도 향상)
# ============================================================
KEYWORDS = {
    "MACRO": [
        "식품제조업 원가 원자재",
        "라면 밀가루 팜유 가격",
        "식품 수출 관세 규제",
        "원달러 환율 식품",
        "소비자물가 식료품",
        "글로벌 식품기업 실적",
        "식품산업 트렌드 전망",
    ],
    "HR": [
        "제조업 주52시간 교대근무",
        "식품제조 산업안전 중대재해",
        "제조업 임금 인상 최저임금",
        "고용노동부 제조업 근로감독",
        "교대근무 야간근로 수당",
        "제조업 인력난 외국인 근로자",
        "근로기준법 개정 제조업",
    ],
}


# ============================================================
# 4. 관련도 사전 필터링
# ============================================================
RELEVANCE_TERMS = {
    "MACRO": {
        "식품", "라면", "면류", "프리믹스", "원자재", "밀가루", "팜유", "대두",
        "원가", "수출", "관세", "환율", "물가", "소비자", "식료품", "제조",
        "글로벌", "무역", "공급망", "인플레이션", "GDP", "경제성장",
        "오뚜기", "농심", "삼양", "풀무원", "CJ", "식품업",
    },
    "HR": {
        "근로", "노동", "임금", "교대", "주52시간", "산업안전", "중대재해",
        "고용", "해고", "퇴직", "인사", "제조업", "공장", "생산직",
        "야간", "수당", "최저임금", "임금피크", "정년", "노조", "단체교섭",
        "근로기준법", "고용노동부", "근로감독", "외국인근로자", "인력난",
    },
}


def compute_relevance_score(article, category):
    """제목+설명에서 관련 단어 출현 횟수 기반 0.0~1.0 점수."""
    text = (article['title'] + " " + article['desc'])
    terms = RELEVANCE_TERMS.get(category, set())
    if not terms:
        return 0.5
    hits = sum(1 for t in terms if t in text)
    return min(hits / 3.0, 1.0)


def filter_by_relevance(news_list, category, min_score=0.3):
    """최소 점수 미만 기사 제거. 점수 내림차순 정렬."""
    scored = [(n, compute_relevance_score(n, category)) for n in news_list]
    filtered = [(n, s) for n, s in scored if s >= min_score]
    filtered.sort(key=lambda x: x[1], reverse=True)
    removed = len(news_list) - len(filtered)
    if removed:
        logger.info(f"  관련도 필터: {category} {removed}건 제거 (총 {len(filtered)}건 유지)")
    return [n for n, s in filtered]


def dedup_across_categories(macro_news, hr_news):
    """HR 뉴스에서 MACRO와 중복되는 기사 제거. MACRO 우선."""
    macro_titles = [n['title'] for n in macro_news]
    deduped_hr = [n for n in hr_news if not is_near_duplicate(n['title'], macro_titles)]
    removed = len(hr_news) - len(deduped_hr)
    if removed:
        logger.info(f"  교차 카테고리 중복 제거: {removed}건 (HR에서 제거)")
    return macro_news, deduped_hr


# ============================================================
# 5. 뉴스 수집 (Naver API)
# ============================================================
def fetch_news(category, keywords):
    """Naver 뉴스 검색 API로 뉴스 수집. 중복 제거 포함."""
    client_id = os.environ.get('NAVER_CLIENT_ID')
    client_secret = os.environ.get('NAVER_CLIENT_SECRET')
    if not client_id or not client_secret:
        logger.warning(f"Naver API 키 미설정 ({category})")
        return []

    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
    collected = []
    seen = set()
    now = datetime.datetime.now(datetime.timezone.utc)
    limit = now - datetime.timedelta(days=2)

    for kw in keywords:
        try:
            resp = requests.get(url, headers=headers,
                                params={"query": kw, "display": 5, "sort": "date"},
                                timeout=10)
            if resp.status_code != 200:
                continue
            for item in resp.json().get('items', []):
                try:
                    pd = parsedate_to_datetime(item['pubDate'])
                    if pd < limit:
                        continue
                    t = clean_html(item['title'])
                    if is_near_duplicate(t, seen):
                        continue
                    collected.append({
                        "title": t,
                        "link": item.get('originallink') or item['link'],
                        "desc": clean_html(item['description']),
                        "date": pd.strftime("%Y-%m-%d")
                    })
                    seen.add(t)
                except Exception:
                    continue
        except Exception:
            continue

    return sorted(collected, key=lambda x: x['date'], reverse=True)[:5]


# ============================================================
# 6. AI 뉴스 분석 (4단계 전략 브리핑 — 파트별 분할 호출)
# ============================================================
def analyze_part(api_key, news_list, part_type):
    """단일 파트(MACRO 또는 HR)의 뉴스를 Gemini로 4단계 분석.

    part_type: "MACRO" 또는 "HR"
    반환: (분석된 기사 리스트, error_type 또는 None)
    """
    if not news_list:
        return [], None

    ctx = ""
    for i, n in enumerate(news_list):
        ctx += f"[{i}] {n['title']} | {n['desc']}\n"

    if part_type == "MACRO":
        part_desc = "거시경제·글로벌 식품시장"
        selection_rule = "거시경제 환경, 글로벌 식품·원자재 시장 트렌드, 수출 규제 변화 등 식품제조기업 경영에 영향을 주는 뉴스만 선정하세요. 특정 기업의 신제품·마케팅·CSR 뉴스는 제외하세요."
    else:
        part_desc = "인사노무·컴플라이언스"
        selection_rule = "근로시간(주52시간), 교대근무, 임금피크제, 산업안전, 고용정책 등 식품제조업 HR에 직접 영향을 주는 뉴스만 선정하세요. 식품제조업과 무관한 업종(병원, IT, 서비스업, 지자체, 반려동물, 부동산)의 기사는 반드시 제외하세요."

    prompt = f"""당신은 오뚜기라면(OTOKI RAMYON) 인사팀 소속 HR 전략 애널리스트입니다.

[독자] 과장·팀장급 이상 고참 관리자 (의사결정권자)
[톤] 보고서 형식, 경어체, 수식어 배제, 숫자·데이터·의사결정 포인트 중심

[회사 컨텍스트]
{COMPANY_CONTEXT}

아래 [{part_desc}] 뉴스 후보에서 **1~3개**를 선정하여 전략 브리핑을 작성하세요.

[선정 기준]
{selection_rule}
- 관련 뉴스가 없으면 빈 배열 []을 반환하세요. 무관한 기사를 억지로 포함하지 마세요.
- 품질 우선: 1개라도 좋은 분석이 3개의 얕은 분석보다 낫습니다.

[분석 4단계]
- fact: 핵심 사실 요약 (2~3문장)
- strategic_meaning: 전략적 의미 (이 뉴스가 왜 중요한지)
- business_impact: 오뚜기라면 관점의 사업 영향 (식품제조, 교대근무, 수출 관점)
- recommended_actions: 즉시 검토 가능한 실행항목 2~3개 (측정지표 포함)

[중요 규칙]
1. 반드시 아래 JSON 형식만 출력하세요. 다른 텍스트, 설명, 마크다운은 절대 포함하지 마세요.
2. 관련 뉴스가 없으면 정확히 {{"articles": []}} 만 출력하세요.
3. ref_id는 반드시 정수여야 합니다.
4. 각 분석 항목(fact, strategic_meaning, business_impact)은 반드시 2문장 이상이어야 합니다.

{{"articles": [{{"headline": "...", "fact": "...", "strategic_meaning": "...", "business_impact": "...", "recommended_actions": ["...", "..."], "ref_id": 0}}]}}

뉴스 후보:
{ctx}"""

    label = "MACRO" if part_type == "MACRO" else "HR"
    logger.info(f"AI 분석 중 ({label})...")
    raw, err = call_gemini(api_key, prompt)
    if not raw:
        logger.error(f"Gemini 응답 없음 (analyze_{label}): {err}")
        return [], err

    parsed = extract_json_from_text(raw)
    if not parsed or not isinstance(parsed.get('articles'), list):
        logger.error(f"JSON 구조 불일치 ({label}) — raw 앞 300자: {raw[:300]}")
        return [], "json_parse_error"

    result = []
    for item in parsed['articles']:
        ref_id = item.get('ref_id')
        if isinstance(ref_id, str):
            ref_id = int(ref_id) if ref_id.isdigit() else -1
        if isinstance(ref_id, int) and 0 <= ref_id < len(news_list):
            n = news_list[ref_id]
            item.update({'link': n['link'], 'date': n['date']})
            result.append(item)

    logger.info(f"{label} 분석 완료: {len(result)}건")
    return result, None


# ============================================================
# 7. 스마트 폴백 (AI 실패 시 관련도 기반 필터링)
# ============================================================
def make_smart_fallback(news_list, category, error_type=None):
    """AI 실패 시 3단계 폴백.

    Tier 1: 높은 관련도(0.6) 기사만 최대 2개 포함 (안내 메시지 포함)
    Tier 2: 관련 기사 없으면 빈 리스트 → HTML에서 "뉴스 없음" 표시

    반환: (articles_list, is_fallback: bool)
    """
    if not news_list:
        return [], True

    # Tier 1: 높은 관련도 기준으로 재필터링
    high_relevance = filter_by_relevance(news_list, category, min_score=0.6)

    if high_relevance:
        result = []
        for n in high_relevance[:2]:
            result.append({
                "headline": n['title'],
                "fact": n['desc'],
                "strategic_meaning": "AI 분석이 일시적으로 제공되지 않았습니다. 아래는 관련도가 높은 기사의 원문 요약입니다.",
                "business_impact": "원문 기사를 통해 자체 영향도를 평가하시기 바랍니다.",
                "recommended_actions": ["원문 기사 확인 후 관련 부서 공유"],
                "link": n['link'],
                "date": n['date']
            })
        logger.info(f"스마트 폴백 ({category}): Tier 1 — {len(result)}건 (관련도 0.6 이상)")
        return result, True

    # Tier 2: 관련 기사 없음
    logger.info(f"스마트 폴백 ({category}): Tier 2 — 관련 기사 없음, 빈 리스트 반환")
    return [], True


# ============================================================
# 8. AI 심층 리포트 (PART 3)
# ============================================================
def generate_deep_report(api_key, all_news_ctx):
    """BCG/골드만삭스 수준의 전략 심층 분석 아티클 생성."""
    prompt = f"""당신은 BCG, 골드만삭스, 맥킨지 수준의 시니어 전략 컨설턴트입니다.

[회사 컨텍스트]
{COMPANY_CONTEXT}

아래 거시경제·식품산업·노동시장 뉴스 데이터를 종합 분석하여,
**노동시장 × 대한민국 식품시장 × 세계 식품시장**을 관통하는
하나의 핵심 주제를 도출하고 심층 분석 아티클을 작성하세요.

[작성 규칙]
- 구조: 도입(이슈 제기, 핵심 논점 2~3문장) → 본론(글로벌 벤치마크 사례, 산업 데이터, 메가트렌드를 인용한 분석 3~4단락) → 시사점(오뚜기라면의 식품제조·교대근무·수출 관점에서의 전략적 제언)
- 분량: 1000~1500자
- 톤: BCG/골드만삭스 전략 리포트 (수식어 배제, 데이터·논리·구조적 사고 중심)
- 단일 HR 이슈가 아닌, 거시경제와 노동시장·식품산업이 교차하는 구조적 인사이트 도출
- 글로벌 사례(미국, 유럽, 일본, 동남아 등)와 국내 현실을 대비하여 분석
- 단락 구분은 \\n\\n 으로 처리

반드시 아래 JSON만 출력하세요. 다른 텍스트는 절대 포함하지 마세요.
{{"topic": "아티클 제목", "content": "본문 텍스트"}}

뉴스 데이터 (거시경제 + 인사노무 통합):
{all_news_ctx}"""

    logger.info("AI 심층 리포트 생성 중...")
    raw, err = call_gemini(api_key, prompt)
    if raw:
        parsed = extract_json_from_text(raw)
        if parsed and parsed.get('topic') and parsed.get('content'):
            logger.info(f"리포트 생성 완료: {parsed['topic']}")
            return parsed
        logger.error(f"리포트 JSON 파싱 실패 — raw 앞 300자: {raw[:300]}")
    else:
        logger.error(f"Gemini 응답 없음 (generate_deep_report): {err}")
    return None


# ============================================================
# 9. 품질 게이트 + 관리자 알림
# ============================================================
def quality_gate(final_p1, final_p2, deep_report, p1_is_fallback, p2_is_fallback):
    """발송 전 품질 검증. (should_send, edition_type, warnings) 반환."""
    warnings = []

    has_real_p1 = bool(final_p1) and not p1_is_fallback
    has_real_p2 = bool(final_p2) and not p2_is_fallback
    has_report = bool(deep_report)

    real_sections = sum([has_real_p1, has_real_p2, has_report])

    if real_sections >= 2:
        return True, "full", warnings

    if real_sections == 1:
        warnings.append("WARNING: AI 분석 3개 섹션 중 1개만 성공")
        return True, "full", warnings

    # real_sections == 0
    if final_p1 or final_p2:
        warnings.append("CRITICAL: AI 분석 전면 실패. Light 에디션으로 발송합니다.")
        return True, "light", warnings

    warnings.append("CRITICAL: 콘텐츠 없음. 발송 중단.")
    return False, "skip", warnings


def send_admin_alert(app_password, warnings):
    """품질 경고 시 관리자에게 알림 메일 발송."""
    body = "HR Newsletter Quality Gate Warnings:\n\n" + "\n".join(warnings)
    body += f"\n\nTimestamp: {datetime.datetime.now().isoformat()}"

    msg = MIMEMultipart()
    msg['From'] = f"HR Brief Bot <{SENDER_EMAIL}>"
    msg['To'] = SENDER_EMAIL
    msg['Subject'] = f"[ALERT] Newsletter Quality Issue - {datetime.datetime.now().strftime('%Y-%m-%d')}"
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER_EMAIL, app_password)
            server.sendmail(SENDER_EMAIL, SENDER_EMAIL, msg.as_string())
        logger.info("관리자 알림 발송 완료")
    except Exception as e:
        logger.error(f"관리자 알림 발송 실패: {e}")


# ============================================================
# 10. 회사 소식 (IMAP 회신 확인 / 토요일 요청)
# ============================================================
def send_news_request_email(app_password):
    """토요일: 회사 소식 요청 메일을 개인메일로 발송."""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    subject = f"[회사소식요청] {today}"
    body = f"""안녕하세요, 성명재입니다.

이번 주 오뚜기라면 회사 소식이 있다면 이 메일에 회신해주세요.
(신제품 출시, 조직 변경, 이벤트, 수상 등)

회신이 없을 경우 오뚜기 신제품 관련 뉴스로 자동 대체됩니다.

---
Daily HR Strategic Brief 자동 발송 시스템
"""
    msg = MIMEMultipart()
    msg['From'] = f"HR Brief Bot <{SENDER_EMAIL}>"
    msg['To'] = SENDER_EMAIL
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, app_password)
        server.sendmail(SENDER_EMAIL, SENDER_EMAIL, msg.as_string())
    logger.info(f"토요일 회사소식 요청 메일 발송 완료: {subject}")


def check_company_news_reply(app_password):
    """IMAP으로 [회사소식요청]에 대한 회신 확인. 있으면 본문 반환, 없으면 None."""
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(SENDER_EMAIL, app_password)
        mail.select("INBOX")

        # 최근 7일 내 회신 검색
        since_date = (datetime.datetime.now() - datetime.timedelta(days=7)).strftime("%d-%b-%Y")
        _, data = mail.search(None, f'(SINCE "{since_date}" SUBJECT "Re: [회사소식요청]")')

        if not data[0]:
            mail.logout()
            return None

        # 가장 최근 메일
        msg_ids = data[0].split()
        _, msg_data = mail.fetch(msg_ids[-1], "(RFC822)")
        raw_email = msg_data[0][1]
        msg = email_lib.message_from_bytes(raw_email)

        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    charset = part.get_content_charset() or 'utf-8'
                    body = part.get_payload(decode=True).decode(charset, errors='replace')
                    break
        else:
            charset = msg.get_content_charset() or 'utf-8'
            body = msg.get_payload(decode=True).decode(charset, errors='replace')

        mail.logout()

        # 회신 본문에서 인용 부분 제거 (> 로 시작하는 줄, -- 이후)
        lines = []
        for line in body.split('\n'):
            if line.strip().startswith('>') or line.strip() == '--':
                break
            lines.append(line)
        clean_body = '\n'.join(lines).strip()

        if len(clean_body) > 10:
            return clean_body
        return None
    except Exception as e:
        logger.error(f"IMAP 확인 실패: {e}")
        return None


def fetch_company_fallback_news():
    """회신 없을 때: 오뚜기 신제품 뉴스 검색."""
    client_id = os.environ.get('NAVER_CLIENT_ID')
    client_secret = os.environ.get('NAVER_CLIENT_SECRET')
    if not client_id or not client_secret:
        return []

    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
    results = []
    for kw in ["오뚜기 신제품", "오뚜기라면 신제품", "오뚜기 출시"]:
        try:
            resp = requests.get(url, headers=headers,
                                params={"query": kw, "display": 5, "sort": "date"},
                                timeout=10)
            if resp.status_code == 200:
                for item in resp.json().get('items', []):
                    t = clean_html(item['title'])
                    if "오뚜기" not in t:
                        continue
                    if not is_near_duplicate(t, {r['title'] for r in results}):
                        results.append({
                            "title": t,
                            "link": item.get('originallink') or item['link'],
                            "desc": clean_html(item['description']),
                        })
        except Exception:
            continue
    return results[:3]


# ============================================================
# 11. HTML 생성 (미니멀 리포트 스타일)
# ============================================================
def build_html(today, final_p1, final_p2, deep_report, company_section_html):
    """텍스트 중심 미니멀 리포트 HTML 생성."""

    def mk_article(item):
        actions_html = ""
        for a in item.get('recommended_actions', []):
            actions_html += f'<div style="margin-bottom:4px;">&#8226; {a}</div>'

        return f"""
        <div style="margin-bottom:28px;">
            <div style="font-size:11px;color:#999;margin-bottom:4px;">{item.get('date', '')}</div>
            <h3 style="margin:0 0 12px 0;font-size:16px;font-weight:700;line-height:1.5;">
                <a href="{item.get('link', '#')}" target="_blank" style="text-decoration:none;color:#111;">{item['headline']}</a>
            </h3>
            <div style="margin-bottom:10px;">
                <span style="font-size:11px;font-weight:700;color:#888;letter-spacing:0.5px;">FACT</span>
                <div style="font-size:14px;color:#333;line-height:1.8;margin-top:2px;">{item.get('fact', '')}</div>
            </div>
            <div style="margin-bottom:10px;">
                <span style="font-size:11px;font-weight:700;color:#888;letter-spacing:0.5px;">STRATEGIC MEANING</span>
                <div style="font-size:14px;color:#333;line-height:1.8;margin-top:2px;">{item.get('strategic_meaning', '')}</div>
            </div>
            <div style="margin-bottom:10px;">
                <span style="font-size:11px;font-weight:700;color:#888;letter-spacing:0.5px;">BUSINESS IMPACT</span>
                <div style="font-size:14px;color:#333;line-height:1.8;margin-top:2px;">{item.get('business_impact', '')}</div>
            </div>
            <div style="background:#F5F5F5;padding:14px;border-radius:4px;">
                <span style="font-size:11px;font-weight:700;color:#888;letter-spacing:0.5px;">RECOMMENDED ACTION</span>
                <div style="font-size:13px;color:#222;line-height:1.7;margin-top:4px;">{actions_html}</div>
            </div>
        </div>
        <div style="border-bottom:1px solid #eee;margin-bottom:28px;"></div>"""

    # PART 1
    p1_html = ""
    if final_p1:
        for item in final_p1:
            p1_html += mk_article(item)
    else:
        p1_html = '<p style="color:#999;font-size:13px;">금일 주요 거시경제/식품산업 뉴스가 없습니다.</p>'

    # PART 2
    p2_html = ""
    if final_p2:
        for item in final_p2:
            p2_html += mk_article(item)
    else:
        p2_html = '<p style="color:#999;font-size:13px;">금일 주요 인사노무/컴플라이언스 뉴스가 없습니다.</p>'

    # PART 3 — 심층 리포트
    p3_html = ""
    if deep_report:
        content_paragraphs = deep_report['content'].replace('\n\n', '</p><p style="font-size:14px;color:#333;line-height:1.8;margin:0 0 16px 0;">')
        p3_html = f"""
        <h3 style="margin:0 0 16px 0;font-size:16px;font-weight:700;color:#111;line-height:1.5;">{deep_report['topic']}</h3>
        <p style="font-size:14px;color:#333;line-height:1.8;margin:0 0 16px 0;">{content_paragraphs}</p>"""
    else:
        p3_html = '<p style="color:#999;font-size:13px;">금일 심층 리포트를 생성하지 못했습니다.</p>'

    html = f"""<html><body style="font-family:'Apple SD Gothic Neo','Malgun Gothic','Noto Sans KR',sans-serif;max-width:620px;margin:0 auto;padding:24px;background:#FFF;color:#333;">

    <!-- 헤더 -->
    <div style="text-align:center;padding-bottom:20px;margin-bottom:24px;border-bottom:2px solid #111;">
        <h1 style="margin:0;font-size:20px;font-weight:800;color:#111;letter-spacing:1px;">DAILY HR STRATEGIC BRIEF</h1>
        <p style="font-size:12px;color:#888;margin:8px 0 0;">오뚜기라면 &middot; 성명재 | {today}</p>
    </div>

    <!-- PART 1 -->
    <h2 style="font-size:16px;font-weight:800;color:#111;margin:0 0 20px 0;">&#9632; PART 1. 거시경제 &amp; 식품산업</h2>
    {p1_html}

    <!-- PART 2 -->
    <div style="border-top:2px solid #111;margin:32px 0 24px;"></div>
    <h2 style="font-size:16px;font-weight:800;color:#111;margin:0 0 20px 0;">&#9632; PART 2. 인사노무 &amp; 컴플라이언스</h2>
    {p2_html}

    <!-- PART 3 -->
    <div style="border-top:2px solid #111;margin:32px 0 24px;"></div>
    <h2 style="font-size:16px;font-weight:800;color:#111;margin:0 0 20px 0;">&#9632; PART 3. HR 심층 리포트</h2>
    {p3_html}

    <!-- PART 4 -->
    <div style="border-top:2px solid #111;margin:32px 0 24px;"></div>
    <h2 style="font-size:16px;font-weight:800;color:#111;margin:0 0 20px 0;">&#9632; PART 4. 회사 소식</h2>
    {company_section_html}

    <!-- 푸터 -->
    <div style="border-top:1px solid #ddd;margin-top:40px;padding-top:16px;text-align:center;">
        <p style="font-size:11px;color:#aaa;line-height:1.6;margin:0;">
            본 브리핑은 오뚜기라면 인사팀 업무 참고를 위해<br>
            AI가 자동 생성한 전략 분석 자료입니다.<br>
            원문 기사 확인 후 의사결정에 활용하시기 바랍니다.
        </p>
    </div>

</body></html>"""

    return html


# ============================================================
# 12. 이메일 발송 (복수 수신 지원)
# ============================================================
def send_email(app_password, recipients, subject, html):
    """Gmail SMTP로 이메일 발송."""
    for recipient in recipients:
        msg = MIMEMultipart()
        msg['From'] = f"HR Brief <{SENDER_EMAIL}>"
        msg['To'] = recipient
        msg['Subject'] = subject
        msg.attach(MIMEText(html, 'html', 'utf-8'))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER_EMAIL, app_password)
            server.sendmail(SENDER_EMAIL, recipient, msg.as_string())
        logger.info(f"발송 완료: {recipient}")


# ============================================================
# 13. 메인 실행
# ============================================================
def run_newsletter():
    """월~금 뉴스레터 메인 실행."""
    api_key = os.environ.get('GEMINI_API_KEY')
    app_password = os.environ.get('GMAIL_APP_PASSWORD')
    recipient_str = os.environ.get('RECIPIENT_EMAILS', 'tjdaudwo21@otokirm.com')
    recipients = [e.strip() for e in recipient_str.split(',') if e.strip()]
    today = datetime.datetime.now().strftime("%Y년 %m월 %d일")

    # Step 1: 뉴스 수집 (고정 키워드)
    logger.info("1. 뉴스 수집 중...")
    macro_news = fetch_news("MACRO", KEYWORDS["MACRO"])
    hr_news = fetch_news("HR", KEYWORDS["HR"])
    logger.info(f"수집 완료: MACRO {len(macro_news)}건, HR {len(hr_news)}건")

    # Step 2: 관련도 필터링
    logger.info("2. 관련도 필터링...")
    macro_news = filter_by_relevance(macro_news, "MACRO")
    hr_news = filter_by_relevance(hr_news, "HR")

    # Step 3: 교차 카테고리 중복 제거
    macro_news, hr_news = dedup_across_categories(macro_news, hr_news)
    logger.info(f"필터 후: MACRO {len(macro_news)}건, HR {len(hr_news)}건")

    # Step 4: AI 분석 PART 1 (거시경제)
    logger.info("3. AI 분석 시작...")
    final_p1, p1_err = analyze_part(api_key, macro_news, "MACRO") if macro_news else ([], None)
    p1_is_fallback = False
    if not final_p1:
        final_p1, p1_is_fallback = make_smart_fallback(macro_news, "MACRO", p1_err)

    # Step 5: AI 분석 PART 2 (HR) — 3초 딜레이
    if macro_news:
        time.sleep(3)
    final_p2, p2_err = analyze_part(api_key, hr_news, "HR") if hr_news else ([], None)
    p2_is_fallback = False
    if not final_p2:
        final_p2, p2_is_fallback = make_smart_fallback(hr_news, "HR", p2_err)

    # Step 6: 심층 리포트 — 5초 딜레이
    if macro_news or hr_news:
        logger.info("Gemini rate limit 보호: 5초 대기...")
        time.sleep(5)
    all_ctx = "--- 거시경제·글로벌 식품시장 ---\n"
    for i, n in enumerate(macro_news):
        all_ctx += f"[M-{i}] {n['title']} | {n['desc']}\n"
    all_ctx += "\n--- 인사노무·컴플라이언스 ---\n"
    for i, n in enumerate(hr_news):
        all_ctx += f"[H-{i}] {n['title']} | {n['desc']}\n"
    deep_report = generate_deep_report(api_key, all_ctx) if (macro_news or hr_news) else None

    # Step 7: 품질 게이트
    logger.info("4. 품질 게이트 검증...")
    should_send, edition_type, warnings = quality_gate(
        final_p1, final_p2, deep_report, p1_is_fallback, p2_is_fallback
    )
    for w in warnings:
        logger.warning(w)

    if not should_send:
        send_admin_alert(app_password, warnings)
        logger.warning("뉴스레터 발송 중단 (품질 게이트)")
        return

    if edition_type == "light":
        send_admin_alert(app_password, warnings)

    # Step 8: 회사 소식
    logger.info("5. 회사 소식 확인 중...")
    company_reply = check_company_news_reply(app_password)
    if company_reply:
        logger.info("회신 발견 → 회사 소식 삽입")
        company_html = f'<div style="font-size:14px;color:#333;line-height:1.8;">{company_reply.replace(chr(10), "<br>")}</div>'
    else:
        logger.info("회신 없음 → 오뚜기 신제품 뉴스 검색")
        fallback_news = fetch_company_fallback_news()
        if fallback_news:
            items_html = ""
            for n in fallback_news:
                items_html += f"""<div style="margin-bottom:12px;">
                    <a href="{n['link']}" target="_blank" style="font-size:14px;color:#111;text-decoration:none;font-weight:600;">{n['title']}</a>
                    <div style="font-size:13px;color:#666;margin-top:4px;line-height:1.6;">{n['desc']}</div>
                </div>"""
            company_html = items_html
        else:
            company_html = '<p style="color:#999;font-size:13px;">금일 회사 소식이 없습니다.</p>'

    # Step 9: HTML 생성 & 발송
    logger.info("6. HTML 생성 & 발송...")
    html = build_html(today, final_p1, final_p2, deep_report, company_html)
    if edition_type == "light":
        subject = f"[{today}] Daily HR Brief (Light) - 오뚜기라면"
    else:
        subject = f"[{today}] Daily HR Strategic Brief - 오뚜기라면"
    send_email(app_password, recipients, subject, html)

    # 실행 요약 로그
    logger.info("=== Newsletter Summary ===")
    logger.info(f"  MACRO: {len(macro_news)} fetched → {len(final_p1)} in newsletter (fallback={p1_is_fallback})")
    logger.info(f"  HR: {len(hr_news)} fetched → {len(final_p2)} in newsletter (fallback={p2_is_fallback})")
    logger.info(f"  Deep report: {'생성됨' if deep_report else '실패'}")
    logger.info(f"  Edition: {edition_type}")
    logger.info(f"  Warnings: {warnings if warnings else 'none'}")
    logger.info("뉴스레터 발송 완료")


def run_weekend_request():
    """토요일: 회사 소식 요청 메일 발송."""
    app_password = os.environ.get('GMAIL_APP_PASSWORD')
    send_news_request_email(app_password)


if __name__ == "__main__":
    mode = os.environ.get('BOT_MODE', 'newsletter')
    if mode == 'weekend_request':
        run_weekend_request()
    else:
        run_newsletter()
