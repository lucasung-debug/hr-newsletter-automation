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
# 2. 뉴스 수집 (장벽 제거 버전)
# -----------------------------------------------------------
def fetch_news_emergency(category):
    client_id = os.environ.get('NAVER_CLIENT_ID')
    client_secret = os.environ.get('NAVER_CLIENT_SECRET')
    
    # API 키가 없으면 빈 리스트 반환 -> 나중에 더미 데이터로 대체됨
    if not client_id or not client_secret: 
        print("⚠️ API Key가 없습니다.")
        return []

    # [변경] 검색어 조건을 다 빼고 가장 넓은 범위로 검색
    if category == "MACRO":
        keywords = ["경제 전망", "금리", "환율", "기업 경영"]
    else:
        keywords = ["식품산업", "오뚜기", "라면", "고용노동부"]

    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
    
    collected = []
    seen = set()
    
    for kw in keywords:
        # [변경] 복잡한 연산자 제거, 그냥 키워드만 던짐
        try:
            resp = requests.get(url, headers=headers, params={"query": kw, "display": 5, "sort": "sim"})
            if resp.status_code == 200:
                items = resp.json().get('items', [])
                now = datetime.datetime.now(datetime.timezone.utc)
                # [변경] 기간을 14일로 늘려서 하나라도 더 잡히게 함
                limit = now - datetime.timedelta(days=14) 
                
                for item in items:
                    try:
                        pd = parsedate_to_datetime(item['pubDate'])
                        if pd >= limit:
                            t = clean_html(item['title'])
                            if t not in seen:
                                collected.append({
                                    "title": t,
                                    "link": item['originallink'] or item['link'],
                                    "desc": clean_html(item['description']),
                                    "date": pd.strftime("%Y-%m-%d")
                                })
                                seen.add(t)
                    except: continue
        except Exception as e:
            print(f"API Error: {e}")
            continue
    
    return sorted(collected, key=lambda x: x['date'], reverse=True)[:10]

