@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 皮卡丘桌宠
echo 正在启动皮卡丘桌宠...
echo.
"C:\Users\28374\.workbuddy\binaries\python\versions\3.13.12\python.exe" -u main.py
echo.
echo 程序已退出（错误信息见上方，或查看 logs\ 目录）
pause
