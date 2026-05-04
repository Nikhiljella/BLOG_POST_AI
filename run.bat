@echo off
setlocal

cd /d "%~dp0"

if not exist ".env" (
  echo Warning: .env was not found. Copy .env.example to .env and fill in your keys.
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating Python virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 (
    echo Failed to create virtual environment. Make sure Python 3 is installed.
    exit /b 1
  )
)

call ".venv\Scripts\activate.bat"

echo Installing dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Failed to install dependencies.
  exit /b 1
)

python main.py %*
exit /b %errorlevel%
