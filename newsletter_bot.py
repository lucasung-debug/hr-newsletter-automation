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
# 2. AI 키워드 기획 (BCG 컨설턴트 페르소나)
# -----------------------------------------------------------
def generate_dynamic_keywords(api_key):
    print("🧠 AI가 이번 주 경영전략 키워드를 기획 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    prompt = f"""
    당신은 30년 경력의 대기업 경영전략 총괄 사장입니다. 
    오늘 날짜({datetime.datetime.now().strftime('%Y-%m-%d')}) 기준, 
    C-Level이 주간 회의에서 반드시 논의해야 할 '네이버 뉴스 검색 키워드'를 기획하세요.

    [조건]
    1. MACRO: 글로벌 경제, 정치, 신기술 트렌드 (3개)
    2. MICRO: 식품/제조 산업, 인사/노무 판례, 조직문화 (3개)
    3. 키워드는 "중대재해처벌법 판례", "글로벌 금리 인하 전망" 처럼 명확하게 작성하세요.

    [출력 양식 (JSON)]
    {{
        "macro_keywords": ["키워드1", "키워드2", "키워드3"],
        "micro_keywords": ["키워드1", "키워드2", "키워드3"]
    }}
    """
    
    try:
        response = requests.post(url, headers={'Content-Type': 'application/json'}, 
                                 data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}))
        if response.status_code == 200:
            result = extract_json_from_text(response.json()['candidates'][0]['content']['parts'][0]['text'])
            if result: return result
    except:
        pass
    
    # [안전장치] AI 실패 시 사용할 전문가용 Evergreen 키워드 세트 (콤마 오류 수정 완료)
    return {
        "macro_keywords": [
            "글로벌 경제 전망 및 금리 환율",
            "대기업 경영 혁신 및 리더십 사례",
            "생성형 AI 비즈니스 적용 트렌드"
        ],
        "micro_keywords": [
            "식품산업 푸드테크 기술 동향",
            "제조업 중대재해처벌법 판례 분석",
            "통상임금 성과급 노무 인사이트",
            "생산직 인력 운영 및 채용 전략"
        ]
    }

# -----------------------------------------------------------
# 3. 뉴스 수집 및 분석 (안전장치 강화)
# -----------------------------------------------------------
def fetch_news_dynamic(keywords, target_type):
    client_id = os.environ.get('NAVER_CLIENT_ID')
    client_secret = os.environ.get('NAVER_CLIENT_SECRET')
    if not client_id or not client_secret: return []

    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
    
    collected_news = []
    seen_titles = set()
    
    for kw in keywords:
        params = {"query": kw, "display": 8, "sort": "sim"}
        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                items = response.json().get('items', [])
                now = datetime.datetime.now(datetime.timezone.utc)
                seven_days_ago = now - datetime.timedelta(days=7)

                for item in items:
                    pub_date = parsedate_to_datetime(item['pubDate'])
                    if pub_date >= seven_days_ago:
                        title = clean_html(item['title'])
                        if title not in seen_titles:
                            collected_news.append({
                                "type": target_type, "title": title, "link": item['originallink'] if item['originallink'] else item['link'],
                                "desc": clean_html(item['description']), "date": pub_date.strftime("%Y-%m-%d")
                            })
                            seen_titles.add(title)
        except: continue
    return collected_news

def run_final_autonomous_briefing():
    api_key = os.environ.get('GEMINI_API_KEY')
    app_password = os.environ.get('GMAIL_APP_PASSWORD')
    user_email = "proposition97@gmail.com"
    today = datetime.datetime.now()
    display_date = today.strftime("%Y년 %m월 %d일")
    
    dynamic_keys = generate_dynamic_keywords(api_key)
    macro_news = fetch_news_dynamic(dynamic_keys['macro_keywords'], "MACRO")
    micro_news = fetch_news_dynamic(dynamic_keys['micro_keywords'], "MICRO")
    
    macro_news = sorted(macro_news, key=lambda x: x['date'], reverse=True)[:12]
    micro_news = sorted(micro_news, key=lambda x: x['date'], reverse=True)[:12]

    if not macro_news and not micro_news: return

    all_news_map = {}; global_id = 1; context_text = ""
    for item in macro_news:
        item['id'] = str(global_id); all_news_map[str(global_id)] = item
        context_text += f"[ID:{global_id}] {item['title']} | {item['desc']}\n"
        global_id += 1
    for item in micro_news:
        item['id'] = str(global_id); all_news_map[str(global_id)] = item
        context_text += f"[ID:{global_id}] {item['title']} | {item['desc']}\n"
        global_id += 1

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    prompt = f"""당신은 오뚜기라면 경영진을 위한 BCG 출신 전략 고문입니다. 
    제공된 뉴스를 분석하여 10개의 핵심 경영 아젠다를 JSON으로 작성하세요.
    데이터: {context_text}
    형식: {{"part1_macro": [{{"headline":"","summary":"","implication":"","ref_id":""}}], "part2_micro": [...]}}"""
    
    response = requests.post(api_url, headers={'Content-Type': 'application/json'}, data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}))
    
    final_parts = {"part1": [], "part2": []}
    if response.status_code == 200:
        try:
            ai_results = extract_json_from_text(response.json()['candidates'][0]['content']['parts'][0]['text'])
            if ai_results:
                for item in ai_results.get('part1_macro', []):
                    ref_id = str(item.get('ref_id'))
                    if ref_id in all_news_map:
                        item.update({"link": all_news_map[ref_id]['link'], "date": all_news_map[ref_id]['date']})
                        final_parts["part1"].append(item)
                for item in ai_results.get('part2_micro', []):
                    ref_id = str(item.get('ref_id'))
                    if ref_id in all_news_map:
                        item.update({"link": all_news_map[ref_id]['link'], "date": all_news_map[ref_id]['date']})
                        final_parts["part2"].append(item)
        except: pass

    # 안전장치 (데이터 부족 시 원본 사용)
    if not final_parts['part1'] and not final_parts['part2']:
        for item in macro_news[:5]: final_parts['part1'].append({"headline": item['title'], "summary": item['desc'], "implication": "원문 참조", "link": item['link'], "date": item['date']})
        for item in micro_news[:5]: final_parts['part2'].append({"headline": item['title'], "summary": item['desc'], "implication": "원문 참조", "link": item['link'], "date": item['date']})

    # HTML 생성 및 발송 (생략 방지 위해 핵심 로직만 기술)
    def create_card(item, color):
        return f'<div style="margin-bottom:25px;padding-bottom:20px;border-bottom:1px dashed #ddd;"><div style="font-size:11px;color:#888;margin-bottom:4px;">{item["date"]}</div><h3 style="margin:0 0 8px 0;font-size:17px;font-weight:700;"><a href="{item["link"]}" target="_blank" style="text-decoration:none;color:#111;">{item["headline"]}</a></h3><p style="margin:0 0 10px 0;font-size:14px;color:#555;">{item["summary"]}</p><div style="background-color:{color};padding:10px 12px;border-radius:4px;font-size:13px;font-weight:600;">💡 Insight: <span style="font-weight:400;">{item["implication"]}</span></div></div>'

    html_p1 = "".join([create_card(i, "#E3F2FD") for i in final_parts['part1']])
    html_p2 = "".join([create_card(i, "#FFF3E0") for i in final_parts['part2']])

    final_html = f'<html><body style="font-family:sans-serif;max-width:680px;margin:0 auto;padding:40px 20px;"><div style="text-align:center;border-bottom:3px solid #ED1C24;padding-bottom:20px;margin-bottom:40px;"><p style="font-size:11px;font-weight:700;color:#666;letter-spacing:2px;">WEEKLY STRATEGIC REPORT</p><h1 style="font-size:28px;font-weight:900;">EXECUTIVE <span style="color:#ED1C24;">INTELLIGENCE</span></h1><p style="font-size:12px;color:#888;">{display_date} | 성명재 매니저</p></div><div style="background:#f9f9f9;padding:15px;border-radius:8px;margin-bottom:30px;font-size:12px;color:#555;text-align:center;"><span style="font-weight:bold;">🤖 AI Strategic Keywords:</span><br>{", ".join(dynamic_keys["macro_keywords"])} / {", ".join(dynamic_keys["micro_keywords"])}</div><div style="margin-bottom:50px;"><h2 style="color:#00483A;">PART 1. MACRO</h2>{html_p1}</div><div><h2 style="color:#ED1C24;">PART 2. MICRO</h2>{html_p2}</div></body></html>'

    msg = MIMEMultipart()
    msg['From'] = f"Luca (Strategy Consultant) <{user_email}>"
    msg['To'] = user_email
    msg['Subject'] = f"[{display_date}] 주간 경영전략 브리핑 (Fixed Version)"
    msg.attach(MIMEText(final_html, 'html'))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(user_email, app_password)
        server.sendmail(user_email, user_email, msg.as_string())
    print("🚀 발송 성공!")

if __name__ == "__main__":
    run_final_autonomous_briefing()
