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

# [핵심 기능] 기사 원문에서 이미지 URL 추출하는 함수
def extract_image_url(entry):
    # 1. RSS 표준 media 태그 확인
    if hasattr(entry, 'media_content') and entry.media_content:
        return entry.media_content[0]['url']
    
    # 2. enclosures 태그 확인 (일부 언론사)
    if hasattr(entry, 'enclosures'):
        for enclosure in entry.enclosures:
            if enclosure.type.startswith('image/'):
                return enclosure.href
                
    # 3. 요약본(summary) HTML 내에서 <img> 태그 검색 (정규표현식)
    if hasattr(entry, 'summary'):
        img_match = re.search(r'<img[^>]+src=["\'](.*?)["\']', entry.summary, re.IGNORECASE)
        if img_match:
            return img_match.group(1)
            
    # 4. [중요] 이미지를 못 찾았을 경우 사용할 '대체 이미지(Placeholder)'
    # 오뚜기 로고나 관련 무료 이미지 URL로 변경하셔도 좋습니다.
    return "https://dummyimage.com/600x300/ED1C24/ffffff.png&text=Ottogi+HR+News"

def run_real_thumbnail_newsletter():
    # 1. 기본 설정
    api_key = os.environ.get('GEMINI_API_KEY')
    app_password = os.environ.get('GMAIL_APP_PASSWORD')
    user_email = "proposition97@gmail.com"

    today = datetime.datetime.now()
    display_date = today.strftime("%Y년 %m월 %d일")
    week_ago = today - datetime.timedelta(days=7)
    
    # 2. 뉴스 및 이미지 수집
    keywords = ["식품산업 채용", "제조업 중대재해", "생산직 인사관리", "푸드테크"]
    collected_news_data = []
    seen_titles = set()
    
    print("📡 뉴스 기사 및 썸네일 추출 중...")
    for kw in keywords:
        query = f"{kw} after:{week_ago.strftime('%Y-%m-%d')}"
        url = f"https://news.google.com/rss/search?q={quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
        feed = feedparser.parse(url)
        for entry in feed.entries[:1]:
            if entry.title not in seen_titles:
                # [핵심] 여기서 이미지를 추출해서 저장합니다.
                img_url = extract_image_url(entry)
                collected_news_data.append({
                    "title": entry.title, 
                    "link": entry.link,
                    "img_url": img_url # 추출한 이미지 주소 저장
                })
                seen_titles.add(entry.title)

    if not collected_news_data:
        # 비상용 더미 데이터에도 대체 이미지 적용
        collected_news_data.append({
            "title": "오뚜기라면, 글로벌 식품 안전 기준 선도", 
            "link": "https://www.ottogi.co.kr",
            "img_url": "https://dummyimage.com/600x300/ED1C24/ffffff.png&text=Ottogi+News"
        })

    # 3. AI 요약 요청 (이미지 생성 요청은 빠짐)
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    news_text_block = "\n".join([f"- {item['title']}" for item in collected_news_data])
    
    # 키워드 추출 부분도 제거하고 요약에만 집중시킵니다.
    prompt = f"""
    당신은 오뚜기라면 인사팀 성명재 매니저입니다.
    아래 뉴스 목록을 분석하여 JSON 데이터만 출력하세요.
    
    [뉴스 목록]
    {news_text_block}

    [JSON 요청 양식]
    [
      {{
        "title": "기사 제목 (30자 이내, 핵심만)",
        "summary": "핵심 내용 2줄 요약 (식품 제조업 HR 관점)"
      }},
      ...
    ]
    
    오직 JSON 리스트만 출력하세요.
    """
    
    print("🤖 AI 요약 진행 중...")
    response = requests.post(api_url, headers={'Content-Type': 'application/json'}, 
                             data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}))
    
    ai_data = []
    if response.status_code == 200:
        raw_text = response.json()['candidates'][0]['content']['parts'][0]['text']
        clean_json = raw_text.replace("```json", "").replace("```", "").strip()
        try:
            ai_data = json.loads(clean_json)
        except:
            ai_data = [{"title": "분석 오류", "summary": "원문을 확인해주세요."}]

    # 4. HTML 조립 (수집한 리얼 썸네일 사용)
    cards_html = ""
    for idx, item in enumerate(ai_data):
        if idx < len(collected_news_data):
            link = collected_news_data[idx]['link']
            # [핵심] 아까 수집해둔 실제 기사 이미지 URL을 사용
            real_img_url = collected_news_data[idx]['img_url']
        else:
            link = "#"
            real_img_url = "https://dummyimage.com/600x300/ccc/000.png&text=No+Image"
        
        cards_html += f"""
        <div style="background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.1); margin-bottom: 30px; border: 1px solid #eee;">
            <div style="background-color: #ED1C24; color: white; padding: 5px 15px; font-size: 12px; font-weight: bold; display: inline-block; border-radius: 0 0 10px 0;">
                REAL NEWS {idx+1}
            </div>
            
            <div style="width: 100%; height: 200px; overflow: hidden; background-color: #f0f0f0;">
                <a href="{link}" target="_blank" style="display: block; width: 100%; height: 100%;">
                    <img src="{real_img_url}" alt="기사 썸네일" style="width: 100%; height: 100%; object-fit: cover; border: 0;">
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
                    현장의 생생한 소식을 담은<br>이번 주 핵심 HR 뉴스입니다.
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
    msg['Subject'] = f"[{display_date}] 🍜 HR 핵심 뉴스 (실제 썸네일 적용)"
    msg.attach(MIMEText(final_html, 'html'))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(user_email, app_password)
        server.sendmail(user_email, user_email, msg.as_string())
    print(f"✅ {display_date} 리얼 썸네일 뉴스레터 발송 완료!")

if __name__ == "__main__":
    run_real_thumbnail_newsletter()
