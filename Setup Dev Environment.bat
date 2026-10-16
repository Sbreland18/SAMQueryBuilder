@echo off
cd /d "%~dp0"
call tools\find_python.bat || exit /b 1
echo Using: %PY%
%PY% --version
%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements-dev.txt
echo.
echo Done. You can now run "Build GUI.bat".
pause