# -----------------------------------------------------------
# 3. 메인 실행 로직
# -----------------------------------------------------------
def run_ultimate_fallback():
    api_key = os.environ.get('GEMINI_API_KEY')
    app_password = os.environ.get('GMAIL_APP_PASSWORD')
    user_email = "proposition97@gmail.com"
    today = datetime.datetime.now().strftime("%Y년 %m월 %d일")
    
    print("1. 뉴스 수집 시도...")
    macro_news = fetch_news_emergency("MACRO")
    micro_news = fetch_news_emergency("MICRO")
    
    # 데이터 준비
    ctx = "--- [MACRO NEWS] ---\n"
    for i, n in enumerate(macro_news): ctx += f"[M-{i}] {n['title']} | {n['desc']}\n"
    ctx += "\n--- [MICRO NEWS] ---\n"
    for i, n in enumerate(micro_news): ctx += f"[F-{i}] {n['title']} | {n['desc']}\n"

    print(f"수집된 뉴스 개수: Macro({len(macro_news)}), Micro({len(micro_news)})")

    # AI 분석 요청
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    prompt = f"""
    뉴스 요약 리포트를 작성하세요.
    데이터가 부족하면 일반적인 경영 상식을 기반으로 작성하세요.

    [JSON 포맷]
    {{
      "part1": [ {{"headline": "...", "summary": "...", "implication": "...", "ref_id": "M-0"}} ],
      "part2": [ {{"headline": "...", "summary": "...", "implication": "...", "ref_id": "F-0"}} ]
    }}
    데이터: {ctx}
    """
    
    final_p1 = []
    final_p2 = []
    
    # AI 시도
    if macro_news or micro_news:
        try:
            res = requests.post(api_url, headers={'Content-Type': 'application/json'}, data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}))
            if res.status_code == 200:
                parsed = extract_json_from_text(res.json()['candidates'][0]['content']['parts'][0]['text'])
                if parsed:
                    for item in parsed.get('part1', []):
                        idx_str = str(item.get('ref_id', '')).replace('M-', '')
                        if idx_str.isdigit():
                            idx = int(idx_str)
                            if idx < len(macro_news):
                                n = macro_news[idx]
                                item.update({'link': n['link'], 'date': n['date']})
                                final_p1.append(item)
                    for item in parsed.get('part2', []):
                        idx_str = str(item.get('ref_id', '')).replace('F-', '')
                        if idx_str.isdigit():
                            idx = int(idx_str)
                            if idx < len(micro_news):
                                n = micro_news[idx]
                                item.update({'link': n['link'], 'date': n['date']})
                                final_p2.append(item)
        except Exception as e:
            print(f"AI Error: {e}")

    # [최후의 보루] 리스트가 여전히 비어있다면, 더미 데이터를 강제로 넣음
    # 이렇게 하면 API가 다 죽어도 메일 레이아웃은 나옴
    if not final_p1:
        print("⚠️ PART 1 데이터 없음 -> 강제 데이터 주입")
        final_p1.append({
            "headline": "[시스템 알림] 뉴스 데이터 수집 실패",
            "summary": "네이버 뉴스 API에서 데이터를 가져오지 못했습니다. API 설정이나 검색 키워드를 확인해주세요.",
            "implication": "System Check Required",
            "link": "https://www.naver.com",
            "date": today
        })
        # 수집된 원본이라도 있으면 넣기
        for n in macro_news[:3]:
             final_p1.append({"headline": n['title'], "summary": n['desc'], "implication": "원문 참조", "link": n['link'], "date": n['date']})

    if not final_p2:
        print("⚠️ PART 2 데이터 없음 -> 강제 데이터 주입")
        final_p2.append({
            "headline": "[시스템 알림] 뉴스 데이터 수집 실패",
            "summary": "관련된 최신 뉴스를 찾을 수 없습니다. 검색 기간을 늘리거나 키워드를 변경해야 합니다.",
            "implication": "Data Not Found",
            "link": "https://www.ottogi.co.kr",
            "date": today
        })
        for n in micro_news[:3]:
             final_p2.append({"headline": n['title'], "summary": n['desc'], "implication": "원문 참조", "link": n['link'], "date": n['date']})


    # HTML 생성
    def mk_card(i, bg):
        return f"""<div style="margin-bottom:20px;padding:15px;background:{bg};border-radius:8px;">
        <div style="font-size:11px;color:#888;margin-bottom:5px;">{i['date']}</div>
        <h3 style="margin:0 0 10px 0;font-size:16px;"><a href="{i['link']}" target="_blank" style="text-decoration:none;color:#111;">{i['headline']}</a></h3>
        <p style="margin:0 0 10px 0;font-size:13px;color:#555;">{i['summary']}</p>
        <div style="font-size:12px;font-weight:bold;color:#333;">💡 Insight: {i['implication']}</div></div>"""

    html = f"""
    <html><body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px;">
        <div style="text-align:center;border-bottom:3px solid #ED1C24;padding-bottom:15px;margin-bottom:30px;">
            <h1 style="margin:0;">WEEKLY <span style="color:#ED1C24;">BRIEF</span></h1>
            <p style="font-size:12px;color:#888;">{today} | 성명재 매니저</p>
        </div>
        <h2 style="color:#00483A;">PART 1. MACRO</h2>
        {''.join([mk_card(x, '#E8F5E9') for x in final_p1])}
        <h2 style="color:#ED1C24;margin-top:40px;">PART 2. MICRO</h2>
        {''.join([mk_card(x, '#FFEBEE') for x in final_p2])}
        <div style="margin-top:50px;text-align:center;font-size:11px;color:#aaa;">Automated by Ultimate Fallback Bot</div>
    </body></html>
    """

    msg = MIMEMultipart()
    msg['From'] = f"Luca (System) <{user_email}>"
    msg['To'] = user_email
    msg['Subject'] = f"[{today}] 주간 경영전략 브리핑 (긴급 복구)"
    msg.attach(MIMEText(html, 'html'))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(user_email, app_password)
        server.sendmail(user_email, user_email, msg.as_string())
    print("✅ 발송 완료")

if __name__ == "__main__":
    run_ultimate_fallback()
