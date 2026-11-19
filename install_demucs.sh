#!/bin/zsh
set -e
cd "$(dirname "$0")"

echo "===================================================="
echo "🤖 正在安裝與設定 Meta Demucs AI 去人聲與導唱引擎 (macOS)..."
echo "===================================================="

if [ ! -d ".venv" ]; then
  echo "📦 建立 Python 虛擬環境 (.venv)..."
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

mkdir -p bin cache

echo "🔧 正在設定靜態 FFmpeg 音訊合成工具與預載 Demucs AI 模型權重..."
python3 -c '
import os, shutil, certifi, imageio_ffmpeg, torch
os.environ["SSL_CERT_FILE"] = certifi.where()

ff_src = imageio_ffmpeg.get_ffmpeg_exe()
ff_dst = os.path.join("bin", "ffmpeg")
if not os.path.exists(ff_dst):
    shutil.copy2(ff_src, ff_dst)
    os.chmod(ff_dst, 0o755)
print("✓ FFmpeg 已就緒:", ff_dst)

from demucs.pretrained import get_model
device = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
model = get_model("htdemucs")
print(f"✓ Meta Demucs (htdemucs) 模型預載完成！(硬體加速裝置: {device})")
'

echo "===================================================="
echo "🎉 Meta Demucs AI 引擎安裝完成！執行 ./start_ktv.sh 即可開唱！"
echo "===================================================="
