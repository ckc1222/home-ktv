#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

OS_NAME="$(uname -s)"
ARCH_NAME="$(uname -m)"

# 1. 自動建立 Python 虛擬環境並確認安裝套件
if [ ! -d ".venv" ]; then
  echo "📦 首次啟動：正在建立 Python 虛擬環境並安裝套件..."
  ./install_demucs.sh
else
  source .venv/bin/activate
  if ! python3 -c "import demucs, soundfile" >/dev/null 2>&1; then
    echo "🤖 偵測到尚未安裝 Meta Demucs AI 引擎，正在自動安裝..."
    ./install_demucs.sh
  fi
fi

# 2. 依作業系統 (macOS vs Raspberry Pi Linux ARM64 / x86_64) 自動下載對應的 yt-dlp 與 deno
mkdir -p bin cache

if [ ! -f "bin/yt-dlp" ]; then
  if [ "$OS_NAME" = "Darwin" ]; then
    echo "⬇️ 正在下載最新版 yt-dlp_macos..."
    curl -L -s "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos" -o bin/yt-dlp
  elif [ "$ARCH_NAME" = "aarch64" ] || [ "$ARCH_NAME" = "arm64" ]; then
    echo "⬇️ 正在下載最新版 yt-dlp_linux_aarch64 (Raspberry Pi 64-bit)..."
    curl -L -s "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux_aarch64" -o bin/yt-dlp
  else
    echo "⬇️ 正在下載最新版 yt-dlp_linux..."
    curl -L -s "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux" -o bin/yt-dlp
  fi
  chmod +x bin/yt-dlp
fi

if [ ! -f "bin/deno" ]; then
  if [ "$OS_NAME" = "Darwin" ]; then
    echo "⬇️ 正在下載 Deno JS 解密引擎 (macOS)..."
    curl -L -s "https://github.com/denoland/deno/releases/latest/download/deno-aarch64-apple-darwin.zip" -o bin/deno.zip
  elif [ "$ARCH_NAME" = "aarch64" ] || [ "$ARCH_NAME" = "arm64" ]; then
    echo "⬇️ 正在下載 Deno JS 解密引擎 (Raspberry Pi ARM64)..."
    curl -L -s "https://github.com/denoland/deno/releases/latest/download/deno-aarch64-unknown-linux-gnu.zip" -o bin/deno.zip
  else
    echo "⬇️ 正在下載 Deno JS 解密引擎 (Linux x64)..."
    curl -L -s "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip" -o bin/deno.zip
  fi
  unzip -q -o bin/deno.zip -d bin/
  rm -f bin/deno.zip
  chmod +x bin/deno
fi

export PATH="$(pwd)/bin:$PATH"
LOCAL_IP=$(python3 -c 'import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("8.8.8.8",80)); print(s.getsockname()[0]); s.close()' 2>/dev/null || echo "127.0.0.1")

echo "===================================================="
echo "🎤 家庭 KTV 歡唱伺服器已啟動 ($OS_NAME / $ARCH_NAME)"
echo "📱 iPad / iPhone 點歌台網址: http://${LOCAL_IP}:8000/"
echo "📺 電視播放端網址: http://${LOCAL_IP}:8000/tv"
echo "===================================================="

if [ "$OS_NAME" = "Darwin" ]; then
  exec caffeinate -dimsu uvicorn server:app --host 0.0.0.0 --port 8000
else
  exec uvicorn server:app --host 0.0.0.0 --port 8000
fi
