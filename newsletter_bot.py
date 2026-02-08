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
# 1. 유틸리티 및 안전장치 함수
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
# 2. AI 키워드 기획
# -----------------------------------------------------------
def generate_dynamic_keywords(api_key):
    print("🧠 AI가 키워드 기획 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    prompt = f"""
    당신은 오뚜기라면 전략기획 임원입니다. 오늘({datetime.datetime.now().strftime('%Y-%m-%d')}) 기준,
    경영진 보고용 뉴스 검색 키워드를 기획하세요.

    [조건]
    1. MACRO: 경제/금융, 글로벌, 기술 (3개)
    2. MICRO: 식품/제조, 인사/노무, 오뚜기 관련 (3개)
    
    [출력 양식(JSON)]
    {{ "macro_keywords": ["..."], "micro_keywords": ["..."] }}
    """
    try:
        response = requests.post(url, headers={'Content-Type': 'application/json'}, data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}))
        if response.status_code == 200:
            res = extract_json_from_text(response.json()['candidates'][0]['content']['parts'][0]['text'])
            if res: return res
    except: pass
    
    # 실패 시 기본 키워드
    return {
        "macro_keywords": ["2026년 경제 전망", "글로벌 공급망", "AI 비즈니스 트렌드"],
        "micro_keywords": ["식품산업 푸드테크", "제조업 중대재해처벌법", "생산직 성과급 임금"]
    }

# -----------------------------------------------------------
# 3. 뉴스 수집 (0건 방지 로직 추가)
# -----------------------------------------------------------
def fetch_news_safe(keywords, prefix, backup_keywords):
    client_id = os.environ.get('NAVER_CLIENT_ID')
    client_secret = os.environ.get('NAVER_CLIENT_SECRET')
    if not client_id or not client_secret: return []

    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
    
    collected = []
    seen = set()
    
    # 1차 시도: AI 키워드
    target_kws = keywords
    
    # 검색 실행 함수
    def search(kws):
        res_list = []
        for kw in kws:
            try:
                # 분석적 기사를 위해 '전망', '사례' 등 추가
                query = kw + (" (전망 OR 분석 OR 사례)" if "오뚜기" not in kw else "")
                resp = requests.get(url, headers=headers, params={"query": query, "display": 8, "sort": "sim"})
                if resp.status_code == 200:
                    items = resp.json().get('items', [])
                    now = datetime.datetime.now(datetime.timezone.utc)
                    week_ago = now - datetime.timedelta(days=7)
                    for item in items:
                        try:
                            pd = parsedate_to_datetime(item['pubDate'])
                            if pd >= week_ago:
                                t = clean_html(item['title'])
                                if t not in seen:
                                    res_list.append({
                                        "id_prefix": prefix, "title": t,
                                        "link": item['originallink'] or item['link'],
                                        "desc": clean_html(item['description']),
                                        "date": pd.strftime("%Y-%m-%d")
                                    })
                                    seen.add(t)
                        except: continue
            except: continue
        return res_list

    collected = search(target_kws)

    # [핵심] 결과가 너무 적으면 비상용 키워드로 재검색
    if len(collected) < 3:
        print(f"⚠️ {prefix} 섹션 데이터 부족. 비상 키워드 투입!")
        collected += search(backup_keywords)
    
    return collected

# -----------------------------------------------------------
# 4. 메인 로직
# -----------------------------------------------------------
def run_failproof_briefing():
    api_key = os.environ.get('GEMINI_API_KEY')
    app_password = os.environ.get('GMAIL_APP_PASSWORD')
    user_email = "proposition97@gmail.com"
    today = datetime.datetime.now().strftime("%Y년 %m월 %d일")
    
    # 1. 키워드 기획
    d_keys = generate_dynamic_keywords(api_key)
    
    # 2. 데이터 수집 (백업 키워드 준비)
    macro_backup = ["경제 전망", "환율 금리", "대기업 경영"]
    micro_backup = ["오뚜기", "라면", "식품업계", "임금 협상", "노동부"]
    
    macro_news = fetch_news_safe(d_keys['macro_keywords'], "M", macro_backup)
    micro_news = fetch_news_safe(d_keys['micro_keywords'], "F", micro_backup)
    
    # 입력 데이터 양 제한 (AI 과부하 방지: 각 10개)
    macro_news = sorted(macro_news, key=lambda x: x['date'], reverse=True)[:10]
    micro_news = sorted(micro_news, key=lambda x: x['date'], reverse=True)[:10]
    
    # 3. Context 생성
    news_map = {}
    ctx = "--- [PART 1: MACRO] ---\n"
    for i, n in enumerate(macro_news):
        uid = f"M-{i+1}"
        n['uid'] = uid
        news_map[uid] = n
        ctx += f"[ID:{uid}] {n['title']}\n"
        
    ctx += "\n--- [PART 2: MICRO] ---\n"
    for i, n in enumerate(micro_news):
        uid = f"F-{i+1}"
        n['uid'] = uid
        news_map[uid] = n
        ctx += f"[ID:{uid}] {n['title']}\n"

    # 4. AI 분석 (분리형 JSON 스키마 사용)
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    prompt = f"""
    오뚜기라면 경영진을 위한 주간 브리핑을 작성하세요.
    
    [필수 조건]
    1. PART 1(MACRO)은 ID가 'M'으로 시작하는 기사 중 4~5개 선정.
    2. PART 2(MICRO)는 ID가 'F'으로 시작하는 기사 중 4~5개 선정.
    3. 각 파트는 반드시 채워져야 합니다.

    [JSON 형식]
    {{
      "part1": [ {{"headline": "...", "summary": "...", "implication": "...", "ref_id": "M-1"}} ],
      "part2": [ {{"headline": "...", "summary": "...", "implication": "...", "ref_id": "F-1"}} ]
    }}
    데이터: {ctx}
    """
    
    res = requests.post(api_url, headers={'Content-Type': 'application/json'}, data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}))
    
    final_p1, final_p2 = [], []
    
    if res.status_code == 200:
        try:
            parsed = extract_json_from_text(res.json()['candidates'][0]['content']['parts'][0]['text'])
            if parsed:
                # ID 기반 강제 매핑
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

    # 5. 최후의 보루 (비어있으면 강제 채움)
    if not final_p1:
        for n in macro_news[:4]: final_p1.append({"headline": n['title'], "summary": n['desc'], "implication": "원문 참조", "link": n['link'], "date": n['date']})
    if not final_p2:
        for n in micro_news[:4]: final_p2.append({"headline": n['title'], "summary": n['desc'], "implication": "원문 참조", "link": n['link'], "date": n['date']})

    # 6. HTML 생성
    def mk_card(i, bg):
        return f'<div style="margin-bottom:20px;padding-bottom:15px;border-bottom:1px dashed #ddd;"><div style="font-size:11px;color:#888;">{i["date"]}</div><h3 style="margin:5px 0;"><a href="{i["link"]}" target="_blank" style="color:#000;text-decoration:none;">{i["headline"]}</a></h3><p style="font-size:13px;color:#444;">{i["summary"]}</p><div style="background:{bg};padding:8px;border-radius:4px;font-size:12px;font-weight:bold;">💡 Insight: <span style="font-weight:normal;">{i["implication"]}</span></div></div>'

    html = f"""
    <html><body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px;">
        <div style="text-align:center;border-bottom:3px solid #E60012;padding-bottom:15px;margin-bottom:30px;">
            <h1 style="margin:0;color:#000;">WEEKLY <span style="color:#E60012;">INSIGHT</span></h1>
            <p style="font-size:12px;color:#666;">{today} | 성명재 매니저</p>
        </div>
        
        <div style="margin-bottom:40px;">
            <h2 style="color:#00483A;border-bottom:2px solid #00483A;padding-bottom:5px;">PART 1. MACRO</h2>
            {''.join([mk_card(x, '#E8F5E9') for x in final_p1])}
        </div>
        
        <div>
            <h2 style="color:#E60012;border-bottom:2px solid #E60012;padding-bottom:5px;">PART 2. MICRO (Industry & HR)</h2>
            {''.join([mk_card(x, '#FFEBEE') for x in final_p2])}
        </div>
        
        <div style="margin-top:40px;text-align:center;font-size:11px;color:#999;border-top:1px solid #eee;padding-top:20px;">
            Powered by Luca's AI Agent
        </div>
    </body></html>
    """

    msg = MIMEMultipart()
    msg['From'] = f"Luca (AI) <{user_email}>"
    msg['To'] = user_email
    msg['Subject'] = f"[{today}] 주간 경영전략 브리핑 (Fail-Proof Ver)"
    msg.attach(MIMEText(html, 'html'))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(user_email, app_password)
        server.sendmail(user_email, user_email, msg.as_string())
    print("🚀 발송 완료")

if __name__ == "__main__":
    run_failproof_briefing()
