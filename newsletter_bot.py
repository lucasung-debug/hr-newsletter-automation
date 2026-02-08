import feedparser
import requests
import json
import datetime
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import quote

def run_stylish_hr_newsletter():
    api_key = os.environ.get('GEMINI_API_KEY')
    app_password = os.environ.get('GMAIL_APP_PASSWORD')
    user_email = "proposition97@gmail.com"

    today = datetime.datetime.now()
    week_ago = today - datetime.timedelta(days=7)
    display_date = today.strftime("%Y년 %m월 %d일")
    
    # 1. 뉴스 수집
    keywords = ["인사관리", "노무이슈", "HRD트렌드"]
    collected_news = ""
    for kw in keywords:
        query = f"{kw} after:{week_ago.strftime('%Y-%m-%d')}"
        url = f"https://news.google.com/rss/search?q={quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
        feed = feedparser.parse(url)
        for entry in feed.entries[:2]:
            collected_news += f"<li><b>{entry.title}</b></li>"

    # 2. AI 뉴스레터 본문 생성 (HTML 태그 포함 요청)
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    prompt = f"""
    당신은 오뚜기라면 인사팀 '성명재' 매니저입니다. 
    다음 뉴스를 바탕으로 동료들에게 보낼 HTML 형식의 뉴스레터 본문 내용을 작성하세요.
    [뉴스 데이터]: {collected_news}
    [지시사항]: 
    - 각 뉴스를 '핵심요약-시사점-실무가이드' 순서로 정리할 것.
    - HTML 태그(h3, p, ul, li 등)를 적절히 섞어서 텍스트만 추출할 것.
    """
    
    response = requests.post(api_url, headers={'Content-Type': 'application/json'}, 
                             data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}))
    
    if response.status_code == 200:
        ai_content = response.json()['candidates'][0]['content']['parts'][0]['text']
        
        # 3. HTML 디자인 템플릿 입히기
        html_body = f"""
        <html>
        <body style="font-family: 'Malgun Gothic', sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: auto; border: 1px solid #ddd; padding: 20px;">
                <div style="background-color: #FFD400; padding: 10px; text-align: center;">
                    <h2 style="margin: 0; color: #ED1C24;">🍜 오뚜기라면 주간 HR 브리핑</h2>
                    <p style="margin: 5px 0 0 0; font-weight: bold;">발행일: {display_date}</p>
                </div>
                <div style="padding: 20, 0;">
                    <p>안녕하세요, 인사팀 <b>성명재 매니저</b>입니다. 이번 주 주요 HR 이슈를 정리해 드립니다.</p>
                    <hr style="border: 0; border-top: 1px solid #eee;">
                    {ai_content}
                </div>
                <div style="background-color: #f9f9f9; padding: 15px; font-size: 12px; color: #666;">
                    본 메일은 AI를 통해 자동 생성된 주간 트렌드 보고서입니다.<br>
                    문의: 인사팀 성명재 매니저 (proposition97@gmail.com)
                </div>
            </div>
        </body>
        </html>
        """

        # 4. 이메일 발송 (HTML 타입 설정)
        msg = MIMEMultipart()
        msg['From'] = f"오뚜기라면 성명재 매니저 <{user_email}>"
        msg['To'] = user_email
        msg['Subject'] = f"[{display_date}] HR 트렌드 및 실무 가이드"
        msg.attach(MIMEText(html_body, 'html')) # 'plain'에서 'html'로 변경

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(user_email, app_password)
            server.sendmail(user_email, user_email, msg.as_string())
        print(f"✅ {display_date} 디자인 버전 발송 성공!")

if __name__ == "__main__":
    run_stylish_hr_newsletter()
