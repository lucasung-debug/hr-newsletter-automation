import feedparser
import requests
import json
import datetime
import smtplib
import os
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import quote

def run_debug_newsletter():
    print("🚀 뉴스레터 봇 가동 시작...")
    
    # 1. 환경 변수 확인
    api_key = os.environ.get('GEMINI_API_KEY')
    app_password = os.environ.get('GMAIL_APP_PASSWORD')
    user_email = "proposition97@gmail.com"

    if not api_key or not app_password:
        print("❌ 오류: 보안 키(API KEY 또는 앱 비밀번호)가 설정되지 않았습니다.")
        return

    today = datetime.datetime.now()
    week_ago = today - datetime.timedelta(days=7)
    display_date = today.strftime("%Y년 %m월 %d일")
    
    # 2. 뉴스 수집
    keywords = ["식품산업 채용", "제조업 중대재해", "생산직 노무관리", "푸드테크"]
    collected_news_data = []
    seen_titles = set()

    print(f"📡 뉴스 수집 중... (기준일: {week_ago.strftime('%Y-%m-%d')})")
    
    for kw in keywords:
        query = f"{kw} after:{week_ago.strftime('%Y-%m-%d')}"
        url = f"https://news.google.com/rss/search?q={quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
        feed = feedparser.parse(url)
        
        for entry in feed.entries[:1]:
            if entry.title not in seen_titles:
                collected_news_data.append({
                    "title": entry.title,
                    "link": entry.link,
                    "keyword": kw
                })
                seen_titles.add(entry.title)

    if not collected_news_data:
        print("⚠️ 수집된 뉴스가 없습니다. 검색 기간이나 키워드를 조정해보세요.")
        # 테스트를 위해 강제 더미 데이터 추가
        print("🔧 테스트용 더미 데이터를 생성합니다.")
        collected_news_data.append({"title": "오뚜기라면, 글로벌 식품 안전 기준 강화", "link": "#", "keyword": "식품안전"})

    print(f"✅ 수집된 뉴스 개수: {len(collected_news_data)}개")

    # 3. AI 요청
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    news_context = "\n".join([f"- {item['title']} (키워드: {item['keyword']})" for item in collected_news_data])

    prompt = f"""
    당신은 오뚜기라면 인사팀 성명재 매니저입니다.
    아래 뉴스 1개를 바탕으로 HTML 카드 뉴스 1개만 작성하세요.
    
    [뉴스]
    {news_context}

    [필수 지침]
    - HTML 태그(<div> 등)만 출력할 것.
    - 마크다운(```html)을 쓰지 말 것.
    - 이미지 태그 예시: <img src="[https://image.pollinations.ai/prompt/FoodFactory?width=600&height=300&nologo=true](https://image.pollinations.ai/prompt/FoodFactory?width=600&height=300&nologo=true)" style="width:100%">
    """
    
    print("🤖 AI에게 원고 작성을 요청하는 중...")
    response = requests.post(api_url, headers={'Content-Type': 'application/json'}, 
                             data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}))
    
    if response.status_code != 200:
        print(f"❌ AI API 호출 실패! 상태 코드: {response.status_code}")
        print(f"에러 내용: {response.text}")
        return

    ai_card_content = response.json()['candidates'][0]['content']['parts'][0]['text']
    
    # 마크다운 제거 (안전장치)
    ai_card_content = ai_card_content.replace("```html", "").replace("```", "")
    
    print("✅ AI 원고 생성 완료. 이메일 발송 준비...")

    # 4. 이메일 발송
    final_html = f"""
    <html>
    <body style="font-family: sans-serif; padding: 20px;">
        <h2 style="color: #ED1C24;">🍜 오뚜기라면 긴급 디버깅 뉴스레터</h2>
        <p>이 메일이 보인다면 시스템이 정상 작동하는 것입니다.</p>
        <hr>
        {ai_card_content}
    </body>
    </html>
    """

    try:
        msg = MIMEMultipart()
        msg['From'] = f"오뚜기라면 봇 <{user_email}>"
        msg['To'] = user_email
        msg['Subject'] = f"[{display_date}] 시스템 점검용 뉴스레터"
        msg.attach(MIMEText(final_html, 'html'))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(user_email, app_password)
            server.sendmail(user_email, user_email, msg.as_string())
        print(f"🚀 이메일 발송 성공! ({user_email} 확인 요망)")
    
    except Exception as e:
        print(f"❌ 이메일 발송 중 에러 발생: {e}")

if __name__ == "__main__":
    run_debug_newsletter()
