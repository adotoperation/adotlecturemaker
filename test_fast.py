import os
import requests
import json

API_KEY = os.environ.get("GEMINI_API_KEY", "")

session = requests.Session()
adapter = requests.adapters.HTTPAdapter(max_retries=2)
session.mount('https://', adapter)

url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"

payload = {
    "contents": [{"parts": [{"text": "Hello, respond with JSON {\"status\": \"ok\"}"}]}],
    "generationConfig": {"responseMimeType": "application/json"}
}

if API_KEY:
    try:
        res = session.post(url, json=payload, timeout=5)
        print("Status Code:", res.status_code)
        print("Response:", res.text[:200])
    except Exception as e:
        print("Error:", e)
else:
    print("No GEMINI_API_KEY provided")
