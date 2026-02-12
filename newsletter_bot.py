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
# 2. 뉴스 수집 (범용 키워드 사용)
# -----------------------------------------------------------
def fetch_news_silent(category):
    client_id = os.environ.get('NAVER_CLIENT_ID')
    client_secret = os.environ.get('NAVER_CLIENT_SECRET')
    
    if not client_id or not client_secret: return []

    # 가장 넓은 범위의 키워드로 무조건 데이터 확보
    if category == "MACRO":
        keywords = ["경제 전망", "금리", "환율", "글로벌 기업", "비즈니스 트렌드"]
    else:
        keywords = ["식품산업", "오뚜기", "라면", "고용노동부", "임금 협상"]

    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
    
    collected = []
    seen = set()
    
    for kw in keywords:
        try:
            # 검색어 단순화 (복잡한 연산자 제거)
            resp = requests.get(url, headers=headers, params={"query": kw, "display": 5, "sort": "sim"})
            if resp.status_code == 200:
                items = resp.json().get('items', [])
                now = datetime.datetime.now(datetime.timezone.utc)
                limit = now - datetime.timedelta(days=7) 
                
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
    
    # 최신순 정렬 후 상위 10개 반환
    return sorted(collected, key=lambda x: x['date'], reverse=True)[:10]

