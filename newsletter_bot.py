import requests
import json
import datetime
import smtplib
import os
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def clean_html(raw_html):
    # 네이버 API가 주는 제목의 <b>태그 등을 제거
    cleanr = re.compile('<.*?>|&quot;|&apos;|&gt;|&lt;')
    return re.sub(cleanr, '', raw_html)

def get_naver_news(keyword):
    client_id = os.environ.get('NAVER_CLIENT_ID')
    client_secret = os.environ.get('NAVER_CLIENT_SECRET')
    
    # 키가 제대로 넘어왔는지 확인
    if not client_id or not client_secret:
        print("❌ 에러: 네이버 API 키가 main.yml에서 전달되지 않았습니다.")
        return []

    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret
    }
    # sort='sim': 정확도순(관련성 높은순), display=3: 상위 3개만
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
                    "desc": clean_html(item['description'])
                })
            return news_list
        else:
            print(f"네이버 API 호출 실패 (코드 {response.status_code})")
            return []
    except Exception as e:
        print(f"네이버 요청 중 에러 발생: {e}")
        return []

def run_naver_clipping():
    # 1. 기본 설정
    api_key = os.environ.get('GEMINI_API_KEY')
    app_password = os.environ.get('GMAIL_APP_PASSWORD')
    user_email = "proposition97@gmail.com"

    today = datetime.datetime.now()
    display_date = today.strftime("%Y년 %m월 %d일")
    
    # 2. 네이버 뉴스 수집 (핵심 키워드)
    keywords = ["식품업계 인사", "제조업 중대재해", "생산직 임금협상", "푸드테크"]
    collected_data = {}
    
    print(f"[{display_date}] 네이버 뉴스 클리핑 시작...")

    for kw in keywords:
        items = get_naver_news(kw)
        if items:
            collected_data[kw] = items
            print(f"- '{kw}' 관련 기사 {len(items)}개 수집 완료")

    if not collected_data:
        print("⚠️ 수집된 뉴스가 없습니다. main.yml 설정을 확인하세요.")
        return

    # 3. AI 분석 요청
    news_context = ""
    for kw, items in collected_data.items():
        news_context += f"\n[키워드: {kw}]\n"
        for item in items:
            news_context += f"- 제목: {item['title']}\n"

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    prompt = f"""
    당신은 오뚜기라면 인사팀 '성명재 매니저'입니다.
    네이버 뉴스 검색결과를 바탕으로 주간 HR 인사이트 리포트를 HTML로 작성하세요.

    [뉴스 데이터]
    {news_context}

    [작성 지침]
    1. **Executive Summary**: 전체 동향을 3문장으로 요약.
    2. **Key Issues**: 각 키워드별로 섹션을 나누어 '주요 이슈'와 '오뚜기라면 HR팀의 대응 방안'을 서술.
    3. 스타일: 깔끔한 비즈니스 리포트 스타일 (회색 배경, 카드 형태).
    """
    
    print("🤖 AI 보고서 생성 중...")
    response = requests.post(api_url, headers={'Content-Type': 'application/json'}, 
                             data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}))
    
    if response.status_code == 200:
        ai_content = response.json()['candidates'][0]['content']['parts'][0]['text']
        ai_content = ai_content.replace("```html", "").replace("```", "")

        # 4. 링크 모음 (부록)
        links_html = "<h4>🔗 네이버 뉴스 원문 바로가기</h4><ul style='font-size: 13px; color: #666;'>"
        for kw, items in collected_data.items():
            for item in items:
                 links_html += f"<li>[{kw}] <a href='{item['link']}' target='_blank' style='color: #007bff; text-decoration: none;'>{item['title']}</a></li>"
        links_html += "</ul>"

        # 5. 최종 HTML 조립
        final_html = f"""
        <html>
        <body style="margin: 0; padding: 0; background-color: #ffffff; font-family: 'Malgun Gothic', sans-serif;">
            <div style="max-width: 700px; margin: 0 auto; border: 1px solid #eeeeee;">
                <div style="background-color: #03C75A; padding: 30px 40px;">
                    <h1 style="margin: 0; color: #ffffff; font-size: 24px;">NAVER News HR Clipping</h1>
                    <p style="margin: 5px 0 0 0; color: #eebbff; font-size: 14px;">오뚜기라면 성명재 매니저 | {display_date}</p>
                </div>
                <div style="padding: 40px;">
                    {ai_content}
                    <hr style="border: 0; border-top: 1px solid #eee; margin: 40px 0;">
                    {links_html}
                </div>
                <div style="background-color: #f9f9f9; padding: 20px; text-align: center; color: #888; font-size: 12px;">
                    Data provided by Naver Search API
                </div>
            </div>
        </body>
        </html>
        """

        msg = MIMEMultipart()
        msg['From'] = f"성명재 매니저 <{user_email}>"
        msg['To'] = user_email
        msg['Subject'] = f"[{display_date}] 네이버 뉴스 기반 HR 인사이트"
        msg.attach(MIMEText(final_html, 'html'))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(user_email, app_password)
            server.sendmail(user_email, user_email, msg.as_string())
        print(f"✅ 네이버 뉴스 클리핑 발송 완료!")

if __name__ == "__main__":
    run_naver_clipping()
