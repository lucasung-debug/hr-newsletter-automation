import feedparser
import requests
import json
import datetime
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import quote

def run_linked_hr_newsletter():
    api_key = os.environ.get('GEMINI_API_KEY')
    app_password = os.environ.get('GMAIL_APP_PASSWORD')
    user_email = "proposition97@gmail.com" # 성명재 매니저님 이메일

    today = datetime.datetime.now()
    week_ago = today - datetime.timedelta(days=7)
    display_date = today.strftime("%Y년 %m월 %d일")
    
    # 1. 뉴스 및 링크 수집 [cite: 2026-02-08]
    keywords = ["인사관리", "노무이슈", "HRD트렌드"]
    news_data_list = [] 
    
    for kw in keywords:
        query = f"{kw} after:{week_ago.strftime('%Y-%m-%d')}"
        url = f"https://news.google.com/rss/search?q={quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
        feed = feedparser.parse(url)
        for entry in feed.entries[:1]: # 키워드당 1개 최신 뉴스 추출
            news_data_list.append({
                "title": entry.title,
                "link": entry.link
            })

    # 2. AI 뉴스레터 본문 생성 요청 [cite: 2026-02-08]
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    # AI에게 전달할 뉴스 텍스트 구성
    news_context = ""
    for item in news_data_list:
        news_context += f"기사제목: {item['title']}\n"

    prompt = f"""
    당신은 오뚜기라면 인사팀 '성명재' 매니저입니다.
    아래 뉴스들의 핵심 요약과 인사팀 시사점을 작성하세요.
    [뉴스 데이터]:\n{news_context}
    
    [작성 가이드]: 
    - 각 뉴스는 <h3>태그를 사용하되, 제목 뒤에 (링크 하단 참조)라고 적어주세요.
    - 본문은 '요약-시사점-실무가이드' 순서로 HTML 형식을 갖추어 작성하세요.
    """
    
    response = requests.post(api_url, headers={'Content-Type': 'application/json'}, 
                             data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}))
    
    if response.status_code == 200:
        ai_content = response.json()['candidates'][0]['content']['parts'][0]['text']
        
        # 3. 뉴스 제목 및 원문 링크 섹션 별도 생성 [cite: 2026-02-08]
        links_html = "<h4>🔗 원문 기사 링크</h4><ul style='font-size: 13px; color: #555;'>"
        for item in news_data_list:
            links_html += f"<li><a href='{item['link']}' target='_blank' style='color: #007bff;'>{item['title']}</a></li>"
        links_html += "</ul>"

        # 4. 전체 HTML 템플릿 구성 [cite: 2026-02-08]
        html_body = f"""
        <html>
        <body style="font-family: 'Malgun Gothic', sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: auto; border: 1px solid #ddd; padding: 20px;">
                <div style="background-color: #FFD400; padding: 10px; text-align: center;">
                    <h2 style="margin: 0; color: #ED1C24;">🍜 오뚜기라면 주간 HR 브리핑</h2>
                    <p style="margin: 5px 0 0 0; font-weight: bold;">발행일: {display_date}</p>
                </div>
                <div style="padding: 20px 0;">
                    <p>안녕하세요, <b>성명재 매니저</b>입니다. 이번 주 수집된 주요 HR 기사 원문과 분석 내용을 공유합니다.</p>
                    <hr style="border: 0; border-top: 1px solid #eee;">
                    {ai_content}
                    <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
                    {links_html}
                </div>
                <div style="background-color: #f9f9f9; padding: 15px; font-size: 11px; color: #888;">
                    본 메일은 AI 기반 자동화 시스템으로 발송되었습니다. [cite: 2026-02-08]<br>
                    수집 기간: {week_ago.strftime('%Y-%m-%d')} ~ {today.strftime('%Y-%m-%d')}
                </div>
            </div>
        </body>
        </html>
        """

        msg = MIMEMultipart()
        msg['From'] = f"성명재 매니저 <{user_email}>"
        msg['To'] = user_email
        msg['Subject'] = f"[{display_date}] HR 트렌드 분석 및 원문 링크"
        msg.attach(MIMEText(html_body, 'html'))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(user_email, app_password)
            server.sendmail(user_email, user_email, msg.as_string())
        print(f"✅ {display_date} 원문 링크 포함 버전 발송 성공!")

if __name__ == "__main__":
    run_linked_hr_newsletter()
