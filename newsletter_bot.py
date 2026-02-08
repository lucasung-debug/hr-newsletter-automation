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
# 2. 뉴스 수집 (고정 키워드 + 안전한 쿼리)
# -----------------------------------------------------------
def fetch_news_fixed(category):
    client_id = os.environ.get('NAVER_CLIENT_ID')
    client_secret = os.environ.get('NAVER_CLIENT_SECRET')
    if not client_id or not client_secret: return []

    # [안전장치 1] 검증된 키워드만 사용 (AI 생성 X)
    if category == "MACRO":
        keywords = ["2026년 경제 전망", "글로벌 경영 전략", "AI 비즈니스 트렌드", "미국 금리 환율 영향", "기업 ESG 경영 사례"]
    else:
        keywords = ["식품산업 푸드테크", "제조업 중대재해처벌법", "생산직 통상임금 성과급", "식품업계 글로벌 전략", "HR 조직문화 혁신"]

    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
    
    collected = []
    seen = set()
    
    for kw in keywords:
        # 쿼리: 키워드 + (전망/분석) -노이즈
        query = f"{kw} (전망 OR 분석 OR 사례) -포토 -인사 -부고"
        try:
            resp = requests.get(url, headers=headers, params={"query": query, "display": 5, "sort": "sim"})
            if resp.status_code == 200:
                items = resp.json().get('items', [])
                now = datetime.datetime.now(datetime.timezone.utc)
                limit = now - datetime.timedelta(days=7) # 최근 7일
                
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
        except: continue
    
    # 최신순 정렬 후 상위 10개만 리턴
    return sorted(collected, key=lambda x: x['date'], reverse=True)[:10]

# -----------------------------------------------------------
# 3. 메인 실행 로직 (절대 실패하지 않는 구조)
# -----------------------------------------------------------
def run_final_stable_bot():
    api_key = os.environ.get('GEMINI_API_KEY')
    app_password = os.environ.get('GMAIL_APP_PASSWORD')
    user_email = "proposition97@gmail.com"
    today = datetime.datetime.now().strftime("%Y년 %m월 %d일")
    
    print("1. 뉴스 수집 중...")
    macro_news = fetch_news_fixed("MACRO")
    micro_news = fetch_news_fixed("MICRO")
    
    # 데이터 준비
    ctx = "--- [MACRO NEWS] ---\n"
    for i, n in enumerate(macro_news): ctx += f"[M-{i}] {n['title']} | {n['desc']}\n"
    ctx += "\n--- [MICRO NEWS] ---\n"
    for i, n in enumerate(micro_news): ctx += f"[F-{i}] {n['title']} | {n['desc']}\n"

    print("2. AI 분석 요청...")
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    prompt = f"""
    경영진 보고용 뉴스 브리핑을 작성하세요.
    
    [조건]
    1. MACRO(M-) 뉴스 중 3~4개 선정.
    2. MICRO(F-) 뉴스 중 3~4개 선정.
    3. 없는 내용은 지어내지 말 것.
    
    [JSON 포맷]
    {{
      "part1": [ {{"headline": "...", "summary": "...", "implication": "...", "ref_id": "M-0"}} ],
      "part2": [ {{"headline": "...", "summary": "...", "implication": "...", "ref_id": "F-0"}} ]
    }}
    데이터: {ctx}
    """
    
    final_p1 = []
    final_p2 = []
    
    try:
        res = requests.post(api_url, headers={'Content-Type': 'application/json'}, data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}))
        if res.status_code == 200:
            parsed = extract_json_from_text(res.json()['candidates'][0]['content']['parts'][0]['text'])
            if parsed:
                # ID 매칭
                for item in parsed.get('part1', []):
                    idx = int(item['ref_id'].replace('M-', ''))
                    if idx < len(macro_news):
                        n = macro_news[idx]
                        item.update({'link': n['link'], 'date': n['date']})
                        final_p1.append(item)
                for item in parsed.get('part2', []):
                    idx = int(item['ref_id'].replace('F-', ''))
                    if idx < len(micro_news):
                        n = micro_news[idx]
                        item.update({'link': n['link'], 'date': n['date']})
                        final_p2.append(item)
    except Exception as e:
        print(f"AI Error: {e}")

    # [안전장치 2] AI가 실패했거나 결과가 비어있으면 원본 뉴스 강제 투입 (절대 빈칸 방지)
    if not final_p1:
        print("⚠️ PART 1 비상 백업 가동")
        for n in macro_news[:4]:
            final_p1.append({"headline": n['title'], "summary": n['desc'], "implication": "원문 기사를 참고하세요.", "link": n['link'], "date": n['date']})
            
    if not final_p2:
        print("⚠️ PART 2 비상 백업 가동")
        for n in micro_news[:4]:
            final_p2.append({"headline": n['title'], "summary": n['desc'], "implication": "원문 기사를 참고하세요.", "link": n['link'], "date": n['date']})

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
        <div style="margin-top:50px;text-align:center;font-size:11px;color:#aaa;">Automated by Stable Bot</div>
    </body></html>
    """

    msg = MIMEMultipart()
    msg['From'] = f"Luca (Stable Bot) <{user_email}>"
    msg['To'] = user_email
    msg['Subject'] = f"[{today}] 주간 경영전략 브리핑 (안정화 버전)"
    msg.attach(MIMEText(html, 'html'))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(user_email, app_password)
        server.sendmail(user_email, user_email, msg.as_string())
    print("✅ 발송 완료")

if __name__ == "__main__":
    run_final_stable_bot()
