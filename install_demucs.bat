@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ====================================================
echo 🤖 正在安裝與設定 Meta Demucs AI 去人聲與導唱引擎 ^(Windows^)...
echo ====================================================

if not exist ".venv\Scripts\python.exe" (
    echo 📦 建立 Python 虛擬環境 ^(.venv^)...
    python -m venv .venv
    if errorlevel 1 (
        echo ❌ 找不到 Python！請先安裝 Python 3.10+ 並勾選 "Add Python to PATH"。
        pause
        exit /b 1
    )
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

if not exist "bin" mkdir bin
if not exist "cache" mkdir cache

echo 🔧 正在設定靜態 FFmpeg 音訊合成工具與預載 Demucs AI 模型權重...
python -c "import os, shutil, certifi, imageio_ffmpeg, torch; os.environ['SSL_CERT_FILE'] = certifi.where(); ff_src = imageio_ffmpeg.get_ffmpeg_exe(); ff_dst = os.path.join('bin', 'ffmpeg.exe'); shutil.copy2(ff_src, ff_dst) if not os.path.exists(ff_dst) else None; print('✓ FFmpeg 已就緒:', ff_dst); from demucs.pretrained import get_model; device = 'cuda' if torch.cuda.is_available() else 'cpu'; get_model('htdemucs'); print('✓ Meta Demucs (htdemucs) 模型預載完成！(硬體加速裝置: ' + device + ')')"

echo ====================================================
echo 🎉 Meta Demucs AI 引擎安裝完成！雙擊 start_ktv.bat 即可開唱！
echo ====================================================
pause
