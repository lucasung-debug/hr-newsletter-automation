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
import feedparser
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
KST = datetime.timezone(datetime.timedelta(hours=9))

# ============================================================
# 1. 유틸리티 함수
# ============================================================
def clean_html(raw_html):
    return re.sub(r'<.*?>|&quot;|&apos;|&gt;|&lt;|&amp;', '', raw_html).strip()


def extract_json_from_text(text):
    """AI 응답에서 JSON 추출 — markdown fence 제거 + brace-depth counting."""
    try:
        text = re.sub(r'```(?:json)?\s*', '', text).strip()
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
    model = os.environ.get('GEMINI_DEEP_MODEL', 'gemini-2.0-flash')
    api_url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
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
                timeout=120
            )
            if res.status_code == 429:
                wait = 30 * (attempt + 1)
                logger.warning(f"Gemini 429 rate limit (시도 {attempt + 1}), {wait}초 대기...")
                time.sleep(wait)
                last_error = "rate_limit"
                continue
            if res.status_code != 200:
                logger.error(f"Gemini HTTP {res.status_code} (시도 {attempt + 1}): {res.text[:300]}")
                last_error = f"http_{res.status_code}"
                time.sleep(5 * (attempt + 1))
                continue
            try:
                body = res.json()
            except json.JSONDecodeError as e:
                logger.error(f"Gemini JSON 파싱 실패 (시도 {attempt + 1}): {e}")
                last_error = "json_decode_error"
                time.sleep(5 * (attempt + 1))
                continue
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
# 3. 산업 프로파일 + 4-Panel 키워드 (Phase 1)
# ============================================================
INDUSTRY_PROFILES = {
    "FOOD_MFG": {
        "PANEL_A": [
            "글로벌 원자재 가격 식품",
            "밀가루 팜유 대두 국제가격",
            "미국 관세 식품 수입 수출",
            "원달러 환율 식품 수출",
            "글로벌 식품기업 공급망",
            "베트남 미국 식품 규제 수출",
            "글로벌 인플레이션 식료품",
        ],
        "PANEL_B": [
            "고용노동부 제조업 정책",
            "최저임금 제조업 인상",
            "주52시간 교대근무 제조업",
            "중대재해처벌법 식품제조",
            "제조업 외국인근로자 인력난",
            "산업안전보건 제조업",
            "한국 경제 제조업 소비",
        ],
        "PANEL_C": [
            "오뚜기 라면 경쟁사",
            "농심 삼양 CJ 풀무원 실적",
            "라면 K-푸드 수출",
            "식품제조 ESG 윤리경영",
            "식품업 HR 채용 인력",
            "오뚜기 신제품 매출",
            "라면 시장 소비 트렌드",
        ],
        "relevance": {
            "PANEL_A": {
                "글로벌", "국제", "원자재", "밀가루", "팜유", "대두", "소맥",
                "환율", "달러", "수출", "관세", "무역", "인플레이션",
                "공급망", "물가", "식료품", "GDP", "미국", "중국", "베트남",
                "식품", "라면", "제조",
            },
            "PANEL_B": {
                "고용노동부", "근로", "노동", "임금", "교대", "주52시간",
                "산업안전", "중대재해", "최저임금", "고용", "정년",
                "노조", "단체교섭", "근로기준법", "인력", "외국인근로자",
                "제조업", "공장", "생산직", "안전보건", "근로감독",
            },
            "PANEL_C": {
                "오뚜기", "농심", "삼양", "풀무원", "CJ", "라면", "면류",
                "식품", "수출", "ESG", "윤리경영", "채용", "인사",
                "신제품", "실적", "매출", "시장", "경쟁", "프리믹스",
            },
        },
        "analyst_roles": {
            "PANEL_A": "Goldman Sachs 글로벌 리서치 애널리스트",
            "PANEL_B": "BCG Korea 시니어 컨설턴트",
            "PANEL_C": "오뚜기라면 HR 전략 애널리스트",
        },
        "panel_labels": {
            "PANEL_A": "국제 MACRO — 글로벌 정치·경제·원자재",
            "PANEL_B": "한국 MICRO — 경제·노동·산업규제",
            "PANEL_C": "산업·회사 — 경쟁사·HR·수출·ESG",
        },
        "selection_rules": {
            "PANEL_A": (
                "글로벌 원자재가격, 무역·관세 정책, 환율, 글로벌 식품기업 동향 등 오뚜기라면 "
                "원가·수출에 영향을 주는 국제 거시경제 뉴스만 선정하세요. "
                "한국 내수·특정 기업 마케팅 뉴스는 제외하세요."
            ),
            "PANEL_B": (
                "고용노동부 정책, 최저임금, 주52시간, 교대근무, 산업안전, 중대재해 등 "
                "식품제조업 HR/노무에 직접 영향을 주는 한국 내 정책·규제 뉴스만 선정하세요. "
                "IT, 서비스, 금융, 병원 등 식품제조업과 무관한 업종 기사는 제외하세요."
            ),
            "PANEL_C": (
                "오뚜기, 경쟁사(농심·삼양·CJ·풀무원), 라면 수출, 식품업 ESG·HR, 시장 트렌드 등 "
                "산업·회사 관련 뉴스만 선정하세요. "
                "거시경제나 규제 뉴스는 Panel A/B 해당이므로 제외하세요."
            ),
        },
        "rss_feeds": [
            {
                "url": "http://www.moel.go.kr/rss.do",
                "label": "고용노동부",
                "panel": "PANEL_B",
            },
            {
                "url": "https://www.kosha.or.kr/kosha/data/rss.do",
                "label": "안전보건공단",
                "panel": "PANEL_B",
            },
        ],
        "company_news_keywords": ["오뚜기 신제품", "오뚜기라면 신제품", "오뚜기 출시"],
        "company_filter_keyword": "오뚜기",
    }
}

# 현재 활성 프로파일
_profile_key = os.environ.get('INDUSTRY_PROFILE', 'FOOD_MFG')
PROFILE = INDUSTRY_PROFILES.get(_profile_key, INDUSTRY_PROFILES['FOOD_MFG'])
RELEVANCE_TERMS = PROFILE['relevance']

# 패널 색상
PANEL_COLORS = {
    "PANEL_A": "#1d4ed8",  # 딥블루
    "PANEL_B": "#15803d",  # 딥그린
    "PANEL_C": "#c2410c",  # 주황
    "PANEL_D": "#7c3aed",  # 보라
}

# 6단계 분석 스키마 (프롬프트 삽입용)
_ARTICLE_SCHEMA = (
    '{"headline":"...","signal_strength":"High|Medium|Low",'
    '"fact":"수치 포함 2~3문장","so_what":"오뚜기라면에 뭐가 달라지는가? 1문장",'
    '"business_impact":"재무·운영·인력 영향",'
    '"strategic_options":['
    '{"option":"A. 선제 대응","action":"...","tradeoff":"..."},'
    '{"option":"B. 관망","action":"...","tradeoff":"..."}],'
    '"decision_point":"○○까지 ○○ 결정. 미결 시 ○○.","ref_id":0}'
)

