# 🎤 Home KTV Party System (家庭聚會 YouTube KTV 系統)

專為 **MacBook Air / Mac mini + iPad / iPhone + Google TV Streamer** 打造的家庭聚會多人點唱 KTV 系統。

## ✨ 核心功能
- 🔍 **YouTube 即時 KTV 搜尋**：支援自動加上「KTV 伴奏」關鍵字與熱門歌手分類。
- ⚡ **雙引擎無縫播放**：
  - 新歌點播後 **0.3 秒 YouTube IFrame 瞬間秒播**。
  - 背景透過 `yt-dlp` + `deno` 自動下載無廣告 MP4 音軌，完成後無縫切換至 WebAudio DSP 引擎。
- 🎛️ **即時消人聲（原唱 ⇄ 伴唱切換）**：WebAudio 立體聲中置相位抵銷 + 140Hz 低頻貝斯保留。
- 🎼 **即時升降 Key（±6 半音）**：雙延遲顆粒合成移調器（Granular Pitch Shifter），變調不變速。
- 🎙️ **KTV 麥克風即時混音 + 2.2 秒立體聲大廳迴音（Hall Reverb）**：
  - 內建 85Hz 防噴麥高通濾波、3.2kHz 人聲穿透力美化 EQ、人聲動態壓縮器（Compressor）與防喇叭嘯叫模式。
  - 支援從 iPhone / iPad 遠端即時調整「人聲音量」、「KTV 迴音強度」與「伴奏音量」。
- 🎉 **聚會互動彈幕與音效**：手機一鍵發送掌聲、歡呼、乾杯音效與跑馬燈彈幕至電視大螢幕。

## 🚀 回家後如何快速啟動（Mac mini / MacBook）

只需一行指令（腳本會自動建立 Python 虛擬環境並下載所需的 `yt-dlp` 與 `deno`）：

```bash
git clone <你的-GitHub-Repo-網址>
cd home-ktv
chmod +x start_ktv.sh
./start_ktv.sh
```

啟動後：
1. **電視端 / Mac 大螢幕**：打開瀏覽器前往 `http://<Mac區網IP>:8000/tv`
2. **iPad / iPhone 點歌台**：直接掃描電視畫面右下角的 **QR Code**，或前往 `http://<Mac區網IP>:8000/`（可透過 Safari「分享 -> 加入主畫面」安裝為全螢幕 App）。
