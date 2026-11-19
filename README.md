# 🎤 Home KTV Party System (家庭聚會 YouTube KTV 系統)

專為 **macOS (MacBook / Mac mini) & Windows PC + iPad / iPhone + Google TV Streamer** 打造的家庭聚會多人點唱 KTV 系統。

## ✨ 核心功能
- 🔍 **YouTube 即時 KTV 搜尋**：支援自動加上「KTV 伴奏」關鍵字與熱門歌手分類。
- 🤖 **Meta Demucs AI 深度學習去人聲 ＋ 4 段式導唱比例切換**：
  - 採用 Meta `htdemucs` 深度學習音源分離引擎（支援 Apple Silicon M 系列晶片 `MPS` 與 NVIDIA `CUDA` GPU 硬體加速）。
  - 將任何一般 YouTube 原版 MV 拆分為 **「100% 無損純伴奏音軌（鼓 + 貝斯 + 樂器）」** 與 **「獨立純人聲導唱音軌」**，伴奏音量 100% 飽滿不衰減。
  - 支援 **0.001 秒無縫切換 4 種導唱模式**：
    - `🎵 100% 原唱`
    - `🎤 50% 半導唱`（伴奏 100% + 保留 50% 歌手人聲帶唱）
    - `🎤 20% 微導唱`（伴奏 100% + 保留 20% 微弱人聲提示旋律）
    - `🤖 0% 純伴奏`（100% 消除歌手人聲）
- 🎼 **即時升降 Key（±6 半音）**：雙延遲顆粒合成移調器（Granular Pitch Shifter），變調不變速。
- 🎙️ **超低延遲 KTV 麥克風 + 立體聲大廳迴音（Hall Reverb）**：
  - 支援 **🎧 100% 純原音極速直通模式**（`latencyHint: 0`）與 **✨ KTV 迴音混響模式**。
  - 支援自選收音麥克風與輸出喇叭／耳機，並可從 iPhone / iPad 遠端即時調整「人聲音量」、「KTV 迴音強度」與「伴奏音量」。
- 🎉 **聚會互動彈幕與音效**：手機一鍵發送掌聲、歡呼、乾杯音效與跑馬燈彈幕至電視大螢幕。

---

## 🚀 快速啟動教學

### 🍎 macOS (MacBook Air / Mac mini)

打開終端機（Terminal）執行：

```bash
git clone https://github.com/ckc1222/home-ktv.git
cd home-ktv
chmod +x install_demucs.sh start_ktv.sh
./install_demucs.sh   # 獨立安裝 Meta Demucs AI 引擎、FFmpeg 並預載模型權重
./start_ktv.sh        # 啟動 KTV 伺服器（若尚未執行 install_demucs.sh 也會自動觸發安裝）
```

### 🪟 Windows 10 / 11

1. 確認電腦已安裝 [Python 3.10+](https://www.python.org/downloads/)（安裝時請勾選 **"Add Python to PATH"**）。
2. 下載或 Clone 本專案：
   ```cmd
   git clone https://github.com/ckc1222/home-ktv.git
   cd home-ktv
   ```
3. 雙擊執行 **`install_demucs.bat`**（自動安裝 Meta Demucs AI 模型與靜態 `ffmpeg.exe`），接著雙擊 **`start_ktv.bat`** 即可啟動！（直接雙擊 `start_ktv.bat` 也會自動檢查並安裝 Demucs）。

---

## 📱 如何點歌與歡唱
1. **電視端 / 電腦大螢幕**：打開 Chrome 前往 `http://127.0.0.1:8000/tv`
2. **iPad / iPhone 點歌台**：直接用手機相機掃描電視畫面右下角的 **QR Code**，或前往 `http://<電腦區網IP>:8000/`（可透過 Safari「分享 -> 加入主畫面」安裝為全螢幕 App）。
