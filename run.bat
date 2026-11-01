@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo 正在啟動剪取 OCR 辨識工具...
python snipping_ocr.py
if %errorlevel% neq 0 (
    echo.
    echo 執行發生錯誤，請確認已安裝相依套件：pip install -r requirements.txt
    pause
)
