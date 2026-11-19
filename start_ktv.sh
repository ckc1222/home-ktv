#!/bin/zsh
set -e
cd "$(dirname "$0")"

# 1. 自動建立 Python 虛擬環境並確認安裝 Meta Demucs 等套件
if [ ! -d ".venv" ]; then
  echo "📦 首次啟動：正在建立 Python 虛擬環境並安裝 Meta Demucs..."
  ./install_demucs.sh
else
  source .venv/bin/activate
  # 若舊環境尚未安裝 demucs，自動補裝
  if ! python3 -c "import demucs, imageio_ffmpeg, soundfile" >/dev/null 2>&1; then
    echo "🤖 偵測到尚未安裝 Meta Demucs AI 引擎，正在自動安裝..."
    ./install_demucs.sh
  fi
fi

# 2. 自動下載最新版獨立 yt-dlp 與 deno 解密引擎 (首次執行時)
mkdir -p bin cache
if [ ! -f "bin/yt-dlp" ]; then
  echo "⬇️ 正在下載最新版 yt-dlp_macos..."
  curl -L -s "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos" -o bin/yt-dlp
  chmod +x bin/yt-dlp
fi

if [ ! -f "bin/deno" ]; then
  echo "⬇️ 正在下載 Deno JS 簽名解密引擎..."
  curl -L -s "https://github.com/denoland/deno/releases/latest/download/deno-aarch64-apple-darwin.zip" -o bin/deno.zip
  unzip -q -o bin/deno.zip -d bin/
  rm -f bin/deno.zip
  chmod +x bin/deno
fi

export PATH="$(pwd)/bin:$PATH"
LOCAL_IP=$(python3 -c 'import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("8.8.8.8",80)); print(s.getsockname()[0]); s.close()' 2>/dev/null || echo "127.0.0.1")

echo "===================================================="
echo "🎤 家庭 KTV 歡唱伺服器已啟動 (Mac 防休眠模式 + Demucs AI 引擎)"
echo "📱 iPad / iPhone 點歌台網址: http://${LOCAL_IP}:8000/"
echo "📺 電視播放端 (Google TV) 網址: http://${LOCAL_IP}:8000/tv"
echo "===================================================="

# 使用 caffeinate 防止 Mac 在聚會期間休眠
exec caffeinate -dimsu uvicorn server:app --host 0.0.0.0 --port 8000
