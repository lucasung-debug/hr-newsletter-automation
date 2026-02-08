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
# 2. 네이버 뉴스 수집 (광범위한 경영 스캔)
# -----------------------------------------------------------
def fetch_strategic_news():
    client_id = os.environ.get('NAVER_CLIENT_ID')
    client_secret = os.environ.get('NAVER_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        return []

    # C-Level이 봐야 할 4대 핵심 도메인 키워드 (광범위 스캔)
    # 검색어 뒤에 주요 경제지/전문지 위주로 필터링 유도
    search_categories = [
        {"domain": "MACRO & POLITICS", "kw": "2026년 한국 경제 전망 금리 정책"},
        {"domain": "INDUSTRY & MARKET", "kw": "식품산업 트렌드 유통 혁신 경쟁사 동향"},
        {"domain": "TECH & FUTURE", "kw": "제조업 AI DX 스마트팩토리 푸드테크"},
        {"domain": "PEOPLE & RISK", "kw": "노동법 개정 중대재해 성과급 조직문화"},
        {"domain": "GLOBAL INSIGHT", "kw": "글로벌 경영 트렌드 CEO 인사이트"}
    ]

    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret
    }
    
    all_raw_news = []
    seen_titles = set()
    global_id_counter = 1 # 링크 매핑을 위한 고유 ID

    # 각 카테고리별로 데이터를 긁어옴
    for category in search_categories:
        # 정확도순으로 상위 15개씩 넉넉히 수집
        params = {"query": category['kw'], "display": 15, "sort": "sim"}
        
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
                            
                            # 중복 제거
                            if title not in seen_titles:
                                all_raw_news.append({
                                    "id": global_id_counter, # [핵심] 고유 ID 부여
                                    "domain": category['domain'],
                                    "title": title,
                                    "link": item['originallink'] if item['originallink'] else item['link'],
                                    "desc": clean_html(item['description']),
                                    "date": pub_date.strftime("%Y-%m-%d")
                                })
                                seen_titles.add(title)
                                global_id_counter += 1
                    except:
                        continue
        except Exception as e:
            print(f"Error fetching {category['domain']}: {e}")
            continue

    return all_raw_news

