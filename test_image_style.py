import os
import requests
import json

API_KEY = os.environ.get("GEMINI_API_KEY", "")
URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"

prompt = """
당신은 대한민국 중·고등학교 영어 내신 분석 전문가이자 스타 강사입니다.
제공되는 영어 지문을 학생들의 내신 대비를 위해 완벽하게 분석하되, 아래의 [구조 분석 및 시각적 표기 규칙]을 준수하여 JSON 형태로만 생성하십시오.

[★구조 분석 및 시각적 표기 규칙★]
1. 영어 문장을 의미 단위 토큰(token) 배열로 나누고, 각 토큰별로 성분을 분석하십시오.
2. 명사구/절은 `[...]` 대괄호, 수식어구/절(전치사구, 관계사절, 부사절 등)은 `(...)` 소괄호로 감싸십시오.
3. 주어(S), 동사(V/Vi/Vt), 목적어(O/IO/DO), 보어(SC/OC)에 해당하는 단어/구에는 sub_tag를 지정하십시오. (sub_tag는 단어 바로 아래에 표시됨)
4. 수식어 구/절이나 명사절/보어절 위에는 top_label (예: "전치사구", "주격보어절", "목적어절", "관계사절", "부사구", "분사구문")을 지정하십시오.
"""

payload = {
    "contents": [{"parts": [{"text": prompt}]}],
    "generationConfig": {"responseMimeType": "application/json"}
}

if __name__ == "__main__":
    if API_KEY:
        res = requests.post(URL, json=payload)
        print("Status Code:", res.status_code)
        print("Response:", res.text[:300])
    else:
        print("No GEMINI_API_KEY provided")
