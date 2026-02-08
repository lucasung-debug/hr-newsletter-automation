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
    
    # 1. 검색어 전략 수정: 인사이트를 얻기 위한 검색어 조합
    # category_type에 따라 검색어 뒤에 '칼럼', '인터뷰' 등을 붙여서 질 좋은 글을 유도
    search_query = keyword
    if category_type == "INSIGHT":
        search_query += " (칼럼 OR 기고 OR 인사이트)"
    elif category_type == "INTERVIEW":
        search_query += " (인터뷰 OR 대담)"
    
    # 정확도순(sim)으로 상위 30개를 긁어서 최신순 필터링
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
                        # 섹션별 2개만 엄선 (너무 길어지지 않게)
                        if len(filtered_content) >= 2:
                            break
                except:
                    continue
            return filtered_content
        return []
    except Exception:
        return []

def run_executive_briefing():
    # 1. 환경 설정
    api_key = os.environ.get('GEMINI_API_KEY')
    app_password = os.environ.get('GMAIL_APP_PASSWORD')
    user_email = "proposition97@gmail.com"

    today = datetime.datetime.now()
    display_date = today.strftime("%Y년 %m월 %d일")
    
    # 2. [전략적 카테고리 구성] 경영진이 봐야 할 4대 필드
    # (검색어 + 콘텐츠 타입) 조합
    search_targets = [
        # [Macro] 거시 경제 및 산업 흐름 (일반 뉴스)
        {"kw": "2026년 한국 경제 제조업 전망", "type": "NEWS", "label": "MACRO & INDUSTRY"},
        {"kw": "식품산업 글로벌 트렌드", "type": "NEWS", "label": "MACRO & INDUSTRY"},
        
        # [Management] 조직관리 및 리더십 (칼럼/기고)
        {"kw": "조직문화 리더십", "type": "INSIGHT", "label": "LEADERSHIP INSIGHT"},
        {"kw": "MZ세대 성과관리", "type": "INSIGHT", "label": "LEADERSHIP INSIGHT"},
        
        # [People] 성공 사례 및 인터뷰 (인터뷰)
        {"kw": "CEO 경영 철학", "type": "INTERVIEW", "label": "LEADERS VOICE"},
        {"kw": "혁신 기업 성공 사례", "type": "INTERVIEW", "label": "CASE STUDY"},

        # [Risk & HR] 필수 노무/법률 (뉴스)
        {"kw": "통상임금 성과급 판례", "type": "NEWS", "label": "RISK MANAGEMENT"}
    ]
    
    collected_data = {}
    print(f"[{display_date}] 경영 브리핑 데이터 수집 중...")

    for target in search_targets:
        items = get_naver_content(target['kw'], target['type'])
        if items:
            # 라벨별로 데이터 묶기
            if target['label'] not in collected_data:
                collected_data[target['label']] = []
            collected_data[target['label']].extend(items)

    if not collected_data:
        print("⚠️ 데이터 수집 실패")
        return

    # 3. AI 분석 요청 (종합 브리핑 모드)
    context_text = ""
    for label, items in collected_data.items():
        context_text += f"\n[SECTION: {label}]\n"
        for item in items:
            context_text += f"- 제목: {item['title']} / 요약: {item['desc']}\n"

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    prompt = f"""
    당신은 오뚜기라면의 C-Level 경영진을 위한 수석 보좌관 'Luca'입니다.
    수집된 정보를 바탕으로 **주간 경영 인사이트 리포트**를 JSON으로 작성하세요.

    [작성 원칙]
    1. **관점(Perspective)**: 단순 정보 전달을 넘어, 이것이 경영진에게 어떤 영감(Inspiration)이나 경각심(Alert)을 주는지 서술하세요.
    2. **다양성**: 경제 전망부터 타사 CEO의 인터뷰까지 폭넓게 다루세요.
    3. **Action**: '관리자로서 생각해볼 질문'이나 '실무 적용점'을 한 줄씩 포함하세요.

    [JSON 출력 양식]
    [
      {{
        "section": "섹션명 (예: MACRO, LEADERSHIP, VOICES)",
        "headline": "통찰력 있는 헤드라인 (30자)",
        "summary": "내용 요약 및 시사점 (2~3문장)",
        "key_takeaway": "경영진을 위한 한 줄 요약 (Action Item)",
        "link": "기사 링크 (없으면 #)" 
      }},
      ... (섹션별 1~2개씩 선정하여 총 6~8개)
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

    # 링크 매칭 보정 (AI가 링크를 잘 못 뱉을 경우를 대비해 수집된 데이터에서 역추적)
    # (간소화를 위해 순차 매칭 로직 사용하지 않고, AI가 비워두면 # 처리)
    # 실제 프로덕션에선 URL 매칭 로직을 정교화해야 하지만, 여기선 수집된 데이터 풀에서 첫번째 링크를 할당하는 방식으로 보완
    
    all_links_pool = []
    for label in collected_data:
        for item in collected_data[label]:
            all_links_pool.append(item['link'])
            
    for i, item in enumerate(ai_data):
        if item.get('link') == "#" or not item.get('link'):
            item['link'] = all_links_pool[i % len(all_links_pool)]

    # 4. HTML 디자인 (매거진 스타일)
    card_html = ""
    current_section = ""
    
    for item in ai_data:
        # 섹션 헤더 (새로운 섹션이 나올 때만 출력)
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
                <a href="{item['link']}" target="_blank" style="text-decoration: none; color: #111;">
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
    msg['Subject'] = f"[{display_date}] 주간 경영/리더십 브리핑 (Management Insights)"
    msg.attach(MIMEText(final_html, 'html'))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(user_email, app_password)
        server.sendmail(user_email, user_email, msg.as_string())
    print(f"✅ 경영 브리핑 발송 완료!")

if __name__ == "__main__":
    run_executive_briefing()
