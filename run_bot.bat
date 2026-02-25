@echo off
cd /d "%~dp0"
start "AntispamBot" /min python antispam_bot.py
python bot.py
pause