# Panel D 스키마 (프롬프트 삽입용)
_REPORT_SCHEMA = (
    '{"bluf":["문장1","문장2","문장3"],'
    '"direction":"Converging|Diverging|Ambiguous",'
    '"direction_reason":"1문장",'
    '"causal_narrative":"A→B→C 3층 인과 서사",'
    '"key_variable":"핵심 변수명",'
    '"risks":[{"risk":"...","likelihood":"High|Medium","impact":"High|Medium"}],'
    '"decision_point":"기한+미결 시 리스크",'
    '"watch_list":["지표1","지표2"]}'
)


# ============================================================
# 4. 관련도 사전 필터링
# ============================================================
EXCLUDE_PATTERNS = [
    "금시세", "금값", "금가격", "금 선물",
    "부동산", "아파트", "분양", "전세", "월세",
    "주식", "코스피", "코스닥", "증시", "주가",
    "암호화폐", "비트코인", "이더리움",
    "반려동물", "반려견", "반려묘",
    "연예", "드라마", "스포츠", "프로야구",
    "날씨", "기상청",
]


def is_excluded(article):
    """제목에 명백히 무관한 키워드가 있으면 True."""
    title = article['title']
    return any(pat in title for pat in EXCLUDE_PATTERNS)


def compute_relevance_score(article, panel_id):
    """제목+설명에서 관련 단어 출현 횟수 기반 0.0~1.0 점수. 제목 매칭 가중치 2배."""
    title = article['title']
    desc = article['desc']
    terms = RELEVANCE_TERMS.get(panel_id, set())
    if not terms:
        return 0.5
    title_hits = sum(1 for t in terms if t in title)
    desc_hits = sum(1 for t in terms if t in desc and t not in title)
    return min((title_hits * 2 + desc_hits) / 6.0, 1.0)


def filter_by_relevance(news_list, panel_id, min_score=0.4):
    """최소 점수 미만 기사 제거. 네거티브 필터 후 점수 내림차순 정렬."""
    before_exclude = len(news_list)
    news_list = [n for n in news_list if not is_excluded(n)]
    excluded = before_exclude - len(news_list)
    if excluded:
        logger.info(f"  네거티브 필터: {panel_id} {excluded}건 제외")
    scored = [(n, compute_relevance_score(n, panel_id)) for n in news_list]
    filtered = [(n, s) for n, s in scored if s >= min_score]
    filtered.sort(key=lambda x: x[1], reverse=True)
    removed = len(news_list) - len(filtered)
    if removed:
        logger.info(f"  관련도 필터: {panel_id} {removed}건 제거 (총 {len(filtered)}건 유지)")
    for n, s in filtered:
        n['relevance_score'] = round(s, 3)
    return [n for n, _ in filtered]


def dedup_across_panels(panel_a, panel_b, panel_c):
    """패널 간 교차 중복 제거. Panel A 우선 → B → C 순."""
    a_titles = [n['title'] for n in panel_a]
    b_titles = [n['title'] for n in panel_b]

    deduped_b = [n for n in panel_b if not is_near_duplicate(n['title'], a_titles)]
    deduped_c = [
        n for n in panel_c
        if not is_near_duplicate(n['title'], a_titles)
        and not is_near_duplicate(n['title'], b_titles)
    ]

    removed_b = len(panel_b) - len(deduped_b)
    removed_c = len(panel_c) - len(deduped_c)
    if removed_b:
        logger.info(f"  교차 중복 제거: Panel B {removed_b}건 제거")
    if removed_c:
        logger.info(f"  교차 중복 제거: Panel C {removed_c}건 제거")
    return panel_a, deduped_b, deduped_c


# ============================================================
# 5. 뉴스 수집 (Naver API + 공공기관 RSS)
# ============================================================
def fetch_news(panel_id, keywords):
    """Naver 뉴스 검색 API로 뉴스 수집. NEWS_COLLECTION_DAYS 환경변수로 기간 설정."""
    client_id = os.environ.get('NAVER_CLIENT_ID')
    client_secret = os.environ.get('NAVER_CLIENT_SECRET')
    if not client_id or not client_secret:
        logger.warning(f"Naver API 키 미설정 ({panel_id})")
        return []

    days = int(os.environ.get('NEWS_COLLECTION_DAYS', '7'))
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
    collected = []
    seen = set()
    now = datetime.datetime.now(datetime.timezone.utc)
    limit = now - datetime.timedelta(days=days)

    for kw in keywords:
        try:
            resp = requests.get(
                url, headers=headers,
                params={"query": kw, "display": 10, "sort": "date"},
                timeout=10
            )
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
                        "date": pd.strftime("%Y-%m-%d"),
                        "source": "naver",
                    })
                    seen.add(t)
                except Exception:
                    continue
        except Exception:
            continue

    logger.info(f"  Naver 수집: {panel_id} {len(collected)}건 (최근 {days}일)")
    return sorted(collected, key=lambda x: x['date'], reverse=True)[:12]


def fetch_rss_news(panel_id):
    """공공기관 RSS 피드 수집 (Panel B 전용). feedparser 사용."""
    feeds = [f for f in PROFILE.get('rss_feeds', []) if f['panel'] == panel_id]
    if not feeds:
        return []

    days = int(os.environ.get('NEWS_COLLECTION_DAYS', '7'))
    now = datetime.datetime.now(datetime.timezone.utc)
    limit = now - datetime.timedelta(days=days)
    collected = []
    seen = set()

    for feed_info in feeds:
        try:
            feed = feedparser.parse(feed_info['url'])
            for entry in feed.entries:
                try:
                    pub = None
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        pub = datetime.datetime(
                            *entry.published_parsed[:6],
                            tzinfo=datetime.timezone.utc
                        )
                    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                        pub = datetime.datetime(
                            *entry.updated_parsed[:6],
                            tzinfo=datetime.timezone.utc
                        )

                    if pub and pub < limit:
                        continue

                    t = clean_html(entry.get('title', ''))
                    if not t or is_near_duplicate(t, seen):
                        continue

                    desc = clean_html(entry.get('summary', entry.get('description', '')))
                    link = entry.get('link', '')
                    date_str = (
                        pub.strftime("%Y-%m-%d") if pub
                        else datetime.datetime.now(KST).strftime("%Y-%m-%d")
                    )
                    collected.append({
                        "title": t,
                        "link": link,
                        "desc": desc,
                        "date": date_str,
                        "source": f"rss_{feed_info['label']}",
                    })
                    seen.add(t)
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"RSS 수집 실패 ({feed_info['label']}): {e}")
            continue

    logger.info(
        f"  RSS 수집: {panel_id} {len(collected)}건 "
        f"({', '.join(f['label'] for f in feeds)})"
    )
    return collected


