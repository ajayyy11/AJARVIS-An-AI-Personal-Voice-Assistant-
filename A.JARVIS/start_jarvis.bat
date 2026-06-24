@echo off
cd /d "%~dp0"
call "%USERPROFILE%\anaconda3\Scripts\activate.bat" ajarvis
python app.py
pause
