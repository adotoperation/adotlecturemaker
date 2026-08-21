import os
import requests
import json

API_KEY = os.environ.get("GEMINI_API_KEY", "")
URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"

def test_gemini_analysis(text):
    if not API_KEY:
        print("No GEMINI_API_KEY provided")
        return
    prompt = f"""
Given the English reading passage, perform detailed syntactic analysis and chunked reading translation for Korean high school / CSAT English teaching materials.

Passage:
{text}
"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"}
    }

    res = requests.post(URL, json=payload)
    print("Status Code:", res.status_code)
    print("Response:", res.text[:500])

if __name__ == "__main__":
    test_gemini_analysis("A study by Eurofound found that young people who were working remotely reported more difficulties in managing their workload than older colleagues.")
