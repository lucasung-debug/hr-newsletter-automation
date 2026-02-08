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

# -----------------------------------------------------------
# 2. 뉴스 수집 (인사이트 & 동향 중심 키워드 강화)
# -----------------------------------------------------------
def fetch_news_by_category(target_type):
    client_id = os.environ.get('NAVER_CLIENT_ID')
    client_secret = os.environ.get('NAVER_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        return []

    # [핵심 변경] 단순 명사가 아니라 '전망', '사례', '전략' 등을 붙여 분석 기사 유도
    if target_type == "MACRO":
        keywords = [
            "국내외 경제 금리 환율 전망",         # 단순 지표 X -> 미래 전망 O
            "글로벌 기업 경영 혁신 리더십 성공 사례",     # 단순 소식 X -> 벤치마킹 사례 O
            "생성형 AI 비즈니스 적용 트렌드 및 전략",     # 단순 기술 X -> 적용 전략 O
            "인구 구조 변화 소비 시장 트렌드 분석",       # 단순 통계 X -> 분석 리포트 O
            "글로벌 공급망 리스크 관리 대응 전략"         # 단순 이슈 X -> 대응책 O
        ]
    else: # MICRO
        keywords = [
            "식품산업 푸드테크 최신 기술 동향",           # 단순 뉴스 X -> 기술 동향 O
            "제조업 중대재해처벌법 대응 및 판례 분석",    # 단순 사고 X -> 판례 분석 O
            "통상임금 성과급 제도 개선 사례",             # 단순 협상 X -> 제도 개선 사례 O
            "제조업 생산직 인력 운영 및 채용 전략",       # 단순 공고 X -> 운영 전략 O
            "최신 HR 조직문화 혁신 기업 사례"             # 단순 행사 X -> 혁신 사례 O
        ]

    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret
    }
    
    collected_news = []
    seen_titles = set()
    
    for kw in keywords:
        # 정확도순(sim)으로 검색하여 '분석적'인 기사를 우선 노출
        params = {"query": kw, "display": 10, "sort": "sim"}
        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                items = response.json().get('items', [])
                now = datetime.datetime.now(datetime.timezone.utc)
                seven_days_ago = now - datetime.timedelta(days=7)

                for item in items:
                    try:
                        pub_date = parsedate_to_datetime(item['pubDate'])
                        if pub_date >= seven_days_ago:
                            title = clean_html(item['title'])
                            if title not in seen_titles:
                                collected_news.append({
                                    "type": target_type,
                                    "title": title,
                                    "link": item['originallink'] if item['originallink'] else item['link'],
                                    "desc": clean_html(item['description']),
                                    "date": pub_date.strftime("%Y-%m-%d")
                                })
                                seen_titles.add(title)
                    except:
                        continue
        except:
            continue
            
    return collected_news

