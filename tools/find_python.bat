@echo off
rem Finds a real Python 3 install and stores the command in %PY%.
rem Ignores the Microsoft Store "python" shortcut.
set "PY="

rem 1) Python launcher (installed with python.org Python)
py -3 --version >nul 2>&1 && set "PY=py -3" && goto :found

rem 2) Common install folders
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%D\python.exe" set "PY="%%D\python.exe""
if defined PY goto :found
for /d %%D in ("%ProgramFiles%\Python3*") do if exist "%%D\python.exe" set "PY="%%D\python.exe""
if defined PY goto :found

rem 3) python on PATH (the Store shortcut fails this test)
python --version >nul 2>&1 && set "PY=python" && goto :found

echo.
echo  Python 3 was not found on this computer.
echo  (The message about the Microsoft Store is Windows' placeholder shortcut, not real Python.)
echo.
echo  Option A: let this script install Python 3.12 now using winget.
echo  Option B: download it from https://www.python.org/downloads/windows/
echo            and tick "Add python.exe to PATH" during setup.
echo.
where winget >nul 2>&1 || goto :nowinget
choice /c YN /m "Install Python 3.12 with winget now"
if errorlevel 2 goto :nowinget
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%D\python.exe" set "PY="%%D\python.exe""
if defined PY goto :found
echo.
echo  Python was installed. Close this window and run the file again.
pause
exit /b 1

:nowinget
pause
exit /b 1

:found
exit /b 0
