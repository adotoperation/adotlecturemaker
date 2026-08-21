import os
import requests
import json

API_KEY = os.environ.get("GEMINI_API_KEY", "")
URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"

prompt = """
[분석 대상 영어 지문]
A study by Eurofound found that young people who were working remotely reported more difficulties in managing their workload than older colleagues.

[★구조 분석 & 후치수식 화살표 토큰 규칙★]
1. 명사구/절은 `[...]` 대괄호, 수식어구/절(전치사구, 관계사절, 부사절 등)은 `(...)` 소괄호로 감싸십시오.
2. 후치수식 규칙: 명사 바로 뒤에 형용사구/절(전치사구, 관계사절 등)이 후치수식할 경우, 명사와 수식구/절 사이에 독립된 화살표 토큰 `{"text": "⟵", "color": "amber"}`을 반드시 삽입하십시오!
   예시: `A study` 토큰 바로 뒤에 `⟵` 토큰 삽입, 그 뒤에 `(by Eurofound)` 토큰 배치.
   예시: `young people` 토큰 바로 뒤에 `⟵` 토큰 삽입, 그 뒤에 `(who were working remotely)` 토큰 배치.
"""

payload = {
    "contents": [{"parts": [{"text": prompt}]}],
    "generationConfig": {"responseMimeType": "application/json"}
}

if API_KEY:
    res = requests.post(URL, json=payload)
    print(res.status_code)
    print(res.text[:500])
else:
    print("No GEMINI_API_KEY provided")
