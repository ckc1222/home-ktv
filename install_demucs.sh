#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

OS_NAME="$(uname -s)"
ARCH_NAME="$(uname -m)"

echo "===================================================="
echo "🤖 正在安裝與設定 Meta Demucs AI 引擎 ($OS_NAME / $ARCH_NAME)..."
echo "===================================================="

# 在 Raspberry Pi / Ubuntu / Debian 上若缺少 python3-venv 或 libsndfile1，提示或自動安裝
if [ "$OS_NAME" = "Linux" ]; then
  if ! dpkg -s python3-venv libsndfile1 ffmpeg >/dev/null 2>&1; then
    echo "📦 正在為 Raspberry Pi / Linux 安裝基礎音訊套件 (python3-venv, libsndfile1, ffmpeg)..."
    sudo apt-get update && sudo apt-get install -y python3-venv python3-pip libsndfile1 ffmpeg unzip curl || true
  fi
fi

if [ ! -d ".venv" ]; then
  echo "📦 建立 Python 虛擬環境 (.venv)..."
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

mkdir -p bin cache

echo "🔧 正在設定 FFmpeg 音訊合成工具與預載 Demucs AI 模型權重..."
python3 -c '
import os, shutil, certifi, torch
os.environ["SSL_CERT_FILE"] = certifi.where()

ff_dst = os.path.join("bin", "ffmpeg")
if not os.path.exists(ff_dst):
    try:
        import imageio_ffmpeg
        ff_src = imageio_ffmpeg.get_ffmpeg_exe()
        if ff_src and os.path.exists(ff_src):
            shutil.copy2(ff_src, ff_dst)
            os.chmod(ff_dst, 0o755)
    except Exception:
        sys_ff = shutil.which("ffmpeg")
        if sys_ff:
            os.symlink(sys_ff, ff_dst)
print("✓ FFmpeg 已就緒")

from demucs.pretrained import get_model
device = "mps" if (hasattr(torch.backends, "mps") and torch.backends.mps.is_available()) else ("cuda" if torch.cuda.is_available() else "cpu")
model = get_model("htdemucs")
print(f"✓ Meta Demucs (htdemucs) 模型預載完成！(硬體加速裝置: {device})")
'

echo "===================================================="
echo "🎉 安裝完成！執行 ./start_ktv.sh 即可開唱！"
echo "===================================================="