# -----------------------------------------------------------
# 3. 메인 실행 로직 (BCG 컨설턴트 모드)
# -----------------------------------------------------------
def run_bcg_executive_briefing():
    # 환경 변수 로드
    api_key = os.environ.get('GEMINI_API_KEY')
    app_password = os.environ.get('GMAIL_APP_PASSWORD')
    user_email = "proposition97@gmail.com"

    today = datetime.datetime.now()
    display_date = today.strftime("%Y년 %m월 %d일")
    
    print(f"[{display_date}] 경영 브리핑용 데이터 수집 중...")
    
    # 1. 뉴스 데이터 수집
    raw_news_list = fetch_strategic_news()
    
    if not raw_news_list:
        print("⚠️ 데이터 수집 실패. API 설정을 확인하세요.")
        return

    # 2. AI에게 보낼 Context 구성 (ID 포함)
    # AI가 'ID'를 보고 선택하게 함으로써 링크 매칭 오류를 원천 차단
    context_text = ""
    for item in raw_news_list:
        context_text += f"[ID:{item['id']}] 도메인:{item['domain']} | 제목:{item['title']} | 내용:{item['desc']}\n"

    print(f"📡 수집된 후보 기사 {len(raw_news_list)}개 중 핵심 아젠다 선별 요청 중...")

    # 3. Gemini 프롬프트 (BCG 컨설턴트 페르소나 주입)
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    prompt = f"""
    당신은 세계적인 전략 컨설팅 펌 BCG(Boston Consulting Group)의 수석 파트너 컨설턴트입니다.
    당신의 클라이언트는 '오뚜기라면'의 C-Level 경영진(CEO, CHRO, CFO)입니다.

    제공된 뉴스 데이터([ID:숫자] 형식) 중에서, 이번 주 주간 경영회의에서 반드시 논의되어야 할 **'가장 중요한 7~8개의 아젠다'**를 선별하여 보고서를 작성하세요.

    [선별 기준]
    1. **Strategic Impact**: 단순 사건 사고가 아닌, 경영 전략에 영향을 미치는 거시적 변화나 경쟁사 동향.
    2. **Diverse Coverage**: 경제, 산업, 기술, 조직문화 등 다양한 분야를 안배할 것.
    3. **Insight-Driven**: 단순 요약이 아니라, '그래서 우리(오뚜기라면)가 무엇을 고민해야 하는가?'를 제시할 것.

    [작성 포맷 - JSON Only]
    반드시 아래 JSON 포맷으로 출력하세요. **'ref_id'에는 해당 기사의 [ID] 번호를 정수형으로 정확히 적어야 합니다.** (링크 연결용)

    [
      {{
        "section": "MACRO / INDUSTRY / TECH / PEOPLE 중 택1",
        "headline": "경영진을 위한 한 줄 헤드라인 (전문적 어조)",
        "executive_summary": "현상 분석 및 핵심 요약 (2문장)",
        "strategic_implication": "오뚜기라면 경영진을 위한 전략적 시사점 및 제언 (1문장)",
        "ref_id": 12 
      }},
      ... (총 7~8개 항목)
    ]

    [입력 데이터]
    {context_text}
    """
    
    response = requests.post(api_url, headers={'Content-Type': 'application/json'}, 
                             data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}))
    
    final_agenda_list = []
    
    if response.status_code == 200:
        try:
            raw_text = response.json()['candidates'][0]['content']['parts'][0]['text']
            clean_json = raw_text.replace("```json", "").replace("```", "").strip()
            ai_results = json.loads(clean_json)
            
            # [링크 매핑 로직] AI가 선택한 ID를 이용해 원본 리스트에서 링크와 날짜를 찾아옴
            # 리스트를 딕셔너리로 변환하여 검색 속도 향상
            news_map = {item['id']: item for item in raw_news_list}
            
            for res in ai_results:
                target_id = res.get('ref_id')
                if target_id in news_map:
                    original = news_map[target_id]
                    res['link'] = original['link'] # 원본 링크 복원
                    res['date'] = original['date']
                    final_agenda_list.append(res)
                else:
                    # AI가 ID를 잘못 뱉었을 경우 (예외처리)
                    continue
                    
        except Exception as e:
            print(f"AI 응답 파싱 에러: {e}")
            # 에러 시 디버깅용 더미 데이터
            final_agenda_list = [{
                "section": "SYSTEM", "headline": "분석 시스템 에러", 
                "executive_summary": "데이터 파싱 중 문제가 발생했습니다.", 
                "strategic_implication": "관리자에게 문의바랍니다.", 
                "link": "#", "date": display_date
            }]
    else:
        print(f"API 호출 에러: {response.status_code}")
        return

    # -----------------------------------------------------------
    # 4. HTML 리포트 디자인 (BCG 스타일 - Clean & Professional)
    # -----------------------------------------------------------
    html_content = ""
    
    for item in final_agenda_list:
        # 섹션별 컬러 코딩 (미세한 차이)
        section_color = "#00483A" # BCG Green 계열 느낌의 짙은 녹색
        if "PEOPLE" in item['section']: section_color = "#8B0000" # HR은 붉은 계열
        
        html_content += f"""
        <div style="margin-bottom: 40px; page-break-inside: avoid;">
            <div style="border-left: 4px solid {section_color}; padding-left: 15px; margin-bottom: 10px;">
                <span style="font-size: 10px; font-weight: 800; color: #888; letter-spacing: 1px;">{item['section']} &middot; {item['date']}</span>
                <h3 style="margin: 5px 0 10px 0; font-size: 20px; font-weight: 700; color: #000; line-height: 1.3;">
                    <a href="{item['link']}" target="_blank" style="text-decoration: none; color: #000; transition: color 0.2s;">
                        {item['headline']}
                    </a>
                </h3>
            </div>
            
            <div style="padding-left: 19px;">
                <p style="margin: 0 0 12px 0; font-size: 14px; color: #444; line-height: 1.6; text-align: justify;">
                    {item['executive_summary']}
                </p>
                <div style="background-color: #f8f9fa; padding: 12px 15px; border-radius: 4px; font-size: 13px; color: #333; line-height: 1.5;">
                    <span style="font-weight: 700; color: {section_color};">⚡ Strategic Implication:</span><br>
                    {item['strategic_implication']}
                </div>
            </div>
        </div>
        """

    final_html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
    <body style="margin: 0; padding: 0; background-color: #ffffff; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #333;">
        <div style="max-width: 700px; margin: 0 auto; padding: 50px 30px;">
            
            <div style="border-bottom: 2px solid #000; padding-bottom: 20px; margin-bottom: 50px;">
                <div style="display: flex; justify-content: space-between; align-items: flex-end;">
                    <div>
                        <p style="font-size: 11px; font-weight: 700; color: #666; letter-spacing: 2px; margin-bottom: 5px;">WEEKLY EXECUTIVE BRIEFING</p>
                        <h1 style="margin: 0; font-size: 32px; font-weight: 900; letter-spacing: -1px; color: #000;">
                            MANAGEMENT <span style="color: #ED1C24;">AGENDA</span>.
                        </h1>
                    </div>
                    <div style="text-align: right;">
                        <p style="margin: 0; font-size: 12px; font-weight: 600; color: #000;">{display_date}</p>
                        <p style="margin: 0; font-size: 11px; color: #888;">Prepared by Luca</p>
                    </div>
                </div>
            </div>

            <div>
                {html_content}
            </div>

            <div style="margin-top: 80px; border-top: 1px solid #eee; padding-top: 20px; text-align: center; font-size: 11px; color: #999;">
                <p>CONFIDENTIAL: FOR INTERNAL EXECUTIVE REVIEW ONLY<br>
                Powered by Naver Search API & Gemini Pro 2.0</p>
            </div>
        </div>
    </body>
    </html>
    """

    # 5. 발송
    msg = MIMEMultipart()
    msg['From'] = f"Luca (Strategy Consultant) <{user_email}>"
    msg['To'] = user_email
    msg['Subject'] = f"[{display_date}] 주간 경영전략 회의 아젠다 (Management Briefing)"
    msg.attach(MIMEText(final_html, 'html'))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(user_email, app_password)
        server.sendmail(user_email, user_email, msg.as_string())
    print(f"✅ 경영전략 리포트 발송 완료!")

if __name__ == "__main__":
    run_bcg_executive_briefing()
