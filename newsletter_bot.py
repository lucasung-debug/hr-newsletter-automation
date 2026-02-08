import feedparser
import requests
import json
import datetime
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import quote

def run_premium_food_hr_newsletter():
    # 1. 환경 변수 및 기본 설정
    api_key = os.environ.get('GEMINI_API_KEY')
    app_password = os.environ.get('GMAIL_APP_PASSWORD')
    user_email = "proposition97@gmail.com"

    today = datetime.datetime.now()
    week_ago = today - datetime.timedelta(days=7)
    display_date = today.strftime("%Y년 %m월 %d일")
    
    # 2. 식품 제조업 맞춤형 뉴스 수집 (키워드 고도화)
    # 오뚜기라면 인사팀에 실질적으로 필요한 키워드로 변경
    keywords = ["식품산업 채용", "제조업 중대재해", "생산직 노무관리", "외국인 근로자 비자", "푸드테크 HR"]
    
    collected_news_data = []
    seen_titles = set() # 중복 기사 제거용

    print(f"[{display_date}] 식품/제조 HR 뉴스 수집 시작...")
    
    for kw in keywords:
        query = f"{kw} after:{week_ago.strftime('%Y-%m-%d')}"
        url = f"https://news.google.com/rss/search?q={quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
        feed = feedparser.parse(url)
        
        # 키워드별 상위 1개 기사만 엄선
        for entry in feed.entries[:1]:
            if entry.title not in seen_titles:
                collected_news_data.append({
                    "title": entry.title,
                    "link": entry.link,
                    "keyword": kw # 어떤 키워드로 수집됐는지 추적
                })
                seen_titles.add(entry.title)

    # 수집된 뉴스가 너무 많으면 3개로 제한 (스압 방지)
    collected_news_data = collected_news_data[:3]

    # 3. AI에게 카드 뉴스 스타일 HTML 생성 요청
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    # 프롬프트에 '식품 제조업' 페르소나와 '카드 뉴스' 포맷을 강력하게 주입
    news_context = ""
    for idx, item in enumerate(collected_news_data):
        news_context += f"{idx+1}. 기사제목: {item['title']} (키워드: {item['keyword']}, 링크: {item['link']})\n"

    prompt = f"""
    당신은 대한민국 최고의 식품 기업 '오뚜기라면'의 인사팀 성명재 매니저입니다.
    수집된 뉴스를 바탕으로 동료들이 클릭할 수밖에 없는 **카드 뉴스 형태의 HTML**을 작성하세요.

    [수집된 뉴스]
    {news_context}

    [디자인 및 작성 지침]
    1. 전체 레이아웃: 각 뉴스마다 '카드' 형태의 디자인을 적용하세요 (테두리, 그림자 효과).
    2. **이미지 생성**: 각 뉴스 내용에 어울리는 영문 키워드(예: Factory, Food Safety, Worker)를 하나 뽑아서, 
       `<img src="https://image.pollinations.ai/prompt/{{영문키워드}}?width=800&height=400&nologo=true" style="width:100%; border-radius: 8px 8px 0 0;">` 
       형태로 삽입하세요. (실제 이미지가 생성되어 나옵니다)
    3. 배지(Badge): 뉴스 성격에 따라 [📢 현장 필독], [⚖️ 노무 이슈], [💡 채용 트렌드] 중 하나를 제목 위에 다세요.
    4. 내용 요약: '식품 제조업 인사팀' 관점에서 **결론-대응방안** 위주로 3줄 요약하세요.
    5. 원문 링크: 카드 하단에 '🔗 원문 보러가기' 버튼을 만드세요.

    [HTML 출력 형식]
    HTML 태그만 출력하세요. `<html>`이나 `<body>` 태그는 제외하고, 카드들이 나열된 `<div>` 덩어리들만 주세요.
    스타일은 인라인 CSS(style="...")를 사용하여 메일에서도 깨지지 않게 하세요.
    """
    
    response = requests.post(api_url, headers={'Content-Type': 'application/json'}, 
                             data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}))
    
    if response.status_code == 200:
        ai_card_content = response.json()['candidates'][0]['content']['parts'][0]['text']
        
        # 4. 최종 HTML 이메일 템플릿 조립 (오뚜기 브랜드 아이덴티티 적용)
        final_html = f"""
        <html>
        <head>
            <style>
                @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap');
                body {{ font-family: 'Noto Sans KR', sans-serif; background-color: #f4f4f4; margin: 0; padding: 0; }}
                .container {{ max-width: 600px; margin: 0 auto; background-color: #ffffff; }}
                .header {{ background-color: #FFD400; padding: 20px; text-align: center; border-bottom: 3px solid #ED1C24; }}
                .footer {{ background-color: #333333; color: #ffffff; padding: 20px; text-align: center; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="color: #ED1C24; margin: 0; font-size: 24px;">🍜 오뚜기라면 HR Weekly</h1>
                    <p style="margin: 10px 0 0 0; font-weight: bold; color: #333;">{display_date} | 성명재 매니저 드림</p>
                </div>

                <div style="padding: 20px; color: #555; line-height: 1.6;">
                    안녕하세요, 오뚜기라면 가족 여러분! 🙇‍♂️<br>
                    이번 주는 <b>식품 안전, 생산 현장 노무 이슈, 그리고 최신 채용 트렌드</b>를 중심으로 정리했습니다.<br>
                    현업에 바로 적용할 수 있는 인사이트를 확인해 보세요.
                </div>

                <div style="padding: 0 20px 20px 20px;">
                    {ai_card_content}
                </div>

                <div class="footer">
                    본 뉴스레터는 HR 업무 자동화 시스템에 의해 발송되었습니다.<br>
                    문의: 인사팀 성명재 매니저 (proposition97@gmail.com)
                </div>
            </div>
        </body>
        </html>
        """

        # 5. 이메일 발송
        msg = MIMEMultipart()
        msg['From'] = f"오뚜기라면 성명재 매니저 <{user_email}>"
        msg['To'] = user_email
        msg['Subject'] = f"[{display_date}] 🍜 식품/제조업 HR 핵심 트렌드 (카드뉴스)"
        msg.attach(MIMEText(final_html, 'html'))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(user_email, app_password)
            server.sendmail(user_email, user_email, msg.as_string())
        print(f"✅ {display_date} 프리미엄 카드 뉴스레터 발송 완료!")

if __name__ == "__main__":
    run_premium_food_hr_newsletter()
