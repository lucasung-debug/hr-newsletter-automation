import feedparser
import requests
import json
import datetime
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import quote

def run_unattended_automation():
    # 보안 정보 로드
    api_key = os.environ.get('GEMINI_API_KEY')
    app_password = os.environ.get('GMAIL_APP_PASSWORD')
    user_email = "proposition97@gmail.com"

    # 날짜 및 뉴스 수집 (2026-02-08 기준)
    today = datetime.datetime.now()
    week_ago = today - datetime.timedelta(days=7)
    week_ago_str = week_ago.strftime("%Y-%m-%d")
    display_date = today.strftime("%Y년 %m월 %d일")
    
    keywords = ["인사관리", "노무이슈", "HRD트렌드"]
    collected_news = ""
    for kw in keywords:
        query = f"{kw} after:{week_ago_str}"
        url = f"https://news.google.com/rss/search?q={quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
        feed = feedparser.parse(url)
        for entry in feed.entries[:2]:
            collected_news += f"- {entry.title}\n"

    # AI 분석 (Gemini 2.0 Flash)
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    prompt = f"오뚜기라면 인사팀 성명재 매니저입니다. {display_date}자 HR 뉴스레터를 작성하세요.\n\n{collected_news}"
    
    response = requests.post(api_url, headers={'Content-Type': 'application/json'}, 
                             data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}))
    
    if response.status_code == 200:
        newsletter_text = response.json()['candidates'][0]['content']['parts'][0]['text']
        
        # 이메일 발송
        msg = MIMEMultipart()
        msg['From'] = f"HR 매니저 성명재 <{user_email}>"
        msg['To'] = user_email
        msg['Subject'] = f"[자동발송] {display_date} 주간 HR 트렌드"
        msg.attach(MIMEText(newsletter_text, 'plain'))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(user_email, app_password)
            server.sendmail(user_email, user_email, msg.as_string())
        print(f"✅ {display_date} 발송 성공!")

if __name__ == "__main__":
    run_unattended_automation()
