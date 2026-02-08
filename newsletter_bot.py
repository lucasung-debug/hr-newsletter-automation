import requests
import json
import datetime
import smtplib
import os
import re
from email.utils import parsedate_to_datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# -----------------------------------------------------------
# 1. 유틸리티 함수
# -----------------------------------------------------------
def clean_html(raw_html):
    cleanr = re.compile('<.*?>|&quot;|&apos;|&gt;|&lt;')
    return re.sub(cleanr, '', raw_html)

def extract_json_from_text(text):
    try:
        match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return None
    except:
        return None

# -----------------------------------------------------------
# 2. [Quality Control] 검증된 고품질 키워드 (하드코딩)
# -----------------------------------------------------------
def get_verified_keywords():
    return {
        # PART 1: 경영진이 봐야 할 거시 담론
        "macro": [
            "2026년 글로벌 경제 전망 금리",
            "글로벌 공급망 리스크 대응 전략",
            "생성형 AI 기업 적용 성공 사례",
            "미국 대선 이후 무역 정책 변화",
            "글로벌 기업 ESG 경영 트렌드"
        ],
        # PART 2: 오뚜기라면 실무/현장 핵심
        "micro": [
            "식품산업 푸드테크 기술 동향",
            "제조업 스마트팩토리 구축 사례",
            "중대재해처벌법 판례 및 대응",
            "생산직 통상임금 성과급 쟁점",
            "글로벌 K-푸드 수출 전략"
        ]
    }

# -----------------------------------------------------------
# 3. 뉴스 수집 (노이즈 필터링 강화)
# -----------------------------------------------------------
def fetch_news_pro(keywords, prefix):
    client_id = os.environ.get('NAVER_CLIENT_ID')
    client_secret = os.environ.get('NAVER_CLIENT_SECRET')
    if not client_id or not client_secret: return []

    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
    
    collected = []
    seen = set()
    
    for kw in keywords:
        # [핵심] 검색 쿼리 튜닝: '분석', '전망' 포함 + '포토', '인사', '부고' 제외
        query = f'{kw} (분석 OR 전망 OR 전략 OR 사례) -포토 -인사 -부고 -오늘의운세'
        
        # 정확도(sim) 우선으로 퀄리티 확보
        params = {"query": query, "display": 5, "sort": "sim"}
        
        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                items = response.json().get('items', [])
                now = datetime.datetime.now(datetime.timezone.utc)
                # 기간: 최근 10일 (주말 포함 넉넉하게)
                limit_date = now - datetime.timedelta(days=10)

                for item in items:
                    try:
                        pub_date = parsedate_to_datetime(item['pubDate'])
                        if pub_date >= limit_date:
                            title = clean_html(item['title'])
                            desc = clean_html(item['description'])
                            
                            # [2차 필터] 제목에 '할인', '마트', '이벤트' 들어가면 제외 (임원용 아님)
                            if any(bad_word in title for bad_word in ["할인", "이벤트", "증정", "모집", "부고"]):
                                continue

                            if title not in seen:
                                collected.append({
                                    "id_prefix": prefix, 
                                    "title": title,
                                    "link": item['originallink'] if item['originallink'] else item['link'],
                                    "desc": desc,
                                    "date": pub_date.strftime("%Y-%m-%d")
                                })
                                seen.add(title)
                    except: continue
        except: continue
        
    return collected

