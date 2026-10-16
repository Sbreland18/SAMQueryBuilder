@echo off
cd /d "%~dp0"
call tools\find_python.bat || exit /b 1
%PY% -c "import PySide6" >nul 2>&1 || (
  echo Installing required packages ^(first run only^)...
  %PY% -m pip install -r requirements.txt || ( pause & exit /b 1 )
)
%PY% main.py
if errorlevel 1 pause
