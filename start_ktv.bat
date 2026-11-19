@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ====================================================
echo 🎤 正在檢查 Windows 家庭 KTV 系統環境...
echo ====================================================

:: 1. 自動建立 Python 虛擬環境並安裝套件 (含 Meta Demucs AI 引擎)
if not exist ".venv\Scripts\python.exe" (
    call install_demucs.bat
) else (
    call .venv\Scripts\activate.bat
    python -c "import demucs, imageio_ffmpeg, soundfile" >nul 2>&1
    if errorlevel 1 (
        echo 🤖 偵測到尚未安裝 Meta Demucs AI 引擎，正在自動安裝...
        call install_demucs.bat
    )
)

:: 2. 自動下載最新版 Windows yt-dlp.exe 與 deno.exe 解密引擎 (首次執行時)
if not exist "bin" mkdir bin
if not exist "cache" mkdir cache

if not exist "bin\yt-dlp.exe" (
    echo ⬇️ 正在下載最新版 yt-dlp.exe ^(Windows^)...
    curl -L -s "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe" -o "bin\yt-dlp.exe"
)

if not exist "bin\deno.exe" (
    echo ⬇️ 正在下載 Deno JS 簽名解密引擎 ^(Windows^)...
    curl -L -s "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip" -o "bin\deno.zip"
    tar -xf "bin\deno.zip" -C "bin"
    del /q "bin\deno.zip"
)

set "PATH=%~dp0bin;%PATH%"

for /f "delims=" %%i in ('python -c "import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('8.8.8.8',80)); print(s.getsockname()[0]); s.close()" 2^>nul') do set LOCAL_IP=%%i
if "%LOCAL_IP%"=="" set LOCAL_IP=127.0.0.1

echo ====================================================
echo 🎤 家庭 KTV 歡唱伺服器已啟動 ^(Windows 防休眠模式 + Demucs AI 引擎^)
echo 📱 iPad / iPhone 點歌台網址: http://%LOCAL_IP%:8000/
echo 📺 電視播放端 ^(Chrome^) 網址: http://%LOCAL_IP%:8000/tv
echo ====================================================

start "" "http://127.0.0.1:8000/tv"
python -m uvicorn server:app --host 0.0.0.0 --port 8000
pause
