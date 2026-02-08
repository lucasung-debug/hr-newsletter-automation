import requests
import json
import datetime
import smtplib
import os
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def clean_html(raw_html):
    cleanr = re.compile('<.*?>|&quot;|&apos;|&gt;|&lt;')
    return re.sub(cleanr, '', raw_html)

def get_naver_news_premium(keyword):
    client_id = os.environ.get('NAVER_CLIENT_ID')
    client_secret = os.environ.get('NAVER_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        return []

    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret
    }
    # 베테랑 관리자를 위해 '정확도(sim)' 위주로 3개 엄선
    params = {"query": keyword, "display": 3, "sort": "sim"}

    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            items = response.json().get('items', [])
            news_list = []
            for item in items:
                news_list.append({
                    "title": clean_html(item['title']),
                    "link": item['originallink'] if item['originallink'] else item['link'],
                    "desc": clean_html(item['description']),
                    "pubDate": item['pubDate']
                })
            return news_list
        return []
    except Exception:
        return []

def run_premium_insight_report():
    # 1. 환경 설정
    api_key = os.environ.get('GEMINI_API_KEY')
    app_password = os.environ.get('GMAIL_APP_PASSWORD')
    user_email = "proposition97@gmail.com"

    today = datetime.datetime.now()
    display_date = today.strftime("%Y년 %m월 %d일")
    
    # 2. [전략적 키워드] 20년 차 인사 관리자/임원용 High-Level 키워드
    keywords = [
        "식품산업 경영환경 인사전략",     # 산업 동향
        "제조업 중대재해 판례 가이드",    # 리스크 관리 (판례 중심)
        "성과급 통상임금 대법원 판결",    # 임금/보상 이슈 (가장 민감)
        "한국 거시경제 제조업 고용지표",  # 경제 흐름
        "글로벌 HR 트렌드 리스킬링",      # 미래 전략
        "2026년 개정 노동법 실무해설"     # 법적 준거성
    ]
    
    collected_data = {}
    print(f"[{display_date}] Premium Insight 수집 시작...")

    for kw in keywords:
        items = get_naver_news_premium(kw)
        if items:
            collected_data[kw] = items

    if not collected_data:
        print("⚠️ 수집된 데이터가 없습니다.")
        return

    # 3. AI 심층 분석 요청 (JSON 구조화)
    news_context = ""
    for kw, items in collected_data.items():
        news_context += f"\n[주제: {kw}]\n"
        for item in items:
            news_context += f"- 기사: {item['title']} / 내용: {item['desc']}\n"

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    # 프롬프트: '해설'과 '판례 분석'을 강조
    prompt = f"""
    당신은 오뚜기라면의 20년 차 인사 책임자(CHRO)를 보좌하는 수석 전문위원 'Luca'입니다.
    수집된 뉴스를 분석하여 다음 구조의 JSON 데이터로 출력하세요.

    [분석 가이드]
    1. 단순 요약이 아닌, **'경영적 시사점'**과 **'법적 쟁점(판례)'** 위주로 분석할 것.
    2. 특히 성과급, 통상임금 이슈는 대법원 판결 흐름을 짚어줄 것.
    3. 톤앤매너: 냉철하고 전문적인 비즈니스 톤.

    [JSON 출력 양식]
    [
      {{
        "category": "주제 카테고리 (예: 노무 리스크, 글로벌 동향)",
        "headline": "인사이트가 담긴 헤드라인 (30자 이내)",
        "summary": "핵심 사실 1문장",
        "insight": "오뚜기라면 인사팀을 위한 실무 제언 또는 법적 해석 (2문장)",
        "keyword": "관련 키워드 1개 (예: Legal, Global, Wage)"
      }},
      ... (총 5~6개 아이템 선정)
    ]
    
    뉴스 데이터:
    {news_context}
    
    오직 JSON 리스트만 출력하세요. 마크다운 제외.
    """
    
    print("🤖 AI 심층 분석 중...")
    response = requests.post(api_url, headers={'Content-Type': 'application/json'}, 
                             data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}))
    
    ai_data = []
    if response.status_code == 200:
        raw_text = response.json()['candidates'][0]['content']['parts'][0]['text']
        clean_json = raw_text.replace("```json", "").replace("```", "").strip()
        try:
            ai_data = json.loads(clean_json)
        except:
            ai_data = [{"category": "System", "headline": "분석 데이터 로드 실패", "summary": "원문 링크를 확인해주세요.", "insight": "API 응답 오류", "keyword": "Error"}]

    # 4. 미니멀리즘 HTML 조립 (Notion 스타일)
    # Python으로 디자인을 통제하여 깨짐 방지
    
    card_list_html = ""
    
    # 키워드별 뉴스 링크 매핑 (AI 결과와 매칭)
    # AI가 생성한 순서대로 매칭하되, 링크는 수집된 데이터 중 가장 관련성 높은 첫 번째 것을 사용한다고 가정
    # (더 정교한 매칭을 위해선 AI에게 링크도 같이 넘겨야 하나, 토큰 절약을 위해 간소화)
    
    all_links = [item['link'] for kw in collected_data for item in collected_data[kw]]
    
    for idx, item in enumerate(ai_data):
        # 링크 할당 (순환)
        link = all_links[idx % len(all_links)]
        
        # 카테고리별 포인트 컬러
        badge_color = "#333"
        if "노무" in item['category'] or "법" in item['category'] or "임금" in item['category']:
            badge_color = "#ED1C24" # 오뚜기 레드 (중요 이슈)
        elif "글로벌" in item['category'] or "경제" in item['category']:
            badge_color = "#0055AA" # 신뢰의 블루
            
        card_list_html += f"""
        <div style="margin-bottom: 30px; border-bottom: 1px solid #eee; padding-bottom: 25px;">
            <div style="font-size: 11px; font-weight: 700; color: {badge_color}; letter-spacing: 1px; margin-bottom: 8px; text-transform: uppercase;">
                {item['category']}
            </div>
            <h3 style="margin: 0 0 10px 0; font-size: 18px; font-weight: 600; line-height: 1.4;">
                <a href="{link}" target="_blank" style="text-decoration: none; color: #111; border-bottom: 1px solid transparent; transition: border-color 0.2s;">
                    {item['headline']} ↗
                </a>
            </h3>
            <p style="margin: 0 0 12px 0; font-size: 14px; color: #555; line-height: 1.6;">
                <span style="font-weight: 600; color: #333;">[Fact]</span> {item['summary']}
            </p>
            <div style="background-color: #f7f7f5; padding: 12px 15px; border-radius: 6px; font-size: 13px; color: #333; line-height: 1.6; border-left: 3px solid {badge_color};">
                <span style="font-weight: 700;">💡 Insight:</span> {item['insight']}
            </div>
        </div>
        """

    final_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin: 0; padding: 0; background-color: #ffffff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #333;">
        <div style="max-width: 640px; margin: 0 auto; padding: 40px 20px;">
            
            <div style="margin-bottom: 50px; padding-bottom: 20px; border-bottom: 2px solid #111;">
                <div style="font-size: 12px; font-weight: bold; color: #888; margin-bottom: 5px;">WEEKLY HR REPORT</div>
                <h1 style="margin: 0; font-size: 28px; font-weight: 800; letter-spacing: -0.5px; color: #111;">
                    HR <span style="color: #ED1C24;">Insight</span> Brief.
                </h1>
                <p style="margin: 10px 0 0 0; font-size: 14px; color: #666;">
                    {display_date} | 오뚜기라면 인사팀 성명재
                </p>
            </div>

            <div>
                {card_list_html}
            </div>

            <div style="margin-top: 60px; padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #999;">
                <p style="font-weight: bold; color: #666; margin-bottom: 10px;">📌 수집된 원문 소스 (Reference)</p>
                <ul style="list-style: none; padding: 0; margin: 0;">
                    {''.join([f'<li style="margin-bottom: 5px;"><a href="{item["link"]}" target="_blank" style="color: #999; text-decoration: none;">- {item["title"]}</a></li>' for kw in collected_data for item in collected_data[kw]][:5])}
                </ul>
                <p style="margin-top: 20px;">Automated by Ottogi Ramyun HR Bot (v3.0)</p>
            </div>
        </div>
    </body>
    </html>
    """

    # 5. 발송
    msg = MIMEMultipart()
    msg['From'] = f"Luca (HR Manager) <{user_email}>"
    msg['To'] = user_email
    msg['Subject'] = f"[{display_date}] 주간 HR 경영 인사이트 (성명재 매니저)"
    msg.attach(MIMEText(final_html, 'html'))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(user_email, app_password)
        server.sendmail(user_email, user_email, msg.as_string())
    print(f"✅ {display_date} 프리미엄 리포트 발송 완료!")

if __name__ == "__main__":
    run_premium_insight_report()
