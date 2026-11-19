# 🎤 Home KTV Party System (家庭聚會 YouTube KTV 系統)

專為 **macOS (MacBook / Mac mini) & Windows PC + iPad / iPhone + Google TV Streamer** 打造的家庭聚會多人點唱 KTV 系統。

## ✨ 核心功能
- 🔍 **YouTube 即時 KTV 搜尋**：支援自動加上「KTV 伴奏」關鍵字與熱門歌手分類。
- ⚡ **雙引擎無縫播放**：
  - 新歌點播後 **0.3 秒 YouTube IFrame 瞬間秒播**。
  - 背景透過 `yt-dlp` + `deno` 自動下載無廣告 MP4 音軌，完成後無縫切換至 WebAudio DSP 引擎。
- 🎛️ **即時消人聲（原唱 ⇄ 伴唱切換）**：WebAudio 立體聲中置相位抵銷 + 140Hz 低頻貝斯保留。
- 🎼 **即時升降 Key（±6 半音）**：雙延遲顆粒合成移調器（Granular Pitch Shifter），變調不變速。
- 🎙️ **單一混音引擎 KTV 麥克風 + 立體聲大廳迴音（Hall Reverb）**：
  - 支援 **🎧 100% 純原音極速直通模式** 與 **✨ KTV 迴音混響模式**。
  - 伴奏與麥克風共用單一超低延遲 `AudioContext`（`latencyHint: 0`），支援自選收音麥克風與輸出喇叭／耳機。
  - 支援從 iPhone / iPad 遠端即時調整「人聲音量」、「KTV 迴音強度」與「伴奏音量」。
- 🎉 **聚會互動彈幕與音效**：手機一鍵發送掌聲、歡呼、乾杯音效與跑馬燈彈幕至電視大螢幕。

---

## 🚀 快速啟動教學

### 🍎 macOS (MacBook Air / Mac mini)

打開終端機（Terminal）執行（腳本會自動建立 Python 虛擬環境並下載 macOS 版 `yt-dlp` 與 `deno`）：

```bash
git clone https://github.com/ckc1222/home-ktv.git
cd home-ktv
chmod +x start_ktv.sh
./start_ktv.sh
```

### 🪟 Windows 10 / 11

1. 確認電腦已安裝 [Python 3.10+](https://www.python.org/downloads/)（安裝時請勾選 **"Add Python to PATH"**）。
2. 下載或 Clone 本專案：
   ```cmd
   git clone https://github.com/ckc1222/home-ktv.git
   cd home-ktv
   ```
3. 直接**滑鼠雙擊執行 `start_ktv.bat`**（或在命令提示字元輸入 `start_ktv.bat`）：
   - 首次執行會自動建立 `.venv` 虛擬環境、安裝所需套件，並自動下載 Windows 版 `yt-dlp.exe` 與 `deno.exe`。
   - 啟動後會自動開啟 Windows 防休眠模式並彈出 `/tv` 電視播放端網頁！（首次執行若 Windows 防火牆跳出詢問，請勾選「私人網路」並允許存取，這樣手機才連得進來）。

---

## 📱 如何點歌與歡唱
1. **電視端 / 電腦大螢幕**：打開 Chrome 前往 `http://127.0.0.1:8000/tv`
2. **iPad / iPhone 點歌台**：直接用手機相機掃描電視畫面右下角的 **QR Code**，或前往 `http://<電腦區網IP>:8000/`（可透過 Safari「分享 -> 加入主畫面」安裝為全螢幕 App）。