# ============================================================
# 6. 패널별 6단계 AI 분석 (Phase 1)
# ============================================================
def analyze_panel(api_key, news_list, panel_id):
    """6단계 분석. top-3 기사를 선정하여 분석.

    반환: (분석된 기사 리스트, error_type 또는 None)
    """
    if not news_list:
        return [], None

    analyst_role = PROFILE['analyst_roles'].get(panel_id, '오뚜기라면 HR 전략 애널리스트')
    panel_label = PROFILE['panel_labels'].get(panel_id, panel_id)
    selection_rule = PROFILE['selection_rules'].get(panel_id, '')

    ctx = ""
    for i, n in enumerate(news_list):
        ctx += f"[{i}] {n['title']} | {n['desc']}\n"

    prompt = f"""당신은 {analyst_role}입니다.

[독자] 과장·팀장급 이상 의사결정권자
[톤] 보고서 형식, 경어체, 수식어 배제, 숫자·데이터·의사결정 포인트 중심

[회사 컨텍스트]
{COMPANY_CONTEXT}

아래 [{panel_label}] 뉴스 후보에서 **최대 3개**를 선정하여 6단계 전략 분석을 작성하세요.

[선정 기준]
{selection_rule}
- 관련 뉴스가 없으면 정확히 {{"articles": []}} 만 출력하세요.
- 품질 우선: 1개라도 깊은 분석이 3개의 얕은 분석보다 낫습니다.

[6단계 분석 스키마]
- signal_strength: High(즉각 대응 필요) | Medium(모니터링) | Low(참고)
- fact: 수치 포함 핵심 사실 2~3문장 (뉴스에 있는 내용만)
- so_what: "그래서 오뚜기라면에 뭐가 달라지는가?" — 1문장
- business_impact: 재무·운영·인력 측면의 영향
- strategic_options: A(선제 대응), B(관망) 각각 action + tradeoff
- decision_point: 기한 명시 + 미결 시 리스크

[중요 규칙]
1. 반드시 아래 JSON 형식만 출력하세요. 다른 텍스트, 마크다운은 절대 포함하지 마세요.
2. 뉴스에 없는 사실·수치를 만들어내지 마세요. 추정 시 "(추정)" 명시.
3. ref_id는 반드시 정수여야 합니다.

{{"articles": [{_ARTICLE_SCHEMA}]}}

뉴스 후보:
{ctx}"""

    logger.info(f"AI 분석 중 ({panel_id})...")
    raw, err = call_gemini(api_key, prompt)
    if not raw:
        logger.warning(f"Gemini 1차 실패 ({panel_id}): {err} — 간소화 프롬프트로 재시도")
        time.sleep(10)
        simple_ctx = "\n".join(
            f"[{i}] {n['title']} | {n['desc']}"
            for i, n in enumerate(news_list[:2])
        )
        simple_prompt = f"""오뚜기라면 전략 애널리스트입니다. 아래 뉴스를 6단계 분석하세요.

[회사 컨텍스트]
{COMPANY_CONTEXT}

JSON만 출력하세요:
{{"articles": [{_ARTICLE_SCHEMA}]}}

뉴스:
{simple_ctx}"""
        raw, err = call_gemini(api_key, simple_prompt)
        if not raw:
            logger.error(f"Gemini 2차 실패 ({panel_id}): {err}")
            return [], err

    parsed = extract_json_from_text(raw)
    if not parsed or not isinstance(parsed.get('articles'), list):
        logger.error(f"JSON 구조 불일치 ({panel_id}) — raw 앞 300자: {raw[:300]}")
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

    logger.info(f"{panel_id} 분석 완료: {len(result)}건")
    return result, None


# ============================================================
# 7. 스마트 폴백 (AI 실패 시 관련도 기반)
# ============================================================
def make_smart_fallback(news_list, panel_id, error_type=None):
    """AI 실패 시 폴백.

    Tier 1: 높은 관련도(0.5) 기사만 최대 2개 포함
    Tier 2: 관련 기사 없으면 빈 리스트

    반환: (articles_list, is_fallback: bool)
    """
    if not news_list:
        return [], True

    high_relevance = filter_by_relevance(news_list, panel_id, min_score=0.5)
    panel_label = PROFILE['panel_labels'].get(panel_id, panel_id)

    if high_relevance:
        result = []
        for n in high_relevance[:2]:
            result.append({
                "headline": n['title'],
                "signal_strength": "Medium",
                "fact": n['desc'],
                "so_what": f"{panel_label} 관점에서 원문 확인이 필요합니다.",
                "business_impact": "오뚜기라면 사업 영향도는 원문 기사를 통해 평가하시기 바랍니다.",
                "strategic_options": [
                    {
                        "option": "A. 원문 확인",
                        "action": "원문 기사 확인 후 영향도 평가",
                        "tradeoff": "시간 소요",
                    },
                    {
                        "option": "B. 모니터링 유지",
                        "action": "다음 주 동향 재확인",
                        "tradeoff": "대응 지연 가능",
                    },
                ],
                "decision_point": "원문 확인 후 관련 부서(경영기획/인사팀)에 공유 여부 결정",
                "link": n['link'],
                "date": n['date'],
            })
        logger.info(f"스마트 폴백 ({panel_id}): Tier 1 — {len(result)}건 (관련도 0.5 이상)")
        return result, True

    logger.info(f"스마트 폴백 ({panel_id}): Tier 2 — 관련 기사 없음")
    return [], True


# ============================================================
# 8. Panel D — 비즈니스 리포트 (Phase 1)
# ============================================================
def generate_business_report(api_key, panel_a_news, panel_b_news, panel_c_news):
    """3축(A·B·C) 교차 통합 비즈니스 리포트 생성 (Panel D) — 패널 개수별 동적 프롬프트."""
    def fmt_panel(label, news):
        lines = f"--- {label} ---\n"
        for i, n in enumerate(news):
            lines += f"[{i}] {n['title']} | {n['desc']}\n"
        return lines

    # 패널 개수 계산
    panel_count = sum([len(panel_a_news) > 0, len(panel_b_news) > 0, len(panel_c_news) > 0])

    all_ctx = ""
    if panel_a_news:
        all_ctx += fmt_panel("Panel A — 국제 MACRO", panel_a_news)
    if panel_b_news:
        if all_ctx:
            all_ctx += "\n"
        all_ctx += fmt_panel("Panel B — 한국 MICRO", panel_b_news)
    if panel_c_news:
        if all_ctx:
            all_ctx += "\n"
        all_ctx += fmt_panel("Panel C — 산업·회사", panel_c_news)

    # 패널 개수별 동적 프롬프트
    if panel_count >= 3:
        # 3층 분석: 전체 인과 프레임워크
        framework = """[분석 프레임워크]
Layer 1 (Panel A): 이번 주 글로벌에서 무슨 일이 일어났는가?
Layer 2 (Panel B): 한국은 어떻게 반응했/반응할 것인가?
Layer 3 (Panel C): 오뚜기라면은 어디에 노출되었는가?
통합 질문: 세 층위가 같은 방향으로 수렴(Converging)하는가, 상쇄(Diverging)하는가, 불확실(Ambiguous)한가?

[필수 규칙]
1. causal_narrative는 "A→B→C" 3층 인과 서사로 작성하세요."""
    elif panel_count == 2:
        # 2층 분석: 두 층 사이의 인과관계
        framework = """[분석 프레임워크]
제시된 2개 패널 간 인과관계를 분석하세요.
- MACRO→MICRO: 글로벌 동향이 한국에 미치는 영향
- MACRO→산업: 글로벌 이슈가 식품·제조산업에 미치는 영향
- MICRO→산업: 한국 경제정책이 오뚜기라면에 미치는 영향

[필수 규칙]
1. causal_narrative는 "X→Y" 2층 인과 서사로 작성하세요."""
    else:
        # 1층 심화 분석: 단일 패널 deep-dive
        framework = """[분석 프레임워크]
제시된 1개 패널에 대해 심화 분석하세요.
- 오뚜기라면에 미치는 직접적 영향을 구체적으로 분석
- 가능한 대응 전략 3~4개 도출
- 불확실 요소와 모니터링 대상 명시

[필수 규칙]
1. causal_narrative는 이슈의 구체적 전개와 영향을 한 문단으로 작성하세요."""

    prompt = f"""당신은 BCG/Goldman Sachs 30년 경력 수석 컨설턴트입니다.

[회사 컨텍스트]
{COMPANY_CONTEXT}

{framework}
2. 반드시 아래 JSON 형식만 출력하세요. 마크다운 불가.
3. 뉴스에 없는 사실·수치를 만들어내지 마세요. 추정 시 "(추정)" 명시.
4. bluf: Bottom Line Up Front — 의사결정자가 가장 먼저 알아야 할 3문장.
5. risks: 3개 이하.
6. watch_list: 다음 주까지 모니터링할 구체적 지표 2~3개.

{{"report": {_REPORT_SCHEMA}}}

이번 주 뉴스 데이터:
{all_ctx}"""

    logger.info(f"Panel D 비즈니스 리포트 생성 중 (패널 {panel_count}개)...")
    raw, err = call_gemini(api_key, prompt)
    if raw:
        parsed = extract_json_from_text(raw)
        if parsed:
            # {"report": {...}} 또는 직접 {...} 형태 모두 처리
            report = parsed.get('report') if isinstance(parsed.get('report'), dict) else parsed
            if isinstance(report, dict) and report.get('bluf') and report.get('direction'):
                logger.info(f"비즈니스 리포트 생성 완료: direction={report['direction']} (패널 {panel_count}개)")
                return report
        logger.error(f"리포트 JSON 파싱 실패 — raw 앞 300자: {raw[:300]}")
    else:
        logger.error(f"Gemini 응답 없음 (generate_business_report): {err}")
    return None