# -----------------------------------------------------------
# 4. 메인 실행 로직
# -----------------------------------------------------------
def run_quality_restored_briefing():
    api_key = os.environ.get('GEMINI_API_KEY')
    app_password = os.environ.get('GMAIL_APP_PASSWORD')
    user_email = "proposition97@gmail.com"
    today = datetime.datetime.now().strftime("%Y년 %m월 %d일")
    
    # 1. 검증된 키워드 가져오기
    keys = get_verified_keywords()
    
    # 2. 뉴스 수집 (M: Macro, F: Food/Field)
    print("running fetch news...")
    macro_news = fetch_news_pro(keys['macro'], "M")
    micro_news = fetch_news_pro(keys['micro'], "F")
    
    # 최신순 정렬 후 상위 10개씩 (과부하 방지)
    macro_news = sorted(macro_news, key=lambda x: x['date'], reverse=True)[:10]
    micro_news = sorted(micro_news, key=lambda x: x['date'], reverse=True)[:10]
    
    # 3. Context 생성
    news_map = {}
    ctx = "--- [PART 1: MACRO CANDIDATES] ---\n"
    for i, n in enumerate(macro_news):
        uid = f"M-{i+1}"
        n['uid'] = uid
        news_map[uid] = n
        ctx += f"[ID:{uid}] {n['title']} | {n['desc'][:100]}\n"
        
    ctx += "\n--- [PART 2: MICRO CANDIDATES] ---\n"
    for i, n in enumerate(micro_news):
        uid = f"F-{i+1}"
        n['uid'] = uid
        news_map[uid] = n
        ctx += f"[ID:{uid}] {n['title']} | {n['desc'][:100]}\n"

    # 4. AI 분석 (BCG 페르소나 강화 + 엄격한 선별)
    print("asking AI...")
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    prompt = f"""
    당신은 오뚜기라면의 **전략기획실장(CSO)**입니다.
    제공된 뉴스 후보군 중에서 경영진 주간회의(Weekly Executive Meeting)에 올릴 **가장 무게감 있고 전략적인 아젠다**를 선별하세요.

    [필수 지침]
    1. **엄격한 큐레이션**: '할인 행사', '단순 사건사고', '지자체 홍보' 등 **지엽적인 뉴스는 과감히 제외**하세요.
    2. **Strategic Insight**: 단순 요약이 아니라, 오뚜기라면의 사업 방향(글로벌, 푸드테크, 리스크 관리)에 주는 시사점을 도출하세요.
    3. **강제 할당**: 
       - PART 1에는 ID가 'M'으로 시작하는 기사만 넣을 것.
       - PART 2에는 ID가 'F'로 시작하는 기사만 넣을 것.
    4. 각 파트별 3~4개의 최상급 기사만 선정하세요.

    [JSON 형식]
    {{
      "part1": [ {{"headline": "임원 보고용 헤드라인", "summary": "요약", "implication": "오뚜기라면 전략적 시사점", "ref_id": "M-1"}} ],
      "part2": [ {{"headline": "임원 보고용 헤드라인", "summary": "요약", "implication": "현장 적용 및 대응 방안", "ref_id": "F-1"}} ]
    }}
    데이터: {ctx}
    """
    
    res = requests.post(api_url, headers={'Content-Type': 'application/json'}, data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}))
    
    final_p1, final_p2 = [], []
    
    if res.status_code == 200:
        try:
            parsed = extract_json_from_text(res.json()['candidates'][0]['content']['parts'][0]['text'])
            if parsed:
                # ID 기반 매핑 + 필터링
                for item in parsed.get('part1', []):
                    if item.get('ref_id') in news_map and item['ref_id'].startswith('M'):
                        original = news_map[item['ref_id']]
                        item.update({'link': original['link'], 'date': original['date']})
                        final_p1.append(item)
                
                for item in parsed.get('part2', []):
                    if item.get('ref_id') in news_map and item['ref_id'].startswith('F'):
                        original = news_map[item['ref_id']]
                        item.update({'link': original['link'], 'date': original['date']})
                        final_p2.append(item)
        except: pass

    # 5. 최후의 백업 (AI가 너무 많이 걸러내서 비었을 경우 대비)
    # 여기서는 Raw Data를 그냥 넣지 않고, 제목 필터링을 한 번 더 거친 상위 기사만 넣음
    if not final_p1:
        for n in macro_news[:3]: final_p1.append({"headline": n['title'], "summary": n['desc'], "implication": "주요 경제 동향입니다.", "link": n['link'], "date": n['date']})
    if not final_p2:
        for n in micro_news[:3]: final_p2.append({"headline": n['title'], "summary": n['desc'], "implication": "주요 산업 동향입니다.", "link": n['link'], "date": n['date']})

    # 6. HTML 생성
    def mk_card(i, bg, tag_color):
        return f"""
        <div style="margin-bottom:25px; padding-bottom:20px; border-bottom:1px solid #eee;">
            <div style="font-size:11px; color:#999; margin-bottom:5px;">{i['date']}</div>
            <h3 style="margin:0 0 10px 0; font-size:18px; font-weight:700; line-height:1.4;">
                <a href="{i['link']}" target="_blank" style="text-decoration:none; color:#111;">{i['headline']}</a>
            </h3>
            <p style="margin:0 0 12px 0; font-size:14px; color:#555; line-height:1.6;">{i['summary']}</p>
            <div style="background-color:{bg}; padding:12px 15px; border-radius:6px; border-left:4px solid {tag_color};">
                <p style="margin:0; font-size:13px; font-weight:bold; color:#333;">💡 Strategic Insight</p>
                <p style="margin:5px 0 0 0; font-size:13px; color:#555;">{i['implication']}</p>
            </div>
        </div>
        """

    html = f"""
    <html><body style="font-family:'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; max-width:680px; margin:0 auto; padding:40px 20px; color:#333;">
        
        <div style="text-align:center; border-bottom:3px solid #ED1C24; padding-bottom:30px; margin-bottom:50px;">
            <p style="font-size:11px; font-weight:800; color:#888; letter-spacing:2px; text-transform:uppercase;">Weekly Executive Report</p>
            <h1 style="margin:10px 0; font-size:32px; font-weight:900; letter-spacing:-1px;">MANAGEMENT <span style="color:#ED1C24;">INSIGHT</span></h1>
            <p style="font-size:13px; color:#666;">{today} | 오뚜기라면 성명재 매니저</p>
        </div>
        
        <div style="margin-bottom:60px;">
            <div style="display:flex; align-items:center; margin-bottom:20px;">
                <span style="background:#00483A; color:#fff; font-size:11px; font-weight:bold; padding:4px 8px; border-radius:4px; margin-right:10px;">PART 1</span>
                <h2 style="margin:0; font-size:22px; color:#00483A; font-weight:800;">MACRO & GLOBAL</h2>
            </div>
            {''.join([mk_card(x, '#F5F9F8', '#00483A') for x in final_p1])}
        </div>
        
        <div>
            <div style="display:flex; align-items:center; margin-bottom:20px;">
                <span style="background:#ED1C24; color:#fff; font-size:11px; font-weight:bold; padding:4px 8px; border-radius:4px; margin-right:10px;">PART 2</span>
                <h2 style="margin:0; font-size:22px; color:#ED1C24; font-weight:800;">INDUSTRY & HR FOCUS</h2>
            </div>
            {''.join([mk_card(x, '#FFF5F5', '#ED1C24') for x in final_p2])}
        </div>
        
        <div style="margin-top:80px; text-align:center; font-size:11px; color:#aaa; border-top:1px solid #eee; padding-top:20px;">
            Confidential: For Internal Executive Review Only
        </div>
    </body></html>
    """

    msg = MIMEMultipart()
    msg['From'] = f"Luca (Strategy Office) <{user_email}>"
    msg['To'] = user_email
    msg['Subject'] = f"[{today}] 주간 경영전략 및 HR 핵심 브리핑 (Premium)"
    msg.attach(MIMEText(html, 'html'))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(user_email, app_password)
        server.sendmail(user_email, user_email, msg.as_string())
    print("🚀 퀄리티 복구 완료! 발송 성공!")

if __name__ == "__main__":
    run_quality_restored_briefing()
