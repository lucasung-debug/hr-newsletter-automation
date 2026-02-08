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
# 2. AI 키워드 기획 (업계 특화 강화)
# -----------------------------------------------------------
def generate_dynamic_keywords(api_key):
    print("🧠 AI가 이번 주 검색 키워드를 기획 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    # Micro 키워드가 너무 기술(Tech)로 빠지지 않도록 '식품/제조' 한정 강화
    prompt = f"""
    당신은 30년 경력의 식품 제조기업(오뚜기라면) 경영전략 사장입니다. 
    오늘({datetime.datetime.now().strftime('%Y-%m-%d')}) 기준, 경영진 필독 네이버 뉴스 검색 키워드를 기획하세요.

    [조건]
    1. **MACRO (거시경제)**: 금리, 환율, 글로벌 공급망, 지정학적 리스크 (3개)
    2. **MICRO (식품/제조/인사)**: 
       - 반드시 '식품산업', '라면/면류', '제조 현장 안전', '생산직 인사'와 관련된 구체적 키워드일 것.
       - '양자컴퓨터', '비트코인' 같은 일반 테크 제외. '푸드테크'는 가능.

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
    
    # Fallback (콤마 오류 수정됨)
    return {
        "macro_keywords": ["2026년 경제 전망 금리", "글로벌 공급망 리스크", "생성형 AI 비즈니스 전략"],
        "micro_keywords": ["식품산업 푸드테크 트렌드", "제조업 중대재해처벌법 판례", "생산직 통상임금 성과급"]
    }

# -----------------------------------------------------------
# 3. 뉴스 수집 (ID에 꼬리표 붙이기)
# -----------------------------------------------------------
def fetch_news_dynamic(keywords, prefix):
    client_id = os.environ.get('NAVER_CLIENT_ID')
    client_secret = os.environ.get('NAVER_CLIENT_SECRET')
    if not client_id or not client_secret: return []

    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
    
    collected_news = []
    seen_titles = set()
    
    for kw in keywords:
        params = {"query": kw, "display": 10, "sort": "sim"}
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
                                "id_prefix": prefix, # 출신 성분 (M 또는 F) 저장
                                "title": title, 
                                "link": item['originallink'] if item['originallink'] else item['link'],
                                "desc": clean_html(item['description']), 
                                "date": pub_date.strftime("%Y-%m-%d")
                            })
                            seen_titles.add(title)
        except: continue
    return collected_news

def run_hard_sorted_briefing():
    api_key = os.environ.get('GEMINI_API_KEY')
    app_password = os.environ.get('GMAIL_APP_PASSWORD')
    user_email = "proposition97@gmail.com"
    today = datetime.datetime.now()
    display_date = today.strftime("%Y년 %m월 %d일")
    
    # 1. 키워드 및 뉴스 수집
    dynamic_keys = generate_dynamic_keywords(api_key)
    
    # ID Prefix: M=Macro, F=Food/Field
    macro_news = fetch_news_dynamic(dynamic_keys['macro_keywords'], "M") 
    micro_news = fetch_news_dynamic(dynamic_keys['micro_keywords'], "F")
    
    # 최신순 상위 15개씩
    macro_news = sorted(macro_news, key=lambda x: x['date'], reverse=True)[:15]
    micro_news = sorted(micro_news, key=lambda x: x['date'], reverse=True)[:15]

    if not macro_news and not micro_news: return

    # 2. Context 생성 (ID에 접두사 포함)
    all_news_map = {}
    context_text = "--- [PART 1: MACRO CANDIDATES] ---\n"
    
    # Macro 뉴스 ID: M-1, M-2...
    for i, item in enumerate(macro_news):
        uid = f"M-{i+1}"
        all_news_map[uid] = item
        context_text += f"[ID:{uid}] {item['title']} | {item['desc']}\n"
        
    context_text += "\n--- [PART 2: MICRO CANDIDATES] ---\n"
    # Micro 뉴스 ID: F-1, F-2...
    for i, item in enumerate(micro_news):
        uid = f"F-{i+1}"
        all_news_map[uid] = item
        context_text += f"[ID:{uid}] {item['title']} | {item['desc']}\n"

    # 3. AI 분석 요청
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    prompt = f"""
    당신은 오뚜기라면 경영진을 위한 전략 컨설턴트입니다.
    제공된 뉴스([ID:M-...] 또는 [ID:F-...]) 중에서 핵심 아젠다 10개를 선정하세요.

    [작성 원칙]
    - PART 1에는 반드시 ID가 'M-'로 시작하는 뉴스만 넣으세요.
    - PART 2에는 반드시 ID가 'F-'로 시작하는 뉴스만 넣으세요.
    
    [JSON 출력 양식]
    {{
      "agenda_list": [
        {{
          "headline": "헤드라인 (30자)",
          "summary": "요약",
          "implication": "시사점",
          "ref_id": "M-1 또는 F-1" 
        }}
      ]
    }}
    데이터: {context_text}
    """
    
    response = requests.post(api_url, headers={'Content-Type': 'application/json'}, data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}))
    
    final_macro = []
    final_micro = []
    
    # 4. 강제 분류 로직 (Python Force Sorting)
    if response.status_code == 200:
        try:
            ai_results = extract_json_from_text(response.json()['candidates'][0]['content']['parts'][0]['text'])
            if ai_results and 'agenda_list' in ai_results:
                for item in ai_results['agenda_list']:
                    ref_id = str(item.get('ref_id'))
                    
                    if ref_id in all_news_map:
                        original = all_news_map[ref_id]
                        item['link'] = original['link']
                        item['date'] = original['date']
                        
                        # [핵심] ID 앞글자를 보고 강제로 방 배정
                        if ref_id.startswith("M"):
                            final_macro.append(item)
                        elif ref_id.startswith("F"):
                            final_micro.append(item)
        except: pass

    # 백업 (데이터 부족 시)
    if not final_macro:
        for item in macro_news[:5]: final_macro.append({"headline": item['title'], "summary": item['desc'], "implication": "원문 참조", "link": item['link'], "date": item['date']})
    if not final_micro:
        for item in micro_news[:5]: final_micro.append({"headline": item['title'], "summary": item['desc'], "implication": "원문 참조", "link": item['link'], "date": item['date']})

    # HTML 생성
    def create_card(item, color):
        return f'<div style="margin-bottom:25px;padding-bottom:20px;border-bottom:1px dashed #ddd;"><div style="font-size:11px;color:#888;margin-bottom:4px;">{item["date"]}</div><h3 style="margin:0 0 8px 0;font-size:17px;font-weight:700;"><a href="{item["link"]}" target="_blank" style="text-decoration:none;color:#111;">{item["headline"]}</a></h3><p style="margin:0 0 10px 0;font-size:14px;color:#555;">{item["summary"]}</p><div style="background-color:{color};padding:10px 12px;border-radius:4px;font-size:13px;font-weight:600;">💡 Insight: <span style="font-weight:400;">{item["implication"]}</span></div></div>'

    html_p1 = "".join([create_card(i, "#E3F2FD") for i in final_macro])
    html_p2 = "".join([create_card(i, "#FFF3E0") for i in final_micro])

    final_html = f'<html><body style="font-family:sans-serif;max-width:680px;margin:0 auto;padding:40px 20px;"><div style="text-align:center;border-bottom:3px solid #ED1C24;padding-bottom:20px;margin-bottom:40px;"><p style="font-size:11px;font-weight:700;color:#666;letter-spacing:2px;">WEEKLY STRATEGIC REPORT</p><h1 style="font-size:28px;font-weight:900;">EXECUTIVE <span style="color:#ED1C24;">INTELLIGENCE</span></h1><p style="font-size:12px;color:#888;">{display_date} | 성명재 매니저</p></div><div style="background:#f9f9f9;padding:15px;border-radius:8px;margin-bottom:30px;font-size:12px;color:#555;text-align:center;"><span style="font-weight:bold;">🤖 AI Strategic Keywords:</span><br>{", ".join(dynamic_keys["macro_keywords"])}<br>{", ".join(dynamic_keys["micro_keywords"])}</div><div style="margin-bottom:50px;"><h2 style="color:#00483A;">PART 1. MACRO</h2>{html_p1}</div><div><h2 style="color:#ED1C24;">PART 2. MICRO (Industry & HR)</h2>{html_p2}</div></body></html>'

    msg = MIMEMultipart()
    msg['From'] = f"Luca (Strategy Consultant) <{user_email}>"
    msg['To'] = user_email
    msg['Subject'] = f"[{display_date}] 주간 경영전략 브리핑 (Fixed Classification)"
    msg.attach(MIMEText(final_html, 'html'))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(user_email, app_password)
        server.sendmail(user_email, user_email, msg.as_string())
    print("🚀 분류 오류 수정 완료! 발송 성공!")

if __name__ == "__main__":
    run_hard_sorted_briefing()
