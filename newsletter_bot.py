import requests
import json
import datetime
import smtplib
import os
import re
from email.utils import parsedate_to_datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def clean_html(raw_html):
    cleanr = re.compile('<.*?>|&quot;|&apos;|&gt;|&lt;')
    return re.sub(cleanr, '', raw_html)

def get_naver_content(keyword, category_type="NEWS"):
    client_id = os.environ.get('NAVER_CLIENT_ID')
    client_secret = os.environ.get('NAVER_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        return []

    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret
    }
    
    # 1. 검색어 전략: 인사이트 유도를 위한 쿼리 확장
    search_query = keyword
    if category_type == "INSIGHT":
        search_query += " (칼럼 OR 기고 OR 인사이트)"
    elif category_type == "INTERVIEW":
        search_query += " (인터뷰 OR 대담)"
    
    params = {"query": search_query, "display": 30, "sort": "sim"}

    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            items = response.json().get('items', [])
            filtered_content = []
            
            # 날짜 필터링 (최근 7일)
            now = datetime.datetime.now(datetime.timezone.utc)
            seven_days_ago = now - datetime.timedelta(days=7)

            for item in items:
                try:
                    pub_date = parsedate_to_datetime(item['pubDate'])
                    if pub_date >= seven_days_ago:
                        filtered_content.append({
                            "title": clean_html(item['title']),
                            "link": item['originallink'] if item['originallink'] else item['link'],
                            "desc": clean_html(item['description']),
                            "source": "Media",
                            "date": pub_date.strftime("%Y-%m-%d")
                        })
                        # 섹션별 2개만 엄선
                        if len(filtered_content) >= 2:
                            break
                except:
                    continue
            return filtered_content
        return []
    except Exception:
        return []

