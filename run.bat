@echo off
chcp 65001 >nul
echo ===================================================
echo Starting '강의용 교안 만들기' Web App...
echo supported by 영업지원팀
echo ===================================================
if exist "%~dp0venv\Scripts\python.exe" (
    "%~dp0venv\Scripts\python.exe" "%~dp0run_local.py"
) else (
    py run_local.py 2>nul || python run_local.py
)
pause