# -----------------------------------------------------------
# 3. 메인 실행 로직 (Silent Fallback 적용)
# -----------------------------------------------------------
def run_silent_fallback_bot():
    api_key = os.environ.get('GEMINI_API_KEY')
    app_password = os.environ.get('GMAIL_APP_PASSWORD')
    user_email = "proposition97@gmail.com"
    today = datetime.datetime.now().strftime("%Y년 %m월 %d일")
    
    print("1. 뉴스 수집 중...")
    macro_news = fetch_news_silent("MACRO")
    micro_news = fetch_news_silent("MICRO")
    
    # 데이터 준비
    ctx = "--- [MACRO NEWS] ---\n"
    for i, n in enumerate(macro_news): ctx += f"[M-{i}] {n['title']} | {n['desc']}\n"
    ctx += "\n--- [MICRO NEWS] ---\n"
    for i, n in enumerate(micro_news): ctx += f"[F-{i}] {n['title']} | {n['desc']}\n"

    print(f"수집 완료: Macro({len(macro_news)}), Micro({len(micro_news)})")

    # AI 분석 요청
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    prompt = f"""
    당신은 대기업 HR 전략 애널리스트입니다. 아래 뉴스 데이터를 바탕으로
    관리직 임원이 즉시 의사결정에 활용할 수 있는 전략 브리핑을 JSON으로 작성하세요.

    [역할]
    - 불필요한 수식어 제거, 숫자·리스크·의사결정 중심 서술
    - "뉴스 요약"이 아닌 "임원 보고용 전략 브리핑" 톤

    [조건]
    1. PART 1 (MACRO): M-로 시작하는 뉴스 중 가장 경영 임팩트가 큰 3개 선정
    2. PART 2 (MICRO): F-로 시작하는 뉴스 중 가장 HR·사업 임팩트가 큰 3개 선정
    3. 각 항목은 반드시 아래 4단계로 작성:
       - fact: 핵심 사실 2문장 이내 (수치 포함 권장)
       - strategic_meaning: 기업 경영·노동시장 관점 의미 해석 (2~3문장)
       - business_impact: 인건비·채용·조직운영·생산성·노무리스크 등 우리 회사 영향 구체화 (2~3문장)
       - recommended_actions: 관리직이 이번 주 바로 검토할 실행 항목 2~3개 (측정 가능한 지표 또는 의사결정 포인트 포함)

    [JSON 포맷 - 반드시 이 구조를 따를 것]
    {{
      "part1": [
        {{
          "headline": "간결한 전략 헤드라인",
          "fact": "핵심 사실 요약",
          "strategic_meaning": "경영·노동시장 관점 해석",
          "business_impact": "우리 회사에 미칠 구체적 영향",
          "recommended_actions": ["실행항목1", "실행항목2", "실행항목3"],
          "ref_id": "M-0"
        }}
      ],
      "part2": [
        {{
          "headline": "간결한 전략 헤드라인",
          "fact": "핵심 사실 요약",
          "strategic_meaning": "경영·노동시장 관점 해석",
          "business_impact": "우리 회사에 미칠 구체적 영향",
          "recommended_actions": ["실행항목1", "실행항목2"],
          "ref_id": "F-0"
        }}
      ]
    }}

    데이터:
    {ctx}
    """
    
    final_p1 = []
    final_p2 = []
    ai_success = False
    
    # AI 시도
    if macro_news or micro_news:
        try:
            res = requests.post(api_url, headers={'Content-Type': 'application/json'}, data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}))
            if res.status_code == 200:
                parsed = extract_json_from_text(res.json()['candidates'][0]['content']['parts'][0]['text'])
                if parsed:
                    for item in parsed.get('part1', []):
                        idx_str = str(item.get('ref_id', '')).replace('M-', '')
                        if idx_str.isdigit() and int(idx_str) < len(macro_news):
                            n = macro_news[int(idx_str)]
                            item.update({'link': n['link'], 'date': n['date']})
                            final_p1.append(item)
                    for item in parsed.get('part2', []):
                        idx_str = str(item.get('ref_id', '')).replace('F-', '')
                        if idx_str.isdigit() and int(idx_str) < len(micro_news):
                            n = micro_news[int(idx_str)]
                            item.update({'link': n['link'], 'date': n['date']})
                            final_p2.append(item)
                    ai_success = True
        except Exception as e:
            print(f"AI Error: {e}")

    # AI 실패 시 원본 뉴스를 4단계 구조에 맞춰 투입
    if not final_p1:
        print("⚠️ PART 1 AI 실패 -> 원본 뉴스 투입")
        for n in macro_news[:4]:
            final_p1.append({
                "headline": n['title'],
                "fact": n['desc'],
                "strategic_meaning": "AI 분석 미제공 — 원문 기사를 직접 확인하세요.",
                "business_impact": "원문 기사를 통해 자체 영향도를 평가하시기 바랍니다.",
                "recommended_actions": ["원문 기사 검토 후 관련 부서 공유"],
                "link": n['link'],
                "date": n['date']
            })

    if not final_p2:
        print("⚠️ PART 2 AI 실패 -> 원본 뉴스 투입")
        for n in micro_news[:4]:
            final_p2.append({
                "headline": n['title'],
                "fact": n['desc'],
                "strategic_meaning": "AI 분석 미제공 — 원문 기사를 직접 확인하세요.",
                "business_impact": "원문 기사를 통해 자체 영향도를 평가하시기 바랍니다.",
                "recommended_actions": ["원문 기사 검토 후 관련 부서 공유"],
                "link": n['link'],
                "date": n['date']
            })

    # HTML 생성 - 4단계 전략 브리핑 카드
    def mk_card(i, accent_color):
        actions_html = ""
        for idx, action in enumerate(i.get('recommended_actions', []), 1):
            actions_html += f'<div style="margin-bottom:4px;font-size:12px;color:#222;">☑ {action}</div>'

        return f"""<div style="margin-bottom:24px;padding:0;border-left:4px solid {accent_color};background:#FAFAFA;border-radius:4px;">
        <div style="padding:16px 18px 14px;">
            <div style="font-size:10px;color:#999;margin-bottom:6px;letter-spacing:0.5px;">{i['date']}</div>
            <h3 style="margin:0 0 14px 0;font-size:15px;font-weight:700;line-height:1.4;"><a href="{i['link']}" target="_blank" style="text-decoration:none;color:#111;">{i['headline']}</a></h3>
            <div style="margin-bottom:12px;padding:10px 12px;background:#FFF;border-radius:4px;">
                <div style="font-size:10px;font-weight:700;color:{accent_color};margin-bottom:4px;letter-spacing:0.5px;">FACT</div>
                <div style="font-size:13px;color:#333;line-height:1.5;">{i.get('fact', '')}</div>
            </div>
            <div style="margin-bottom:12px;padding:10px 12px;background:#FFF;border-radius:4px;">
                <div style="font-size:10px;font-weight:700;color:{accent_color};margin-bottom:4px;letter-spacing:0.5px;">STRATEGIC MEANING</div>
                <div style="font-size:13px;color:#333;line-height:1.5;">{i.get('strategic_meaning', '')}</div>
            </div>
            <div style="margin-bottom:12px;padding:10px 12px;background:#FFF;border-radius:4px;">
                <div style="font-size:10px;font-weight:700;color:{accent_color};margin-bottom:4px;letter-spacing:0.5px;">BUSINESS IMPACT ON OUR COMPANY</div>
                <div style="font-size:13px;color:#333;line-height:1.5;">{i.get('business_impact', '')}</div>
            </div>
            <div style="padding:10px 12px;background:#FFF;border-radius:4px;">
                <div style="font-size:10px;font-weight:700;color:{accent_color};margin-bottom:6px;letter-spacing:0.5px;">RECOMMENDED HR ACTION</div>
                {actions_html}
            </div>
        </div></div>"""

    html = f"""
    <html><body style="font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif;max-width:640px;margin:0 auto;padding:20px;background:#FFF;">
        <div style="text-align:center;border-bottom:3px solid #ED1C24;padding-bottom:15px;margin-bottom:10px;">
            <h1 style="margin:0;font-size:22px;letter-spacing:1px;">WEEKLY HR <span style="color:#ED1C24;">STRATEGIC BRIEF</span></h1>
            <p style="font-size:11px;color:#888;margin:6px 0 0;">{today} | 성명재 매니저</p>
        </div>
        <div style="text-align:center;margin-bottom:30px;padding:8px;background:#F5F5F5;border-radius:4px;">
            <span style="font-size:11px;color:#666;">본 브리핑은 경영진 의사결정 지원을 위해 작성되었습니다</span>
        </div>

        <h2 style="color:#00483A;font-size:14px;border-bottom:2px solid #00483A;padding-bottom:6px;letter-spacing:1px;">PART 1. MACRO ENVIRONMENT</h2>
        {'' if not final_p1 else ''.join([mk_card(x, '#00483A') for x in final_p1])}
        {'' if final_p1 else '<p style="color:#999;font-size:12px;">금주 주요 거시경제 뉴스가 없습니다.</p>'}

        <h2 style="color:#ED1C24;margin-top:40px;font-size:14px;border-bottom:2px solid #ED1C24;padding-bottom:6px;letter-spacing:1px;">PART 2. INDUSTRY &amp; HR</h2>
        {'' if not final_p2 else ''.join([mk_card(x, '#ED1C24') for x in final_p2])}
        {'' if final_p2 else '<p style="color:#999;font-size:12px;">금주 주요 산업/HR 뉴스가 없습니다.</p>'}

        <div style="margin-top:50px;text-align:center;font-size:10px;color:#bbb;border-top:1px solid #eee;padding-top:12px;">
            Automated Strategic Brief | Powered by AI Analysis
        </div>
    </body></html>
    """

    msg = MIMEMultipart()
    msg['From'] = f"Luca (Brief) <{user_email}>"
    msg['To'] = user_email
    msg['Subject'] = f"[{today}] Weekly HR Strategic Brief"
    msg.attach(MIMEText(html, 'html'))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(user_email, app_password)
        server.sendmail(user_email, user_email, msg.as_string())
    print("✅ 발송 완료")

if __name__ == "__main__":
    run_silent_fallback_bot()
