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
# 2. 뉴스 수집 (지속 가능한 불변의 키워드 전략)
# -----------------------------------------------------------
def fetch_news_by_category(target_type):
    client_id = os.environ.get('NAVER_CLIENT_ID')
    client_secret = os.environ.get('NAVER_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        return []

    # [핵심 변경] 연도(Year)나 특정 사건을 제거하고, '테마' 위주로 변경
    if target_type == "MACRO":
        # PART 1: 경영 환경 (BCG View) - 언제 검색해도 그 주의 핫이슈가 걸리도록 설계
        keywords = [
            "국내외 경제 전망 및 금리 환율",      # 경제 지표는 매주 변하므로 항상 유효
            "글로벌 기업 경영 혁신 및 리더십",     # 타사 사례 벤치마킹
            "인공지능 AI 기술 비즈니스 적용",      # 향후 수년간 지속될 메가 트렌드
            "인구 구조 변화와 소비 시장 트렌드",   # 저출산/고령화 등 사회 변화
            "글로벌 공급망 이슈 및 지정학적 리스크" # 전쟁, 무역 분쟁 등 대외 변수
        ]
    else: # MICRO
        # PART 2: 직무 전문성 (HR Expert View) - 제조업 HR의 본질적 고민
        keywords = [
            "식품산업 최신 동향 및 푸드테크",      # 오뚜기 본업 (항상 최신 기술/트렌드 수집)
            "제조업 중대재해처벌법 및 안전 보건",  # 법적 리스크 (판례는 계속 나옴)
            "노동법 이슈 및 통상임금 성과급",      # 보상/노무 이슈 (매년 반복되는 사이클)
            "생산직 채용 및 인력 운영 전략",       # 제조업의 영원한 숙제 (인력난)
            "최신 HR 트렌드 및 조직문화 혁신"      # 평가, 보상, 문화 등 HR 일반
        ]

    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret
    }
    
    collected_news = []
    seen_titles = set()
    
    for kw in keywords:
        # 정확도순(sim)으로 검색하면, 해당 키워드 내에서 '지금 가장 뜨거운' 기사가 올라옴
        params = {"query": kw, "display": 10, "sort": "sim"}
        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                items = response.json().get('items', [])
                
                # 날짜 필터링 (최근 7일)
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
# 3. 메인 실행 로직
# -----------------------------------------------------------
def run_perennial_briefing():
    api_key = os.environ.get('GEMINI_API_KEY')
    app_password = os.environ.get('GMAIL_APP_PASSWORD')
    user_email = "proposition97@gmail.com"

    today = datetime.datetime.now()
    display_date = today.strftime("%Y년 %m월 %d일")
    
    print(f"[{display_date}] Sustainable Insight 수집 중...")
    
    macro_news = fetch_news_by_category("MACRO")
    micro_news = fetch_news_by_category("MICRO")
    
    if not macro_news and not micro_news:
        print("⚠️ 데이터 수집 실패")
        return

    all_news_map = {}
    global_id = 1
    context_text = ""
    
    context_text += "--- [PART 1: MACRO (Management View)] ---\n"
    for item in macro_news:
        item['id'] = global_id
        all_news_map[global_id] = item
        context_text += f"[ID:{global_id}] {item['title']} | {item['desc']}\n"
        global_id += 1
        
    context_text += "\n--- [PART 2: MICRO (HR Expert View)] ---\n"
    for item in micro_news:
        item['id'] = global_id
        all_news_map[global_id] = item
        context_text += f"[ID:{global_id}] {item['title']} | {item['desc']}\n"
        global_id += 1

    print(f"📡 총 {len(all_news_map)}개 후보 기사 분석 중...")

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    # 프롬프트: 시의성에 구애받지 않는 통찰력 요구
    prompt = f"""
    당신은 오뚜기라면 경영진을 위한 전략 컨설턴트입니다.
    제공된 뉴스 데이터를 바탕으로 **총 10개의 핵심 아젠다**를 선정하세요.

    [선정 기준]
    - 이번 주에 발생한 뉴스 중, 경영진이 반드시 알아야 할 '변화의 신호(Signal)'를 포착하세요.
    - 단순 사건 전달보다는, 미래 전략 수립에 필요한 인사이트 위주로 선정하세요.

    [JSON 출력 양식]
    'ref_id'는 제공된 데이터의 [ID] 번호입니다.
    
    {{
      "part1_macro": [
        {{
          "headline": "거시적 관점의 헤드라인 (30자)",
          "summary": "핵심 내용 요약",
          "implication": "경영진을 위한 거시적 시사점",
          "ref_id": 123
        }},
        ... (5개)
      ],
      "part2_micro": [
        {{
          "headline": "직무/산업 특화 헤드라인 (30자)",
          "summary": "핵심 내용 요약",
          "implication": "오뚜기라면 현장 적용을 위한 제언",
          "ref_id": 456
        }},
        ... (5개)
      ]
    }}

    [데이터]
    {context_text}
    """
    
    response = requests.post(api_url, headers={'Content-Type': 'application/json'}, 
                             data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}))
    
    final_parts = {"part1": [], "part2": []}
    
    if response.status_code == 200:
        try:
            raw_text = response.json()['candidates'][0]['content']['parts'][0]['text']
            clean_json = raw_text.replace("```json", "").replace("```", "").strip()
            ai_results = json.loads(clean_json)
            
            for item in ai_results.get('part1_macro', []):
                original = all_news_map.get(item['ref_id'])
                if original:
                    item['link'] = original['link']
                    item['date'] = original['date']
                    final_parts["part1"].append(item)
                    
            for item in ai_results.get('part2_micro', []):
                original = all_news_map.get(item['ref_id'])
                if original:
                    item['link'] = original['link']
                    item['date'] = original['date']
                    final_parts["part2"].append(item)
        except Exception as e:
            print(f"파싱 에러: {e}")
            return

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
                <p style="font-size:13px; color:#666; margin-bottom:20px;">경제 전망, 글로벌 트렌드, 사회 변화 등 거시적 경영 환경 (5건)</p>
                {html_part1}
            </div>

            <div>
                <div style="display: flex; align-items: center; margin-bottom: 20px;">
                    <div style="background:#ED1C24; color:#fff; font-size:12px; font-weight:bold; padding:4px 10px; border-radius:20px; margin-right:10px;">PART 2</div>
                    <h2 style="margin:0; font-size:20px; color:#ED1C24;">INDUSTRY & HR FOCUS</h2>
                </div>
                <p style="font-size:13px; color:#666; margin-bottom:20px;">식품/제조 산업 동향 및 인사/노무 핵심 실무 이슈 (5건)</p>
                {html_part2}
            </div>

            <div style="margin-top: 60px; padding-top: 20px; border-top: 1px solid #eee; text-align: center; font-size: 11px; color: #aaa;">
                <p>Strategic Intelligence for Ottogi Ramyun Leadership<br>Automated by Luca's Agent</p>
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
    print(f"✅ 유지보수 프리(Free) 리포트 발송 완료!")

if __name__ == "__main__":
    run_perennial_briefing()
