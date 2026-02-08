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
# 2. [NEW] AI가 이번 주 검색 키워드를 스스로 기획하는 함수
# -----------------------------------------------------------
def generate_dynamic_keywords(api_key):
    print("🧠 AI가 이번 주 핵심 검색 키워드를 기획 중...")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    # 30년 차 전략 임원 페르소나 주입
    prompt = f"""
    당신은 30년 경력의 대기업 전략기획 및 경영지원 총괄 사장입니다.
    오늘 날짜({datetime.datetime.now().strftime('%Y-%m-%d')}) 기준으로, 
    이번 주에 반드시 챙겨봐야 할 **'네이버 뉴스 검색용 키워드'**를 기획하세요.

    [조건]
    1. **MACRO (거시)**: 경제, 정치, 글로벌 트렌드, 기술 변화 등 (3개)
    2. **MICRO (식품/제조/인사)**: 식품산업, 제조업 현장, 노동법, 조직문화 등 (3개)
    3. 키워드는 네이버 검색이 잘 되도록 "2026년 금리 전망", "식품업계 푸드테크 트렌드" 처럼 구체적인 명사형으로 작성하세요.

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
            if result:
                print(f"✅ AI 기획 키워드: {result}")
                return result
    except Exception as e:
        print(f"키워드 생성 실패: {e}")
    
    # 실패 시 기본 키워드 (Fallback) - 콤마 수정 및 최적화 완료
    print("⚠️ AI 기획 실패 -> 기본(Fallback) 키워드 사용")
    return {
        "macro_keywords": [
            "경제 전망 금리", 
            "글로벌 기업 경영 혁신 사례", 
            "생성형 AI 비즈니스 전략", 
            "소비 시장 트렌드 분석", 
            "글로벌 공급망 리스크 대응"
        ],
        "micro_keywords": [
            "식품산업 푸드테크 기술 동향",
            "제조업 중대재해처벌법 판례",
            "생산직 인력 채용 운영 전략",
            "HR 조직문화 혁신 사례",
            "통상임금 성과급 이슈",
            "고용노동부 노동 정책"
        ]
    }
    }

# -----------------------------------------------------------
# 3. 뉴스 수집 (AI가 만든 키워드로 검색)
# -----------------------------------------------------------
def fetch_news_dynamic(keywords, target_type):
    client_id = os.environ.get('NAVER_CLIENT_ID')
    client_secret = os.environ.get('NAVER_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        return []

    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret
    }
    
    collected_news = []
    seen_titles = set()
    
    for kw in keywords:
        # 검색어 뒤에 '전망', '분석' 등을 붙여 퀄리티 보정
        final_query = kw
        if target_type == "MACRO": final_query += " (전망 OR 분석 OR 시사점)"
        else: final_query += " (사례 OR 전략 OR 동향)"

        params = {"query": final_query, "display": 5, "sort": "sim"}
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
# 4. 메인 실행 로직
# -----------------------------------------------------------
def run_autonomous_briefing():
    api_key = os.environ.get('GEMINI_API_KEY')
    app_password = os.environ.get('GMAIL_APP_PASSWORD')
    user_email = "proposition97@gmail.com"

    today = datetime.datetime.now()
    display_date = today.strftime("%Y년 %m월 %d일")
    
    # [STEP 1] AI에게 이번 주 키워드 기획 요청
    dynamic_keys = generate_dynamic_keywords(api_key)
    
    print(f"[{display_date}] AI 기획 키워드로 뉴스 수집 시작...")
    
    # [STEP 2] 생성된 키워드로 뉴스 수집
    macro_news = fetch_news_dynamic(dynamic_keys['macro_keywords'], "MACRO")
    micro_news = fetch_news_dynamic(dynamic_keys['micro_keywords'], "MICRO")
    
    # 과부하 방지: 최신순 정렬 후 상위 10개씩만
    macro_news = sorted(macro_news, key=lambda x: x['date'], reverse=True)[:10]
    micro_news = sorted(micro_news, key=lambda x: x['date'], reverse=True)[:10]

    if not macro_news and not micro_news:
        print("⚠️ 뉴스 수집 실패")
        return

    # ID 매핑 및 Context 생성
    all_news_map = {}
    global_id = 1
    context_text = ""
    
    context_text += f"--- [PART 1: MACRO (Keywords: {', '.join(dynamic_keys['macro_keywords'])})] ---\n"
    for item in macro_news:
        item['id'] = str(global_id)
        all_news_map[str(global_id)] = item
        context_text += f"[ID:{global_id}] {item['title']} | {item['desc']}\n"
        global_id += 1
        
    context_text += f"\n--- [PART 2: MICRO (Keywords: {', '.join(dynamic_keys['micro_keywords'])})] ---\n"
    for item in micro_news:
        item['id'] = str(global_id)
        all_news_map[str(global_id)] = item
        context_text += f"[ID:{global_id}] {item['title']} | {item['desc']}\n"
        global_id += 1

    print(f"📡 수집된 {len(all_news_map)}개 데이터 분석 요청...")

    # [STEP 3] 최종 보고서 작성 (AI)
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    prompt = f"""
    당신은 오뚜기라면 경영진을 위한 30년 차 전략 고문입니다.
    이번 주에 검색된 뉴스를 바탕으로 **주간 경영 인사이트 리포트**를 작성하세요.

    [JSON 출력 양식]
    반드시 아래 포맷을 준수하세요. 
    
    {{
      "part1_macro": [
        {{
          "headline": "헤드라인 (30자 이내)",
          "summary": "핵심 내용",
          "implication": "경영 시사점 (1문장)",
          "ref_id": "ID번호"
        }}
      ],
      "part2_micro": [
        {{
          "headline": "헤드라인 (30자 이내)",
          "summary": "핵심 내용",
          "implication": "실무/현장 시사점 (1문장)",
          "ref_id": "ID번호"
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
            ai_results = extract_json_from_text(raw_text)
            
            if ai_results:
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
                
                if final_parts["part1"] or final_parts["part2"]:
                    ai_success = True
                    print("✅ AI 분석 및 매칭 완료")

        except Exception as e:
            print(f"AI 파싱 에러: {e}")

    # Fallback (AI 실패 시)
    if not ai_success or (not final_parts['part1'] and not final_parts['part2']):
        print("🚨 백업 데이터 사용")
        for item in macro_news[:4]:
            final_parts['part1'].append({
                "headline": item['title'], "summary": item['desc'], "implication": "원문 참조", "link": item['link'], "date": item['date']
            })
        for item in micro_news[:4]:
            final_parts['part2'].append({
                "headline": item['title'], "summary": item['desc'], "implication": "원문 참조", "link": item['link'], "date": item['date']
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
    
    # 이번 주 AI가 선정한 키워드 표시 (헤더 부분)
    keywords_display = f"""
    <div style="background:#f9f9f9; padding:15px; border-radius:8px; margin-bottom:30px; font-size:12px; color:#555; text-align:center;">
        <span style="font-weight:bold;">🤖 AI's Pick This Week:</span><br>
        {', '.join(dynamic_keys['macro_keywords'])} / {', '.join(dynamic_keys['micro_keywords'])}
    </div>
    """

    final_html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
    <body style="margin: 0; padding: 0; background-color: #ffffff; font-family: 'Helvetica Neue', Arial, sans-serif;">
        <div style="max-width: 680px; margin: 0 auto; padding: 40px 20px;">
            <div style="text-align: center; margin-bottom: 30px; border-bottom: 3px solid #ED1C24; padding-bottom: 20px;">
                <p style="font-size: 11px; font-weight: 700; color: #666; letter-spacing: 2px;">WEEKLY STRATEGIC REPORT</p>
                <h1 style="margin: 5px 0; font-size: 28px; font-weight: 900; color: #111;">
                    EXECUTIVE <span style="color: #ED1C24;">INTELLIGENCE</span>
                </h1>
                <p style="font-size: 12px; color: #888;">{display_date} &middot; 성명재 매니저</p>
            </div>

            {keywords_display}

            <div style="margin-bottom: 50px;">
                <div style="display: flex; align-items: center; margin-bottom: 20px;">
                    <div style="background:#00483A; color:#fff; font-size:12px; font-weight:bold; padding:4px 10px; border-radius:20px; margin-right:10px;">MACRO</div>
                    <h2 style="margin:0; font-size:20px; color:#00483A;">GLOBAL & ECONOMY</h2>
                </div>
                {html_part1 if html_part1 else "<p style='color:#666'>관련 뉴스 없음</p>"}
            </div>

            <div>
                <div style="display: flex; align-items: center; margin-bottom: 20px;">
                    <div style="background:#ED1C24; color:#fff; font-size:12px; font-weight:bold; padding:4px 10px; border-radius:20px; margin-right:10px;">MICRO</div>
                    <h2 style="margin:0; font-size:20px; color:#ED1C24;">INDUSTRY & HR</h2>
                </div>
                {html_part2 if html_part2 else "<p style='color:#666'>관련 뉴스 없음</p>"}
            </div>

            <div style="margin-top: 60px; padding-top: 20px; border-top: 1px solid #eee; text-align: center; font-size: 11px; color: #aaa;">
                <p>Automated by Autonomous AI Agent</p>
            </div>
        </div>
    </body>
    </html>
    """

    msg = MIMEMultipart()
    msg['From'] = f"Luca (AI Agent) <{user_email}>"
    msg['To'] = user_email
    msg['Subject'] = f"[{display_date}] 주간 경영전략 브리핑 (AI Autonomous Ver)"
    msg.attach(MIMEText(final_html, 'html'))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(user_email, app_password)
        server.sendmail(user_email, user_email, msg.as_string())
    print(f"✅ 자율주행(Autonomous) 리포트 발송 완료!")

if __name__ == "__main__":
    run_autonomous_briefing()