# ============================================================
# 9. 품질 게이트 + 관리자 알림 (Phase 1)
# ============================================================
def quality_gate(panel_results, panel_is_fallback, business_report):
    """발송 전 품질 검증. (should_send, edition_type, warnings) 반환.

    real_panels: AI 분석 성공 패널 수 (A/B/C 중)
    ≥2 → full / 1 → full+경고 / 0+폴백 → light / 모두없음 → 중단
    """
    warnings = []
    real_panels = sum(
        1 for pid in ('PANEL_A', 'PANEL_B', 'PANEL_C')
        if panel_results.get(pid) and not panel_is_fallback.get(pid)
    )

    if real_panels >= 2:
        return True, "full", warnings

    if real_panels == 1:
        warnings.append("WARNING: AI 분석 3개 패널 중 1개만 성공")
        return True, "full", warnings

    # real_panels == 0
    has_any_content = any(panel_results.get(pid) for pid in ('PANEL_A', 'PANEL_B', 'PANEL_C'))
    if has_any_content:
        warnings.append("CRITICAL: AI 분석 전면 실패. Light 에디션으로 발송합니다.")
        return True, "light", warnings

    warnings.append("CRITICAL: 콘텐츠 없음. 발송 중단.")
    return False, "skip", warnings


def send_admin_alert(app_password, warnings):
    """품질 경고 시 관리자에게 알림 메일 발송."""
    body = "HR Newsletter Quality Gate Warnings:\n\n" + "\n".join(warnings)
    body += f"\n\nTimestamp: {datetime.datetime.now(KST).isoformat()}"

    msg = MIMEMultipart()
    msg['From'] = f"HR Brief Bot <{SENDER_EMAIL}>"
    msg['To'] = SENDER_EMAIL
    msg['Subject'] = (
        f"[ALERT] Newsletter Quality Issue - "
        f"{datetime.datetime.now(KST).strftime('%Y-%m-%d')}"
    )
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.login(SENDER_EMAIL, app_password)
            server.sendmail(SENDER_EMAIL, SENDER_EMAIL, msg.as_string())
        logger.info("관리자 알림 발송 완료")
    except Exception as e:
        logger.error(f"관리자 알림 발송 실패: {e}")


# ============================================================
# 10. 회사 소식 (IMAP 회신 확인 / 토요일 요청)
# ============================================================
def send_news_request_email(app_password):
    """토요일: 회사 소식 요청 메일을 개인메일로 발송. timeout + 에러 처리."""
    try:
        today = datetime.datetime.now(KST).strftime("%Y-%m-%d")
        subject = f"[회사소식요청] {today}"
        body = f"""안녕하세요, 성명재입니다.

이번 주 오뚜기라면 회사 소식이 있다면 이 메일에 회신해주세요.
(신제품 출시, 조직 변경, 이벤트, 수상 등)

회신이 없을 경우 오뚜기 신제품 관련 뉴스로 자동 대체됩니다.

---
Weekly HR Strategic Intelligence 자동 발송 시스템
"""
        msg = MIMEMultipart()
        msg['From'] = f"HR Brief Bot <{SENDER_EMAIL}>"
        msg['To'] = SENDER_EMAIL
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.login(SENDER_EMAIL, app_password)
            server.sendmail(SENDER_EMAIL, SENDER_EMAIL, msg.as_string())
        logger.info(f"토요일 회사소식 요청 메일 발송 완료: {subject}")
        return True
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"토요일 메일 SMTP 인증 실패: {e}")
        return False
    except (smtplib.SMTPException, OSError) as e:
        logger.error(f"토요일 메일 발송 실패: {e}")
        return False


def check_company_news_reply(app_password):
    """IMAP으로 [회사소식요청]에 대한 회신 확인. timeout + try-finally로 logout 보장."""
    mail = None
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", timeout=30)
        mail.login(SENDER_EMAIL, app_password)
        mail.select("INBOX")

        # 최근 7일 내 회신 검색
        since_date = (datetime.datetime.now(KST) - datetime.timedelta(days=7)).strftime("%d-%b-%Y")
        _, data = mail.search(None, f'(SINCE "{since_date}" SUBJECT "Re: [회사소식요청]")')

        if not data[0]:
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

        # 회신 본문에서 인용 부분 제거
        lines = []
        for line in body.split('\n'):
            if line.strip().startswith('>') or line.strip() == '--':
                break
            lines.append(line)
        clean_body = '\n'.join(lines).strip()

        if len(clean_body) > 10:
            return clean_body
        return None
    except (imaplib.IMAP4.error, OSError, TimeoutError) as e:
        logger.error(f"IMAP 확인 실패 ({type(e).__name__}): {e}")
        return None
    except Exception as e:
        logger.error(f"IMAP 처리 중 예기치 않은 오류: {e}")
        return None
    finally:
        if mail is not None:
            try:
                mail.logout()
            except Exception:
                pass


def fetch_company_fallback_news():
    """회신 없을 때: INDUSTRY_PROFILE의 company_news_keywords로 회사 뉴스 검색."""
    client_id = os.environ.get('NAVER_CLIENT_ID')
    client_secret = os.environ.get('NAVER_CLIENT_SECRET')
    if not client_id or not client_secret:
        return []

    keywords = PROFILE.get('company_news_keywords', ["오뚜기 신제품", "오뚜기라면 신제품", "오뚜기 출시"])
    filter_kw = PROFILE.get('company_filter_keyword', "오뚜기")
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
    results = []
    for kw in keywords:
        try:
            resp = requests.get(
                url, headers=headers,
                params={"query": kw, "display": 5, "sort": "date"},
                timeout=10
            )
            if resp.status_code == 200:
                for item in resp.json().get('items', []):
                    t = clean_html(item['title'])
                    if filter_kw not in t:
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
# 11. HTML 생성 — 4-Panel (Phase 1)
# ============================================================
def _signal_badge(level):
    """signal_strength 레벨에 따른 인라인 배지 HTML."""
    colors = {
        "High": ("#dc2626", "HIGH"),
        "Medium": ("#d97706", "MEDIUM"),
        "Low": ("#6b7280", "LOW"),
    }
    bg, label = colors.get(level, ("#6b7280", level or "—"))
    return (
        f'<span style="display:inline-block;background:{bg};color:#fff;'
        f'font-size:10px;font-weight:700;padding:2px 7px;border-radius:3px;'
        f'letter-spacing:0.5px;margin-bottom:8px;">{label}</span>'
    )