# -----------------------------------------------------------
# 3. 메인 실행 로직 (안전장치 포함)
# -----------------------------------------------------------
def run_insight_briefing():
    api_key = os.environ.get('GEMINI_API_KEY')
    app_password = os.environ.get('GMAIL_APP_PASSWORD')
    user_email = "proposition97@gmail.com"

    today = datetime.datetime.now()
    display_date = today.strftime("%Y년 %m월 %d일")
    
    print(f"[{display_date}] 인사이트 뉴스 수집 중...")
    
    macro_news = fetch_news_by_category("MACRO")
    micro_news = fetch_news_by_category("MICRO")
    
    if not macro_news and not micro_news:
        print("⚠️ 수집 실패")
        return

    all_news_map = {}
    global_id = 1
    context_text = ""
    
    context_text += "--- [PART 1: MACRO] ---\n"
    for item in macro_news:
        item['id'] = str(global_id)
        all_news_map[str(global_id)] = item
        context_text += f"[ID:{global_id}] {item['title']} | {item['desc']}\n"
        global_id += 1
        
    context_text += "\n--- [PART 2: MICRO] ---\n"
    for item in micro_news:
        item['id'] = str(global_id)
        all_news_map[str(global_id)] = item
        context_text += f"[ID:{global_id}] {item['title']} | {item['desc']}\n"
        global_id += 1

    print(f"📡 총 {len(all_news_map)}개 기사 분석 요청...")

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    prompt = f"""
    당신은 오뚜기라면 경영진을 위한 전략 컨설턴트입니다.
    제공된 뉴스 데이터를 바탕으로 **총 10개의 핵심 아젠다**를 선정하세요.

    [JSON 출력 양식]
    'ref_id'는 제공된 데이터의 [ID] 번호입니다.
    
    {{
      "part1_macro": [
        {{
          "headline": "헤드라인 (30자 이내)",
          "summary": "핵심 내용 요약",
          "implication": "경영 시사점",
          "ref_id": "1"
        }}
      ],
      "part2_micro": [
        {{
          "headline": "헤드라인 (30자 이내)",
          "summary": "핵심 내용 요약",
          "implication": "실무 시사점",
          "ref_id": "10"
        }}
      ]
    }}

    [데이터]
    {context_text}
    """
    
    response = requests.post(api_url, headers={'Content-Type': 'application/json'}, 
                             data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}))
    
    final_parts = {"part1": [], "part2": []}
    ai_success = False

    if response.status_code == 200:
        try:
            raw_text = response.json()['candidates'][0]['content']['parts'][0]['text']
            clean_json = raw_text.replace("```json", "").replace("```", "").strip()
            ai_results = json.loads(clean_json)
            
            for item in ai_results.get('part1_macro', []):
                ref_id = str(item.get('ref_id'))
                if ref_id in all_news_map:
                    original = all_news_map[ref_id]
                    item['link'] = original['link']
                    item['date'] = original['date']
                    final_parts["part1"].append(item)

            for item in ai_results.get('part2_micro', []):
                ref_id = str(item.get('ref_id'))
                if ref_id in all_news_map:
                    original = all_news_map[ref_id]
                    item['link'] = original['link']
                    item['date'] = original['date']
                    final_parts["part2"].append(item)
            
            ai_success = True
            print("✅ AI 분석 및 ID 매칭 성공")

        except Exception as e:
            print(f"⚠️ AI 파싱 에러: {e}")
            ai_success = False

    # 안전장치 (Fallback)
    if not ai_success or (not final_parts['part1'] and not final_parts['part2']):
        print("🚨 백업 데이터 사용")
        for item in macro_news[:5]:
            final_parts['part1'].append({
                "headline": item['title'],
                "summary": item['desc'][:80] + "...",
                "implication": "원문 기사를 참고하여 주십시오.",
                "link": item['link'],
                "date": item['date']
            })
        for item in micro_news[:5]:
            final_parts['part2'].append({
                "headline": item['title'],
                "summary": item['desc'][:80] + "...",
                "implication": "주요 HR/산업 이슈입니다.",
                "link": item['link'],
                "date": item['date']
            })

    # HTML 조립
    def create_card(item, color):
        return f"""
        <div style="margin-bottom: 25px; padding-bottom: 20px; border-bottom: 1px dashed #ddd;">
            <div style="font-size: 11px; color: #888; margin-bottom: 4px;">{item['date']}</div>
            <h3 style="margin: 0 0 8px 0; font-size: 17px; font-weight: 700; line-height: 1.4;">
                <a href="{item['link']}" target="_blank" style="text-decoration: none; color: #111;">
                    {item['headline']}
                </a>
            </h3>
            <p style="margin: 0 0 10px 0; font-size: 14px; color: #555; line-height: 1.5;">{item['summary']}</p>
            <div style="background-color: {color}; padding: 10px 12px; border-radius: 4px; font-size: 13px; color: #222; font-weight: 600;">
                💡 Insight: <span style="font-weight: 400;">{item['implication']}</span>
            </div>
        </div>
        """

    html_part1 = "".join([create_card(item, "#E3F2FD") for item in final_parts['part1']])
    html_part2 = "".join([create_card(item, "#FFF3E0") for item in final_parts['part2']])
    
    if not html_part1: html_part1 = "<p style='color:#666; font-size:13px;'>금주 주요 거시경제 뉴스가 없습니다.</p>"
    if not html_part2: html_part2 = "<p style='color:#666; font-size:13px;'>금주 주요 산업/HR 뉴스가 없습니다.</p>"

    final_html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
    <body style="margin: 0; padding: 0; background-color: #ffffff; font-family: 'Helvetica Neue', Arial, sans-serif;">
        <div style="max-width: 680px; margin: 0 auto; padding: 40px 20px;">
            <div style="text-align: center; margin-bottom: 40px; border-bottom: 3px solid #ED1C24; padding-bottom: 20px;">
                <p style="font-size: 11px; font-weight: 700; color: #666; letter-spacing: 2px;">WEEKLY STRATEGIC REPORT</p>
                <h1 style="margin: 5px 0; font-size: 28px; font-weight: 900; color: #111;">
                    MANAGEMENT & HR <span style="color: #ED1C24;">BRIEF</span>
                </h1>
                <p style="font-size: 12px; color: #888;">{display_date} &middot; 성명재 매니저</p>
            </div>

            <div style="margin-bottom: 50px;">
                <div style="display: flex; align-items: center; margin-bottom: 20px;">
                    <div style="background:#00483A; color:#fff; font-size:12px; font-weight:bold; padding:4px 10px; border-radius:20px; margin-right:10px;">PART 1</div>
                    <h2 style="margin:0; font-size:20px; color:#00483A;">MACRO & SOCIETY</h2>
                </div>
                {html_part1}
            </div>

            <div>
                <div style="display: flex; align-items: center; margin-bottom: 20px;">
                    <div style="background:#ED1C24; color:#fff; font-size:12px; font-weight:bold; padding:4px 10px; border-radius:20px; margin-right:10px;">PART 2</div>
                    <h2 style="margin:0; font-size:20px; color:#ED1C24;">INDUSTRY & HR FOCUS</h2>
                </div>
                {html_part2}
            </div>

            <div style="margin-top: 60px; padding-top: 20px; border-top: 1px solid #eee; text-align: center; font-size: 11px; color: #aaa;">
                <p>Automated by Luca's Agent</p>
            </div>
        </div>
    </body>
    </html>
    """

    msg = MIMEMultipart()
    msg['From'] = f"Luca (HR Strategy) <{user_email}>"
    msg['To'] = user_email
    msg['Subject'] = f"[{display_date}] 주간 경영전략 및 HR 핵심 브리핑 (Vol.{datetime.datetime.now().isocalendar()[1]})"
    msg.attach(MIMEText(final_html, 'html'))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(user_email, app_password)
        server.sendmail(user_email, user_email, msg.as_string())
    print(f"✅ 리포트 발송 완료 (인사이트 키워드 적용)")

if __name__ == "__main__":
    run_insight_briefing()
