@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --onefile --windowed --name bedrok_loader bedrok_loader.py
echo.
echo Output: dist\bedrok_loader.exe
pause
