import feedparser
import requests
import json
import datetime
import smtplib
import os
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import quote

def run_clickable_card_newsletter():
    # 1. 기본 설정 및 보안 인증
    api_key = os.environ.get('GEMINI_API_KEY')
    app_password = os.environ.get('GMAIL_APP_PASSWORD')
    user_email = "proposition97@gmail.com"

    # 날짜 설정 (서버 시간 기준)
    today = datetime.datetime.now()
    display_date = today.strftime("%Y년 %m월 %d일")
    week_ago = today - datetime.timedelta(days=7)
    
    # 2. 뉴스 수집 (식품/제조/HR 키워드)
    keywords = ["식품산업 채용", "제조업 중대재해", "생산직 인사관리", "푸드테크"]
    collected_news_data = []
    seen_titles = set()
    
    # 키워드별 상위 1개 기사 수집
    for kw in keywords:
        query = f"{kw} after:{week_ago.strftime('%Y-%m-%d')}"
        url = f"https://news.google.com/rss/search?q={quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
        feed = feedparser.parse(url)
        for entry in feed.entries[:1]:
            if entry.title not in seen_titles:
                # 링크(link)를 여기서 확실하게 저장합니다.
                collected_news_data.append({"title": entry.title, "link": entry.link})
                seen_titles.add(entry.title)

    # 뉴스가 없을 경우 비상용 데이터
    if not collected_news_data:
        collected_news_data.append({"title": "오뚜기라면, 글로벌 식품 안전 기준 선도", "link": "https://www.ottogi.co.kr"})

    # 3. AI에게 요약 데이터(JSON) 요청
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    news_text_block = "\n".join([f"- {item['title']}" for item in collected_news_data])

    prompt = f"""
    당신은 오뚜기라면 인사팀 성명재 매니저입니다.
    아래 뉴스 목록을 분석하여 JSON 데이터만 출력하세요.
    
    [뉴스 목록]
    {news_text_block}

    [JSON 요청 양식]
    [
      {{
        "title": "기사 제목 (30자 이내, 핵심만)",
        "summary": "핵심 내용 2줄 요약 (식품 제조업 HR 관점)",
        "keyword": "기사 내용을 대표하는 영어 단어 1개 (예: Factory, Meeting, Food, Safety)"
      }},
      ...
    ]
    
    오직 JSON 리스트만 출력하세요.
    """
    
    response = requests.post(api_url, headers={'Content-Type': 'application/json'}, 
                             data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}))
    
    # 4. 데이터 파싱 및 HTML 조립
    ai_data = []
    if response.status_code == 200:
        raw_text = response.json()['candidates'][0]['content']['parts'][0]['text']
        clean_json = raw_text.replace("```json", "").replace("```", "").strip()
        try:
            ai_data = json.loads(clean_json)
        except:
            ai_data = [{"title": "데이터 분석 오류", "summary": "뉴스 원문을 확인해주세요.", "keyword": "Error"}]

    cards_html = ""
    for idx, item in enumerate(ai_data):
        # 수집된 원본 링크 매칭 (인덱스 기준)
        if idx < len(collected_news_data):
            link = collected_news_data[idx]['link']
        else:
            link = "#"
        
        # Pollinations AI 이미지 URL (랜덤 시드 추가로 매번 다른 이미지 생성)
        img_url = f"https://image.pollinations.ai/prompt/{item['keyword']}?width=600&height=300&nologo=true&seed={idx}"
        
        # HTML 조립 (핵심: 이미지와 제목에 <a> 태그 적용)
        cards_html += f"""
        <div style="background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.1); margin-bottom: 30px; border: 1px solid #eee;">
            <div style="background-color: #ED1C24; color: white; padding: 5px 15px; font-size: 12px; font-weight: bold; display: inline-block; border-radius: 0 0 10px 0;">
                NEWS {idx+1}
            </div>
            
            <div style="width: 100%; height: 200px; overflow: hidden; background-color: #f0f0f0;">
                <a href="{link}" target="_blank" style="display: block; width: 100%; height: 100%;">
                    <img src="{img_url}" alt="{item['keyword']}" style="width: 100%; height: 100%; object-fit: cover; border: 0;">
                </a>
            </div>
            
            <div style="padding: 20px;">
                <h3 style="margin: 0 0 10px 0; font-size: 18px; line-height: 1.4;">
                    <a href="{link}" target="_blank" style="text-decoration: none; color: #333;">{item['title']}</a>
                </h3>
                <p style="margin: 0; color: #666; font-size: 14px; line-height: 1.6;">{item['summary']}</p>
                
                <div style="margin-top: 15px; text-align: right;">
                     <a href="{link}" target="_blank" style="text-decoration: none; color: #ED1C24; font-weight: bold; font-size: 13px; border: 1px solid #ED1C24; padding: 5px 10px; border-radius: 4px;">
                        🔗 원문 읽기
                     </a>
                </div>
            </div>
        </div>
        """

    final_html = f"""
    <html>
    <body style="margin: 0; padding: 0; background-color: #f4f4f4; font-family: 'Malgun Gothic', sans-serif;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #f4f4f4;">
            <div style="background-color: #FFD400; padding: 30px 20px; text-align: center; border-bottom: 4px solid #ED1C24;">
                <h1 style="margin: 0; color: #ED1C24; font-size: 26px;">🍜 오뚜기라면 HR Insight</h1>
                <p style="margin: 10px 0 0 0; font-weight: bold; color: #333;">{display_date} | 성명재 매니저</p>
            </div>
            
            <div style="padding: 20px;">
                <p style="text-align: center; color: #666; margin-bottom: 30px;">
                    식품 제조 현장의 혁신과 안전을 위한<br>이번 주 핵심 뉴스를 확인하세요.
                </p>
                
                {cards_html}
                
            </div>
            
            <div style="text-align: center; padding: 20px; color: #999; font-size: 12px;">
                © 2026 Ottogi Ramyun HR Team. Automated by Github Actions.
            </div>
        </div>
    </body>
    </html>
    """

    # 5. 이메일 발송
    msg = MIMEMultipart()
    msg['From'] = f"오뚜기라면 성명재 <{user_email}>"
    msg['To'] = user_email
    msg['Subject'] = f"[{display_date}] 🍜 이번 주 HR 핵심 카드뉴스 (링크 포함)"
    msg.attach(MIMEText(final_html, 'html'))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(user_email, app_password)
        server.sendmail(user_email, user_email, msg.as_string())
    print(f"✅ {display_date} 카드뉴스 발송 완료!")

if __name__ == "__main__":
    run_clickable_card_newsletter()
