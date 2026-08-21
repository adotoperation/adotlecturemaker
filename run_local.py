import os
import sys
import webbrowser
import threading
import time
from app import app

def open_browser():
    time.sleep(1.5)
    print("Opening browser at http://localhost:5000 ...")
    webbrowser.open("http://localhost:5000")

if __name__ == "__main__":
    print("=" * 65)
    print(" [강의용 교안 만들기] 로컬 서버를 실행합니다.")
    print(" supported by 영업지원팀")
    print(" 주소: http://localhost:5000")
    print(" 종료하려면 Ctrl+C 를 누르세요.")
    print("=" * 65)
    
    # Launch browser thread
    threading.Thread(target=open_browser, daemon=True).start()
    
    # Start web server
    app.run(host="127.0.0.1", port=5000, debug=False)