def _direction_badge(direction):
    """direction 값에 따른 인라인 배지 HTML."""
    colors = {
        "Converging": ("#dc2626", "▲ CONVERGING — 리스크 수렴"),
        "Diverging": ("#15803d", "▽ DIVERGING — 리스크 상쇄"),
        "Ambiguous": ("#d97706", "◇ AMBIGUOUS — 불확실"),
    }
    bg, label = colors.get(direction, ("#6b7280", direction or "—"))
    return (
        f'<span style="display:inline-block;background:{bg};color:#fff;'
        f'font-size:11px;font-weight:700;padding:4px 12px;border-radius:3px;">{label}</span>'
    )


def _mk_article(item, panel_color):
    """6단계 분석 기사 HTML 블록 생성."""
    strategic_opts_html = ""
    for opt in item.get('strategic_options', []):
        strategic_opts_html += (
            f'<div style="margin-bottom:6px;">'
            f'<span style="font-weight:700;color:#333;">{opt.get("option", "")}</span> '
            f'{opt.get("action", "")} '
            f'<span style="color:#999;font-size:12px;">(tradeoff: {opt.get("tradeoff", "")})</span>'
            f'</div>'
        )

    return f"""
    <div style="margin-bottom:28px;">
        <div style="font-size:11px;color:#999;margin-bottom:4px;">{item.get('date', '')}</div>
        {_signal_badge(item.get('signal_strength', ''))}
        <h3 style="margin:0 0 14px 0;font-size:16px;font-weight:700;line-height:1.5;">
            <a href="{item.get('link', '#')}" target="_blank"
               style="text-decoration:none;color:#111;">{item.get('headline', '')}</a>
        </h3>
        <div style="margin-bottom:10px;">
            <span style="font-size:10px;font-weight:700;color:{panel_color};
                         letter-spacing:0.8px;">FACT</span>
            <div style="font-size:14px;color:#333;line-height:1.8;margin-top:3px;">
                {item.get('fact', '')}
            </div>
        </div>
        <div style="background:#f0f9ff;border-left:3px solid {panel_color};
                    padding:10px 14px;margin-bottom:10px;border-radius:0 4px 4px 0;">
            <span style="font-size:10px;font-weight:700;color:{panel_color};
                         letter-spacing:0.8px;">SO WHAT</span>
            <div style="font-size:14px;color:#1e3a5f;font-weight:600;
                        line-height:1.7;margin-top:3px;">
                {item.get('so_what', '')}
            </div>
        </div>
        <div style="margin-bottom:10px;">
            <span style="font-size:10px;font-weight:700;color:{panel_color};
                         letter-spacing:0.8px;">BUSINESS IMPACT</span>
            <div style="font-size:14px;color:#333;line-height:1.8;margin-top:3px;">
                {item.get('business_impact', '')}
            </div>
        </div>
        <div style="background:#F5F5F5;padding:12px 14px;border-radius:4px;margin-bottom:10px;">
            <span style="font-size:10px;font-weight:700;color:{panel_color};
                         letter-spacing:0.8px;">STRATEGIC OPTIONS</span>
            <div style="font-size:13px;color:#222;line-height:1.7;margin-top:6px;">
                {strategic_opts_html}
            </div>
        </div>
        <div style="background:#fef9ec;border:1px solid #fbbf24;
                    padding:10px 14px;border-radius:4px;">
            <span style="font-size:10px;font-weight:700;color:#92400e;
                         letter-spacing:0.8px;">DECISION POINT</span>
            <div style="font-size:13px;color:#78350f;font-weight:600;
                        line-height:1.7;margin-top:3px;">
                {item.get('decision_point', '')}
            </div>
        </div>
    </div>
    <div style="border-bottom:1px solid #eee;margin-bottom:28px;"></div>"""


def _mk_panel_header(panel_id, title):
    """패널 헤더 HTML."""
    color = PANEL_COLORS.get(panel_id, "#333")
    return (
        f'<div style="border-top:3px solid {color};margin:32px 0 20px;">'
        f'<h2 style="font-size:15px;font-weight:800;color:{color};'
        f'margin:12px 0 0;letter-spacing:0.5px;">'
        f'&#9632; {title}</h2></div>'
    )