def run_executive_briefing_fixed():
    # 1. 환경 설정
    api_key = os.environ.get('GEMINI_API_KEY')
    app_password = os.environ.get('GMAIL_APP_PASSWORD')
    user_email = "proposition97@gmail.com"

    today = datetime.datetime.now()
    display_date = today.strftime("%Y년 %m월 %d일")
    
    # 2. [전략적 카테고리 구성] 경영진용 4대 필드
    search_targets = [
        # [Macro] 거시 경제 (뉴스)
        {"kw": "2026년 한국 경제 제조업 전망", "type": "NEWS", "label": "MACRO & INDUSTRY"},
        {"kw": "식품산업 글로벌 트렌드", "type": "NEWS", "label": "MACRO & INDUSTRY"},
        
        # [Management] 리더십 (칼럼)
        {"kw": "조직문화 리더십 혁신", "type": "INSIGHT", "label": "LEADERSHIP INSIGHT"},
        {"kw": "MZ세대 성과관리", "type": "INSIGHT", "label": "LEADERSHIP INSIGHT"},
        
        # [People] 인터뷰 (인터뷰)
        {"kw": "CEO 경영 철학", "type": "INTERVIEW", "label": "LEADERS VOICE"},
        {"kw": "혁신 기업 성공 사례", "type": "INTERVIEW", "label": "CASE STUDY"},

        # [Risk] 노무 (뉴스)
        {"kw": "통상임금 성과급 판례", "type": "NEWS", "label": "RISK MANAGEMENT"}
    ]
    
    collected_data = {}
    print(f"[{display_date}] 경영 브리핑 데이터 수집 중...")

    for target in search_targets:
        items = get_naver_content(target['kw'], target['type'])
        if items:
            if target['label'] not in collected_data:
                collected_data[target['label']] = []
            collected_data[target['label']].extend(items)

    if not collected_data:
        print("⚠️ 데이터 수집 실패")
        return

    # 3. AI 분석 요청 (링크 매핑 오류 해결 버전)
    context_text = ""
    for label, items in collected_data.items():
        context_text += f"\n[SECTION: {label}]\n"
        for item in items:
            # [핵심] AI에게 링크(URL)를 직접 전달
            context_text += f"- 제목: {item['title']} | 원문링크: {item['link']} | 내용: {item['desc']}\n"

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    prompt = f"""
    당신은 오뚜기라면의 C-Level 경영진을 위한 수석 보좌관 'Luca'입니다.
    수집된 정보를 바탕으로 **주간 경영 인사이트 리포트**를 JSON으로 작성하세요.

    [작성 원칙]
    1. **링크 유지**: 입력 데이터에 있는 '원문링크'를 JSON의 'link' 필드에 **그대로 복사**하세요. 절대 다른 링크를 만들거나 순서를 섞지 마세요.
    2. **관점(Perspective)**: 경영진에게 주는 영감(Inspiration)이나 경각심(Alert) 위주 서술.
    3. **Action**: 'Takeaway'를 한 줄 포함하세요.

    [JSON 출력 양식]
    [
      {{
        "section": "섹션명 (예: MACRO, LEADERSHIP)",
        "headline": "통찰력 있는 헤드라인 (30자)",
        "summary": "내용 요약 및 시사점 (2~3문장)",
        "key_takeaway": "경영진을 위한 한 줄 요약",
        "link": "입력 데이터에서 제공된 원문링크 (정확히 복사할 것)" 
      }},
      ... (섹션별 1~2개씩 선정)
    ]
    
    데이터:
    {context_text}
    오직 JSON 리스트만 출력하세요.
    """
    
    print("🤖 AI 경영 인사이트 도출 중...")
    response = requests.post(api_url, headers={'Content-Type': 'application/json'}, 
                             data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}))
    
    ai_data = []
    if response.status_code == 200:
        raw_text = response.json()['candidates'][0]['content']['parts'][0]['text']
        clean_json = raw_text.replace("```json", "").replace("```", "").strip()
        try:
            ai_data = json.loads(clean_json)
        except:
            ai_data = [{"section": "Error", "headline": "분석 실패", "summary": "원문 참조", "key_takeaway": "System Check", "link": "#"}]

    # 4. HTML 디자인 (매거진 스타일)
    card_html = ""
    current_section = ""
    
    for item in ai_data:
        # 안전장치: 링크가 없으면 네이버 메인이라도 넣음
        final_link = item.get('link', '#')
        if final_link == '#': 
            final_link = 'https://news.naver.com'

        # 섹션 헤더
        if item['section'] != current_section:
            card_html += f"""
            <div style="margin-top: 40px; margin-bottom: 20px; border-bottom: 2px solid #000; padding-bottom: 5px;">
                <span style="font-size: 14px; font-weight: 900; color: #000; letter-spacing: 1px;">{item['section']}</span>
            </div>
            """
            current_section = item['section']
            
        card_html += f"""
        <div style="margin-bottom: 30px;">
            <h3 style="margin: 0 0 10px 0; font-size: 18px; font-weight: 700; line-height: 1.4;">
                <a href="{final_link}" target="_blank" style="text-decoration: none; color: #111;">
                    {item['headline']}
                </a>
            </h3>
            <p style="margin: 0 0 12px 0; font-size: 14px; color: #555; line-height: 1.6; text-align: justify;">
                {item['summary']}
            </p>
            <div style="background-color: #f4f4f4; padding: 10px 15px; border-radius: 4px; font-size: 12px; color: #333; font-weight: 600;">
                💡 Takeaway: <span style="font-weight: 400;">{item['key_takeaway']}</span>
            </div>
        </div>
        """

    final_html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
    <body style="margin: 0; padding: 0; background-color: #ffffff; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
            
            <div style="text-align: center; margin-bottom: 50px;">
                <p style="font-size: 10px; font-weight: 700; color: #999; letter-spacing: 2px; margin-bottom: 10px;">EXECUTIVE WEEKLY BRIEFING</p>
                <h1 style="margin: 0; font-size: 36px; font-weight: 900; letter-spacing: -1px; color: #000;">
                    MANAGEMENT<br><span style="color: #ED1C24;">INSIGHTS</span>
                </h1>
                <p style="margin: 15px 0 0 0; font-size: 13px; color: #666;">
                    {display_date} &middot; Editor Luca &middot; For Executives
                </p>
            </div>

            <div>{card_html}</div>

            <div style="margin-top: 60px; padding-top: 30px; border-top: 1px solid #eee; text-align: center; font-size: 11px; color: #aaa;">
                <p>Curated for Ottogi Ramyun Leadership<br>
                Powered by Naver Search API & Gemini</p>
            </div>
        </div>
    </body>
    </html>
    """

    # 5. 발송
    msg = MIMEMultipart()
    msg['From'] = f"Luca (Executive Brief) <{user_email}>"
    msg['To'] = user_email
    msg['Subject'] = f"[{display_date}] 주간 경영/리더십 브리핑 (Fixed Link Ver)"
    msg.attach(MIMEText(final_html, 'html'))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(user_email, app_password)
        server.sendmail(user_email, user_email, msg.as_string())
    print(f"✅ 경영 브리핑 발송 완료!")

if __name__ == "__main__":
    run_executive_briefing_fixed()
