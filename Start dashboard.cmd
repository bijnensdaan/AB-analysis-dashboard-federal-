@echo off
pushd "%~dp0"
where pythonw.exe >nul 2>nul
if errorlevel 1 (
  echo Python is niet gevonden. Start vanuit deze map met: python -B validatietool/open_dashboard.py
  pause
  popd
  exit /b 1
)
start "" /b pythonw.exe -B "validatietool\open_dashboard.py"
popd