def build_html(today, panel_a, panel_b, panel_c, business_report, company_html):
    """4-Panel 주간 리포트 HTML 생성."""

    # Panel A
    p_a_color = PANEL_COLORS["PANEL_A"]
    if panel_a:
        p_a_html = "".join(_mk_article(item, p_a_color) for item in panel_a)
    else:
        p_a_html = '<p style="color:#999;font-size:13px;">금주 주요 국제 거시경제 뉴스가 없습니다.</p>'

    # Panel B
    p_b_color = PANEL_COLORS["PANEL_B"]
    if panel_b:
        p_b_html = "".join(_mk_article(item, p_b_color) for item in panel_b)
    else:
        p_b_html = '<p style="color:#999;font-size:13px;">금주 주요 한국 노동·규제 뉴스가 없습니다.</p>'

    # Panel C
    p_c_color = PANEL_COLORS["PANEL_C"]
    if panel_c:
        p_c_html = "".join(_mk_article(item, p_c_color) for item in panel_c)
    else:
        p_c_html = '<p style="color:#999;font-size:13px;">금주 주요 산업·회사 뉴스가 없습니다.</p>'

    # Panel D — 비즈니스 리포트
    p_d_color = PANEL_COLORS["PANEL_D"]
    if business_report:
        bluf_items = "".join(
            f'<li style="margin-bottom:6px;font-weight:600;">{s}</li>'
            for s in business_report.get('bluf', [])
        )
        risks_rows = "".join(
            f'<tr>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;font-size:13px;">'
            f'{r.get("risk","")}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;font-size:12px;'
            f'text-align:center;color:{"#dc2626" if r.get("likelihood")=="High" else "#d97706"};">'
            f'{r.get("likelihood","")}</td>'
            f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;font-size:12px;'
            f'text-align:center;color:{"#dc2626" if r.get("impact")=="High" else "#d97706"};">'
            f'{r.get("impact","")}</td>'
            f'</tr>'
            for r in business_report.get('risks', [])
        )
        watch_items = "".join(
            f'<span style="display:inline-block;background:#f3f4f6;border:1px solid #d1d5db;'
            f'border-radius:3px;padding:3px 10px;font-size:12px;margin:2px;">{w}</span>'
            for w in business_report.get('watch_list', [])
        )
        p_d_html = f"""
        <div style="background:#faf7ff;border:1px solid #ede9fe;
                    border-radius:6px;padding:20px 24px;margin-bottom:20px;">
            <div style="margin-bottom:16px;">
                <span style="font-size:10px;font-weight:700;color:{p_d_color};
                             letter-spacing:0.8px;">BLUF — BOTTOM LINE UP FRONT</span>
                <ol style="margin:8px 0 0;padding-left:20px;color:#1e1b4b;
                           font-size:14px;line-height:1.8;">
                    {bluf_items}
                </ol>
            </div>
            <div style="margin-bottom:16px;">
                {_direction_badge(business_report.get('direction',''))}
                <span style="font-size:13px;color:#4b5563;margin-left:10px;">
                    {business_report.get('direction_reason','')}
                </span>
            </div>
            <div style="margin-bottom:14px;">
                <span style="font-size:10px;font-weight:700;color:{p_d_color};
                             letter-spacing:0.8px;">CAUSAL NARRATIVE</span>
                <div style="font-size:14px;color:#333;line-height:1.8;margin-top:4px;">
                    {business_report.get('causal_narrative','')}
                </div>
            </div>
            <div style="margin-bottom:14px;">
                <span style="font-size:10px;font-weight:700;color:{p_d_color};
                             letter-spacing:0.8px;">KEY VARIABLE</span>
                <span style="font-size:14px;color:#333;margin-left:8px;font-weight:600;">
                    {business_report.get('key_variable','')}
                </span>
            </div>
            <div style="margin-bottom:14px;">
                <span style="font-size:10px;font-weight:700;color:{p_d_color};
                             letter-spacing:0.8px;">RISKS</span>
                <table style="width:100%;border-collapse:collapse;margin-top:8px;">
                    <thead>
                        <tr style="background:#ede9fe;">
                            <th style="padding:6px 10px;text-align:left;font-size:11px;
                                       color:{p_d_color};">리스크</th>
                            <th style="padding:6px 10px;text-align:center;font-size:11px;
                                       color:{p_d_color};width:80px;">가능성</th>
                            <th style="padding:6px 10px;text-align:center;font-size:11px;
                                       color:{p_d_color};width:80px;">영향도</th>
                        </tr>
                    </thead>
                    <tbody>{risks_rows}</tbody>
                </table>
            </div>
            <div style="background:#fef9ec;border:1px solid #fbbf24;
                        padding:10px 14px;border-radius:4px;margin-bottom:14px;">
                <span style="font-size:10px;font-weight:700;color:#92400e;
                             letter-spacing:0.8px;">DECISION POINT</span>
                <div style="font-size:13px;color:#78350f;font-weight:600;
                            line-height:1.7;margin-top:3px;">
                    {business_report.get('decision_point','')}
                </div>
            </div>
            <div>
                <span style="font-size:10px;font-weight:700;color:{p_d_color};
                             letter-spacing:0.8px;">WATCH LIST</span>
                <div style="margin-top:6px;">{watch_items}</div>
            </div>
        </div>"""
    else:
        p_d_html = '<p style="color:#999;font-size:13px;">금주 비즈니스 리포트를 생성하지 못했습니다.</p>'

    html = f"""<html><body style="font-family:'Apple SD Gothic Neo','Malgun Gothic',
'Noto Sans KR',sans-serif;max-width:640px;margin:0 auto;padding:24px;
background:#FFF;color:#333;">

    <!-- 헤더 -->
    <div style="text-align:center;padding-bottom:20px;margin-bottom:8px;
                border-bottom:2px solid #111;">
        <h1 style="margin:0;font-size:19px;font-weight:800;color:#111;letter-spacing:1px;">
            WEEKLY HR STRATEGIC INTELLIGENCE
        </h1>
        <p style="font-size:12px;color:#888;margin:8px 0 0;">
            오뚜기라면 &middot; 성명재 | {today}
        </p>
    </div>

    <!-- Panel A -->
    {_mk_panel_header("PANEL_A", "PANEL A &mdash; 국제 MACRO / 글로벌 정치·경제·원자재")}
    {p_a_html}

    <!-- Panel B -->
    {_mk_panel_header("PANEL_B", "PANEL B &mdash; 한국 MICRO / 경제·노동·산업규제")}
    {p_b_html}

    <!-- Panel C -->
    {_mk_panel_header("PANEL_C", "PANEL C &mdash; 산업·회사 / 경쟁사·HR·수출·ESG")}
    {p_c_html}

    <!-- Panel D -->
    {_mk_panel_header("PANEL_D", "PANEL D &mdash; 비즈니스 리포트 / 3축 통합 전략")}
    {p_d_html}

    <!-- 회사 소식 -->
    <div style="border-top:2px solid #111;margin:32px 0 20px;"></div>
    <h2 style="font-size:15px;font-weight:800;color:#111;margin:0 0 16px 0;">
        &#9632; 회사 소식
    </h2>
    {company_html}

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
    """Gmail SMTP로 이메일 발송. 수신자별 try-except로 부분 실패 격리."""
    failed = []
    for recipient in recipients:
        try:
            msg = MIMEMultipart()
            msg['From'] = f"HR Brief <{SENDER_EMAIL}>"
            msg['To'] = recipient
            msg['Subject'] = subject
            msg.attach(MIMEText(html, 'html', 'utf-8'))

            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
                server.login(SENDER_EMAIL, app_password)
                server.sendmail(SENDER_EMAIL, recipient, msg.as_string())
            logger.info(f"발송 완료: {recipient}")
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP 인증 실패 ({recipient}): {e}")
            failed.append(recipient)
            break  # 인증 실패 시 나머지도 실패할 것이므로 중단
        except (smtplib.SMTPException, OSError) as e:
            logger.error(f"발송 실패 ({recipient}): {e}")
            failed.append(recipient)
            continue  # 다음 수신자 시도
    if failed:
        logger.error(f"발송 실패 수신자: {failed}")
    return failed


# ============================================================
# 13-A. 환경변수 검증 (Phase 1 안정성 강화)
# ============================================================
def validate_environment(mode='newsletter'):
    """필수 환경변수 사전 검증. 누락 시 명확한 오류 메시지."""
    common = ['GMAIL_APP_PASSWORD']
    if mode == 'newsletter':
        required = common + ['GEMINI_API_KEY', 'NAVER_CLIENT_ID', 'NAVER_CLIENT_SECRET']
    else:  # weekend
        required = common
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        logger.error(f"필수 환경변수 누락: {', '.join(missing)}")
        raise EnvironmentError(f"필수 환경변수 누락: {', '.join(missing)}")
    logger.info(f"환경변수 검증 완료 (mode={mode})")


def validate_profile_schema(profile_key, profile_dict):
    """INDUSTRY_PROFILE 필수 키 검증. 누락 시 ValueError 발생."""
    required = [
        "PANEL_A", "PANEL_B", "PANEL_C",
        "relevance",
        "analyst_roles",
        "panel_labels",
        "selection_rules",
        "rss_feeds",
        "company_news_keywords",
        "company_filter_keyword"
    ]
    missing = [k for k in required if k not in profile_dict]
    if missing:
        logger.error(f"프로파일 {profile_key} 스키마 누락: {missing}")
        raise ValueError(f"프로파일 {profile_key} 필수 키 누락: {missing}")
    logger.info(f"프로파일 스키마 검증 완료: {profile_key}")


# ============================================================
# 13. 메인 실행 (Phase 1 — 4-Panel Weekly)
# ============================================================
def run_newsletter():
    """매주 수요일 뉴스레터 메인 실행 (4-Panel)."""
    validate_environment('newsletter')
    validate_profile_schema('FOOD_MFG', PROFILE)
    api_key = os.environ.get('GEMINI_API_KEY')
    app_password = os.environ.get('GMAIL_APP_PASSWORD')
    recipient_str = os.environ.get('RECIPIENT_EMAILS', 'tjdaudwo21@otokirm.com')
    recipients = [e.strip() for e in recipient_str.split(',') if e.strip()]
    today_kst = datetime.datetime.now(KST)
    today = today_kst.strftime("%Y년 %m월 %d일")
    today_str = today_kst.strftime("%Y-%m-%d")

    # Step 1: 뉴스 수집
    logger.info("1. 뉴스 수집 중...")
    panel_a_news = fetch_news("PANEL_A", PROFILE["PANEL_A"])
    panel_b_news = fetch_news("PANEL_B", PROFILE["PANEL_B"]) + fetch_rss_news("PANEL_B")
    panel_c_news = fetch_news("PANEL_C", PROFILE["PANEL_C"])

    # 수집 단계 카운터
    a_fetched = len(panel_a_news)
    b_fetched = len(panel_b_news)
    c_fetched = len(panel_c_news)
    logger.info(
        f"수집 완료: Panel A {a_fetched}건, "
        f"Panel B {b_fetched}건, Panel C {c_fetched}건"
    )

    # Step 2: 관련도 필터링
    logger.info("2. 관련도 필터링...")
    panel_a_news = filter_by_relevance(panel_a_news, "PANEL_A")
    panel_b_news = filter_by_relevance(panel_b_news, "PANEL_B")
    panel_c_news = filter_by_relevance(panel_c_news, "PANEL_C")

    # 필터링 후 카운터 및 필터율 계산
    a_after_filter = len(panel_a_news)
    b_after_filter = len(panel_b_news)
    c_after_filter = len(panel_c_news)

    a_filter_rate = 0 if a_fetched == 0 else int(100 * (a_fetched - a_after_filter) / a_fetched)
    b_filter_rate = 0 if b_fetched == 0 else int(100 * (b_fetched - b_after_filter) / b_fetched)
    c_filter_rate = 0 if c_fetched == 0 else int(100 * (c_fetched - c_after_filter) / c_fetched)

    # 상위 3개 점수 추출
    a_top_scores = [n.get('relevance_score', 0) for n in panel_a_news[:3]]
    b_top_scores = [n.get('relevance_score', 0) for n in panel_b_news[:3]]
    c_top_scores = [n.get('relevance_score', 0) for n in panel_c_news[:3]]

    logger.info(
        f"필터 후: Panel A {a_after_filter}건 (필터율 {a_filter_rate}%, 상위 점수 {a_top_scores}), "
        f"Panel B {b_after_filter}건 (필터율 {b_filter_rate}%, 상위 점수 {b_top_scores}), "
        f"Panel C {c_after_filter}건 (필터율 {c_filter_rate}%, 상위 점수 {c_top_scores})"
    )

    # Step 3: 패널 간 교차 중복 제거
    panel_a_news, panel_b_news, panel_c_news = dedup_across_panels(
        panel_a_news, panel_b_news, panel_c_news
    )
    logger.info(
        f"필터 후: Panel A {len(panel_a_news)}건, "
        f"Panel B {len(panel_b_news)}건, Panel C {len(panel_c_news)}건"
    )

    # Step 4: Panel A AI 분석
    logger.info("3. AI 분석 시작 (Panel A)...")
    _t0 = time.time()
    final_a, a_err = analyze_panel(api_key, panel_a_news[:6], "PANEL_A") if panel_a_news else ([], None)
    logger.info(f"  Panel A 분석 완료: {time.time() - _t0:.1f}s")
    a_is_fallback = False
    if not final_a:
        final_a, a_is_fallback = make_smart_fallback(panel_a_news, "PANEL_A", a_err)

    # Step 5: Panel B AI 분석 — 8초 딜레이
    logger.info("3. AI 분석 시작 (Panel B)...")
    if panel_a_news:
        time.sleep(8)
    _t0 = time.time()
    final_b, b_err = analyze_panel(api_key, panel_b_news[:6], "PANEL_B") if panel_b_news else ([], None)
    logger.info(f"  Panel B 분석 완료: {time.time() - _t0:.1f}s")
    b_is_fallback = False
    if not final_b:
        final_b, b_is_fallback = make_smart_fallback(panel_b_news, "PANEL_B", b_err)

    # Step 6: Panel C AI 분석 — 8초 딜레이
    logger.info("3. AI 분석 시작 (Panel C)...")
    if panel_b_news:
        time.sleep(8)
    _t0 = time.time()
    final_c, c_err = analyze_panel(api_key, panel_c_news[:6], "PANEL_C") if panel_c_news else ([], None)
    logger.info(f"  Panel C 분석 완료: {time.time() - _t0:.1f}s")
    c_is_fallback = False
    if not final_c:
        final_c, c_is_fallback = make_smart_fallback(panel_c_news, "PANEL_C", c_err)

    # Step 7: Panel D 비즈니스 리포트
    total_articles = len(panel_a_news) + len(panel_b_news) + len(panel_c_news)
    business_report = None
    if total_articles >= 2:
        logger.info("Gemini rate limit 보호: 10초 대기...")
        time.sleep(10)
        business_report = generate_business_report(
            api_key, panel_a_news[:4], panel_b_news[:4], panel_c_news[:4]
        )
    else:
        logger.info(f"비즈니스 리포트 스킵: 기사 {total_articles}건 (최소 2건 필요)")

    # Step 8: 품질 게이트
    logger.info("4. 품질 게이트 검증...")
    panel_results = {"PANEL_A": final_a, "PANEL_B": final_b, "PANEL_C": final_c}
    panel_is_fallback = {"PANEL_A": a_is_fallback, "PANEL_B": b_is_fallback, "PANEL_C": c_is_fallback}
    should_send, edition_type, warnings = quality_gate(panel_results, panel_is_fallback, business_report)
    for w in warnings:
        logger.warning(w)

    if not should_send:
        send_admin_alert(app_password, warnings)
        logger.warning("뉴스레터 발송 중단 (품질 게이트)")
        return

    if edition_type == "light":
        send_admin_alert(app_password, warnings)

    # Step 9: 회사 소식
    logger.info("5. 회사 소식 확인 중...")
    company_reply = check_company_news_reply(app_password)
    if company_reply:
        logger.info("회신 발견 → 회사 소식 삽입")
        company_html = (
            f'<div style="font-size:14px;color:#333;line-height:1.8;">'
            f'{company_reply.replace(chr(10), "<br>")}</div>'
        )
    else:
        logger.info("회신 없음 → 오뚜기 신제품 뉴스 검색")
        fallback_news = fetch_company_fallback_news()
        if fallback_news:
            items_html = ""
            for n in fallback_news:
                items_html += (
                    f'<div style="margin-bottom:12px;">'
                    f'<a href="{n["link"]}" target="_blank" '
                    f'style="font-size:14px;color:#111;text-decoration:none;font-weight:600;">'
                    f'{n["title"]}</a>'
                    f'<div style="font-size:13px;color:#666;margin-top:4px;line-height:1.6;">'
                    f'{n["desc"]}</div></div>'
                )
            company_html = items_html
        else:
            company_html = '<p style="color:#999;font-size:13px;">금주 회사 소식이 없습니다.</p>'

    # Step 10: JSON 저장
    save_report_json(
        today_str,
        final_a, final_b, final_c, business_report,
        raw_a=panel_a_news, raw_b=panel_b_news, raw_c=panel_c_news,
    )

    # Step 11: HTML 생성 & 발송
    logger.info("6. HTML 생성 & 발송...")
    html = build_html(today, final_a, final_b, final_c, business_report, company_html)
    if edition_type == "light":
        subject = f"[{today}] Weekly HR Brief (Light) - 오뚜기라면"
    else:
        subject = f"[{today}] Weekly HR Strategic Intelligence - 오뚜기라면"
    failed_recipients = send_email(app_password, recipients, subject, html)

    # [RUN SUMMARY] 구조화 실행 요약 (필터링 통계 포함)
    fallback_count = sum([a_is_fallback, b_is_fallback, c_is_fallback])
    send_result = "ok" if not failed_recipients else f"failed={failed_recipients}"
    logger.info(
        f"[RUN SUMMARY] "
        f"수집=A{a_fetched}/B{b_fetched}/C{c_fetched} "
        f"필터율=A{a_filter_rate}%/B{b_filter_rate}%/C{c_filter_rate}% "
        f"상위점수=A{a_top_scores}/B{b_top_scores}/C{c_top_scores} "
        f"패널결과=A{len(final_a)}/B{len(final_b)}/C{len(final_c)} "
        f"폴백={fallback_count} report={'ok' if business_report else 'skip'} "
        f"edition={edition_type} 발송={send_result}"
    )
    logger.info("뉴스레터 발송 완료")


def run_weekend_request():
    """토요일: 회사 소식 요청 메일 발송."""
    validate_environment('weekend')
    app_password = os.environ.get('GMAIL_APP_PASSWORD')
    send_news_request_email(app_password)


# ============================================================
# 14. JSON 저장 (Phase 1 신규 — Phase 2 웹 대시보드 연동 준비)
# ============================================================
def save_report_json(today_str, panel_a, panel_b, panel_c, business_report,
                     raw_a=None, raw_b=None, raw_c=None):
    """data/reports/YYYY-MM-DD.json 저장 및 index.json 업데이트.

    raw_a/b/c: 관련도 필터 + 교차 중복 제거 후, AI 선정 이전의 전체 수집 기사.
               Phase 2 기사 스크랩 창고(/articles) 및 NotebookLM 공급용.
    """
    try:
        os.makedirs("data/reports", exist_ok=True)
        report = {
            "date": today_str,
            "generated_at": datetime.datetime.now(KST).isoformat(),
            "raw_articles": {
                "panel_a": raw_a or [],
                "panel_b": raw_b or [],
                "panel_c": raw_c or [],
            },
            "panel_a": panel_a,
            "panel_b": panel_b,
            "panel_c": panel_c,
            "panel_d": business_report,
        }
        report_path = f"data/reports/{today_str}.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logger.info(f"JSON 저장 완료: {report_path}")

        # index.json 업데이트 (최신 52개 유지)
        index_path = "data/reports/index.json"
        if os.path.exists(index_path):
            with open(index_path, "r", encoding="utf-8") as f:
                index = json.load(f)
        else:
            index = {"reports": []}

        # 이미 동일 날짜 있으면 덮어쓰기
        index["reports"] = [r for r in index["reports"] if r.get("date") != today_str]

        # signal_strength 카운트 집계 (웹 뷰어 배지용)
        all_items = list(panel_a or []) + list(panel_b or []) + list(panel_c or [])
        sig_counts = {"High": 0, "Medium": 0, "Low": 0}
        for _item in all_items:
            s = _item.get("signal_strength", "")
            if s in sig_counts:
                sig_counts[s] += 1

        index["reports"].insert(0, {
            "date": today_str,
            "signal_summary": {
                "direction": business_report.get("direction") if business_report else None,
                "High": sig_counts["High"],
                "Medium": sig_counts["Medium"],
                "Low": sig_counts["Low"],
            },
            "panel_d": {
                "topic": (business_report.get("topic") or "") if business_report else "",
            },
            "all_tags": list({
                (_item.get("headline") or "")[:30]
                for _item in all_items
                if _item.get("headline")
            }),
        })
        index["reports"] = index["reports"][:52]

        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        logger.info("index.json 업데이트 완료")

        # latest.md 생성 (NotebookLM raw URL 소비용)
        generate_latest_md(today_str, panel_a, panel_b, panel_c, business_report)
    except Exception as e:
        logger.error(f"JSON 저장 실패: {e}")


def generate_latest_md(today_str, panel_a, panel_b, panel_c, business_report):
    """data/reports/latest.md 생성 — NotebookLM이 raw URL로 소비 가능한 최신 리포트 요약."""
    try:
        panel_labels = {
            "panel_a": PROFILE.get("panel_labels", {}).get("PANEL_A", "국제 MACRO"),
            "panel_b": PROFILE.get("panel_labels", {}).get("PANEL_B", "한국 MICRO"),
            "panel_c": PROFILE.get("panel_labels", {}).get("PANEL_C", "산업·회사"),
        }
        lines = [f"# HR Strategic Intelligence — {today_str}\n"]

        for label_key, articles in [("panel_a", panel_a), ("panel_b", panel_b), ("panel_c", panel_c)]:
            label = panel_labels[label_key]
            lines.append(f"\n## {label}\n")
            for item in (articles or []):
                headline = item.get("headline") or item.get("title", "")
                signal = item.get("signal_strength", "")
                fact = item.get("fact", "")
                so_what = item.get("so_what", "")
                decision = item.get("decision_point", "")
                link = item.get("link", "")
                if link:
                    lines.append(f"### [{signal}] [{headline}]({link})")
                else:
                    lines.append(f"### [{signal}] {headline}")
                if fact:
                    lines.append(f"- **팩트:** {fact}")
                if so_what:
                    lines.append(f"- **So What:** {so_what}")
                if decision:
                    lines.append(f"- **결정 포인트:** {decision}")
                lines.append("")

        if business_report:
            lines.append("\n## 비즈니스 리포트 (Panel D)\n")
            bluf = business_report.get("bluf", [])
            if bluf:
                lines.append("**BLUF:**")
                for b in bluf:
                    lines.append(f"- {b}")
            direction = business_report.get("direction", "")
            direction_reason = business_report.get("direction_reason", "")
            if direction:
                lines.append(f"\n**방향:** {direction} — {direction_reason}")
            narrative = business_report.get("causal_narrative", "")
            if narrative:
                lines.append(f"\n**인과 서사:** {narrative}")
            decision = business_report.get("decision_point", "")
            if decision:
                lines.append(f"\n**결정 포인트:** {decision}")
            watch = business_report.get("watch_list", [])
            if watch:
                lines.append(f"\n**감시 지표:** {', '.join(watch)}")

        md_path = "data/reports/latest.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        logger.info(f"latest.md 생성 완료: {md_path}")
    except Exception as e:
        logger.error(f"latest.md 생성 실패: {e}")


if __name__ == "__main__":
    mode = os.environ.get('BOT_MODE', 'newsletter')
    if mode == 'weekend_request':
        run_weekend_request()
    else:
        run_newsletter()
