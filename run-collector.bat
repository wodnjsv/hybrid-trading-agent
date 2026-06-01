@echo off
REM ManjuAgent 데이터 수집기 (Windows). 평일 장중 09:00~15:30 KST 에 실행.
REM 코드가 절전을 자동 방지하므로 켜두면 종료(Ctrl+C) 전까지 계속 녹음합니다.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [오류] .venv 가 없습니다. 먼저 아래를 실행하세요:
  echo     python -m venv .venv
  echo     .venv\Scripts\pip install -e ".[dev]"
  pause
  exit /b 1
)

if not exist "secrets.yaml" (
  echo [오류] secrets.yaml 이 없습니다. secrets.example.yaml 을 복사해 키를 채우세요.
  pause
  exit /b 1
)

".venv\Scripts\manju-collect.exe"
pause
