import asyncio
import json
import os
import re
import shutil
import socket
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
BIN_DIR = BASE_DIR / "bin"
CACHE_DIR = BASE_DIR / "cache"
BIN_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)

# 自動將 imageio_ffmpeg 的靜態 ffmpeg 執行檔複製到 bin/ 目錄（跨平台支援 macOS 與 Windows）
try:
    import imageio_ffmpeg

    ffmpeg_target = BIN_DIR / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if not ffmpeg_target.exists():
        shutil.copy2(imageio_ffmpeg.get_ffmpeg_exe(), ffmpeg_target)
        if os.name != "nt":
            os.chmod(ffmpeg_target, 0o755)
except Exception:
    pass

# 設定 SSL 憑證路徑，確保 macOS / Windows 下載 AI 模型權重不報錯
try:
    import certifi

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except Exception:
    pass

# 將獨立版 yt-dlp、deno 與 ffmpeg 加入環境變數 PATH (相容 macOS ':' 與 Windows ';')
os.environ["PATH"] = f"{BIN_DIR}{os.pathsep}{os.environ.get('PATH', '')}"

# Windows 防休眠模式 (等同 macOS caffeinate)
if os.name == "nt":
    try:
        import ctypes

        ctypes.windll.kernel32.SetThreadExecutionState(0x80000003)
    except Exception:
        pass

app = FastAPI(title="Home KTV Party Server")

# 全域快取的 Demucs AI 模型（避免每次消人聲重新載入模型）
_demucs_model = None
_demucs_device = None


def get_demucs_model():
    global _demucs_model, _demucs_device
    if _demucs_model is not None:
        return _demucs_model, _demucs_device
    import torch
    from demucs.pretrained import get_model

    if torch.backends.mps.is_available():
        _demucs_device = "mps"
    elif torch.cuda.is_available():
        _demucs_device = "cuda"
    else:
        _demucs_device = "cpu"

    model = get_model("htdemucs")
    model.to(_demucs_device)
    model.eval()
    _demucs_model = model
    print(f"[AI Demucs] Loaded htdemucs on device: {_demucs_device}")
    return _demucs_model, _demucs_device


def get_local_ip() -> str:
    """取得電腦在區域網路 (Wi-Fi / 有線網路) 的 IP 位址"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def is_video_cached(video_id: str) -> bool:
    mp4_path = CACHE_DIR / f"{video_id}.mp4"
    return mp4_path.exists() and mp4_path.stat().st_size > 100_000


def is_ai_inst_cached(video_id: str) -> bool:
    inst_path = CACHE_DIR / f"{video_id}_inst.mp4"
    vocal_path = CACHE_DIR / f"{video_id}_vocal.m4a"
    return (
        inst_path.exists()
        and inst_path.stat().st_size > 100_000
        and vocal_path.exists()
        and vocal_path.stat().st_size > 20_000
    )


class KTVRoomState:
    def __init__(self):
        self.queue: List[Dict] = []
        self.current_song: Optional[Dict] = None
        self.is_playing: bool = True
        self.vocal_cut: bool = False  # 相容舊欄位 (True 代表 vocal_level < 100)
        self.vocal_level: int = 100   # 人聲導唱比例：100=原唱, 50=半導唱, 20=微導唱, 0=純伴奏
        self.ai_processing_vid: Optional[str] = None
        self.pitch_semitones: int = 0  # -6 ~ +6 半音
        self.volume: int = 85          # 伴奏音量 (0 ~ 100)
        self.mic_enabled: bool = False
        self.mic_volume: int = 100     # 麥克風人聲音量 (0 ~ 200)
        self.reverb_level: int = 0     # KTV 迴音強度 (0 ~ 100)
        self.anti_howl: bool = False   # 防喇叭嘯叫模式

    def to_dict(self):
        cur = None
        if self.current_song:
            vid = self.current_song.get("video_id", "")
            cur = {
                **self.current_song,
                "cached": is_video_cached(vid),
                "ai_cached": is_ai_inst_cached(vid),
                "ai_processing": self.ai_processing_vid == vid,
            }
        q_list = [
            {
                **s,
                "cached": is_video_cached(s.get("video_id", "")),
                "ai_cached": is_ai_inst_cached(s.get("video_id", "")),
            }
            for s in self.queue
        ]
        return {
            "type": "state_update",
            "current_song": cur,
            "queue": q_list,
            "is_playing": self.is_playing,
            "vocal_cut": self.vocal_level < 100,
            "vocal_level": self.vocal_level,
            "ai_processing_vid": self.ai_processing_vid,
            "pitch_semitones": self.pitch_semitones,
            "volume": self.volume,
            "mic_enabled": self.mic_enabled,
            "mic_volume": self.mic_volume,
            "reverb_level": self.reverb_level,
            "anti_howl": self.anti_howl,
            "server_ip": get_local_ip(),
        }


room = KTVRoomState()
connected_clients: List[WebSocket] = []
downloading_tasks: Dict[str, asyncio.Task] = {}
ai_tasks: Dict[str, asyncio.Task] = {}


async def broadcast(payload: dict):
    dead = []
    message = json.dumps(payload, ensure_ascii=False)
    for ws in connected_clients:
        try:
            await ws.send_text(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in connected_clients:
            connected_clients.remove(ws)


async def broadcast_state():
    await broadcast(room.to_dict())


def download_video_sync(video_id: str) -> bool:
    """使用最新獨立版 yt-dlp + deno 在背景下載高品質 MP4"""
    if not re.match(r"^[A-Za-z0-9_-]{6,20}$", video_id):
        return False
    target = CACHE_DIR / f"{video_id}.mp4"
    if is_video_cached(video_id):
        return True

    temp_target = CACHE_DIR / f"{video_id}.temp.mp4"
    yt_dlp_name = "yt-dlp.exe" if os.name == "nt" else "yt-dlp"
    yt_dlp_bin = (
        str(BIN_DIR / yt_dlp_name) if (BIN_DIR / yt_dlp_name).exists() else "yt-dlp"
    )
    cmd = [
        yt_dlp_bin,
        "--no-playlist",
        "--sleep-interval",
        "0",
        "-f",
        "18/best[ext=mp4][acodec!=none][vcodec!=none]/best[ext=mp4]",
        "-o",
        str(temp_target),
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    try:
        subprocess.run(cmd, check=True, timeout=120)
        if temp_target.exists() and temp_target.stat().st_size > 100_000:
            if target.exists():
                target.unlink()
            temp_target.rename(target)
            return True
    except Exception as e:
        print(f"[yt-dlp cache] Failed for {video_id}: {e}")
    return False


def run_ai_vocal_removal_sync(video_id: str) -> bool:
    """使用 Meta Demucs (htdemucs) 深度學習模型分離 100% 純伴奏（鼓+貝斯+樂器，完全不掉音量）"""
    if is_ai_inst_cached(video_id):
        return True
    if not is_video_cached(video_id):
        if not download_video_sync(video_id):
            return False

    src_mp4 = CACHE_DIR / f"{video_id}.mp4"
    out_inst_mp4 = CACHE_DIR / f"{video_id}_inst.mp4"
    out_vocal_m4a = CACHE_DIR / f"{video_id}_vocal.m4a"
    temp_in_wav = CACHE_DIR / f"{video_id}_in.wav"
    temp_inst_wav = CACHE_DIR / f"{video_id}_inst.wav"
    temp_vocal_wav = CACHE_DIR / f"{video_id}_vocal.wav"
    temp_inst_mp4 = CACHE_DIR / f"{video_id}_inst.temp.mp4"
    temp_vocal_m4a = CACHE_DIR / f"{video_id}_vocal.temp.m4a"

    ffmpeg_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    ffmpeg_bin = (
        str(BIN_DIR / ffmpeg_name) if (BIN_DIR / ffmpeg_name).exists() else "ffmpeg"
    )

    try:
        import soundfile as sf
        import torch
        from demucs.apply import apply_model

        model, device = get_demucs_model()

        # 1. 轉出 44.1kHz 立體聲 WAV
        subprocess.run(
            [
                ffmpeg_bin,
                "-y",
                "-i",
                str(src_mp4),
                "-vn",
                "-ac",
                "2",
                "-ar",
                "44100",
                str(temp_in_wav),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # 2. 執行 Demucs 深度學習音源分離
        audio, sr = sf.read(str(temp_in_wav), dtype="float32")
        wav = torch.from_numpy(audio.T)
        ref = wav.mean(0)
        mean_val = ref.mean()
        std_val = ref.std() + 1e-8
        wav_norm = (wav - mean_val) / std_val

        with torch.no_grad():
            sources = apply_model(
                model,
                wav_norm[None],
                device=device,
                shifts=0,
                split=True,
                overlap=0.1,
            )[0]
            sources = sources * std_val + mean_val

        # sources: 0=drums, 1=bass, 2=other, 3=vocals
        inst_audio = (sources[0] + sources[1] + sources[2]).cpu().numpy().T
        vocal_audio = sources[3].cpu().numpy().T
        sf.write(str(temp_inst_wav), inst_audio, sr)
        sf.write(str(temp_vocal_wav), vocal_audio, sr)

        # 3. 將純伴奏音軌與原影片無損合成 (-c:v copy 只需 0.3 秒)
        subprocess.run(
            [
                ffmpeg_bin,
                "-y",
                "-i",
                str(src_mp4),
                "-i",
                str(temp_inst_wav),
                "-c:v",
                "copy",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                str(temp_inst_mp4),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # 4. 將分離出的純人聲轉為獨立導唱音軌 (_vocal.m4a)，供前端 0% / 20% / 50% / 100% 即時混音導唱！
        subprocess.run(
            [
                ffmpeg_bin,
                "-y",
                "-i",
                str(temp_vocal_wav),
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                str(temp_vocal_m4a),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        if (
            temp_inst_mp4.exists()
            and temp_inst_mp4.stat().st_size > 100_000
            and temp_vocal_m4a.exists()
        ):
            if out_inst_mp4.exists():
                out_inst_mp4.unlink()
            if out_vocal_m4a.exists():
                out_vocal_m4a.unlink()
            temp_inst_mp4.rename(out_inst_mp4)
            temp_vocal_m4a.rename(out_vocal_m4a)
            return True
    except Exception as e:
        print(f"[AI Demucs] Failed for {video_id}: {e}")
    finally:
        for p in [temp_in_wav, temp_inst_wav, temp_vocal_wav, temp_inst_mp4, temp_vocal_m4a]:
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass
    return False


async def ensure_cached_async(video_id: str):
    if not video_id or is_video_cached(video_id):
        return
    if video_id in downloading_tasks and not downloading_tasks[video_id].done():
        return

    async def _worker():
        loop = asyncio.get_event_loop()
        ok = await loop.run_in_executor(None, download_video_sync, video_id)
        if ok:
            print(f"[yt-dlp cache] Ready: {video_id}.mp4")
            await broadcast_state()
            await broadcast(
                {
                    "type": "cache_ready",
                    "video_id": video_id,
                }
            )

    downloading_tasks[video_id] = asyncio.create_task(_worker())


async def ensure_ai_inst_async(video_id: str):
    """在背景啟動 Demucs AI 去人聲任務，完成後即時通知電視端無縫切換為純伴奏"""
    if not video_id:
        return
    if is_ai_inst_cached(video_id):
        await broadcast_state()
        await broadcast({"type": "ai_inst_ready", "video_id": video_id})
        return
    if video_id in ai_tasks and not ai_tasks[video_id].done():
        return

    async def _ai_worker():
        room.ai_processing_vid = video_id
        await broadcast_state()
        await broadcast(
            {
                "type": "toast",
                "text": "🤖 Apple M4 AI 正在深度分離純伴奏（約需 25 秒，完成後自動切換）...",
            }
        )
        loop = asyncio.get_event_loop()
        ok = await loop.run_in_executor(None, run_ai_vocal_removal_sync, video_id)
        if room.ai_processing_vid == video_id:
            room.ai_processing_vid = None
        if ok:
            print(f"[AI Demucs] Ready: {video_id}_inst.mp4")
            await broadcast_state()
            await broadcast({"type": "ai_inst_ready", "video_id": video_id})
            await broadcast(
                {
                    "type": "toast",
                    "text": "✨ AI 純伴奏分離完成！已切換為 100% 滿音量純伴奏模式！",
                }
            )
        else:
            room.vocal_cut = False
            await broadcast_state()
            await broadcast(
                {
                    "type": "toast",
                    "text": "⚠️ AI 去人聲處理失敗，維持原唱播放",
                }
            )

    ai_tasks[video_id] = asyncio.create_task(_ai_worker())


def search_youtube_sync(query: str, max_results: int = 16) -> List[Dict]:
    """快速搜尋 YouTube 影片"""
    encoded = urllib.parse.quote(query)
    url = f"https://www.youtube.com/results?search_query={encoded}&hl=zh-TW"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        html = resp.read().decode("utf-8", errors="ignore")

    match = re.search(r"var ytInitialData = (\{.*?\});</script>", html)
    if not match:
        return []

    data = json.loads(match.group(1))
    results = []
    try:
        sections = (
            data["contents"]["twoColumnSearchResultsRenderer"]["primaryContents"][
                "sectionListRenderer"
            ]["contents"]
        )
        for section in sections:
            items = section.get("itemSectionRenderer", {}).get("contents", [])
            for item in items:
                video = item.get("videoRenderer")
                if not video:
                    continue
                video_id = video.get("videoId")
                title_runs = video.get("title", {}).get("runs", [])
                title = "".join(r.get("text", "") for r in title_runs)
                channel_runs = video.get("ownerText", {}).get("runs", [])
                channel = "".join(r.get("text", "") for r in channel_runs)
                duration = video.get("lengthText", {}).get("simpleText", "MV")
                thumbs = video.get("thumbnail", {}).get("thumbnails", [])
                thumbnail = (
                    thumbs[-1]["url"]
                    if thumbs
                    else f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
                )
                if video_id and title:
                    results.append(
                        {
                            "video_id": video_id,
                            "title": title,
                            "channel": channel,
                            "duration": duration,
                            "thumbnail": thumbnail,
                        }
                    )
                    if len(results) >= max_results:
                        return results
    except Exception:
        pass
    return results


@app.get("/api/info")
async def api_info(request: Request):
    host_header = request.headers.get("host", f"{get_local_ip()}:8000")
    port = host_header.split(":")[-1] if ":" in host_header else "8000"
    local_ip = get_local_ip()
    return {
        "server_ip": local_ip,
        "port": port,
        "controller_url": f"http://{local_ip}:{port}/",
        "tv_url": f"http://{local_ip}:{port}/tv",
    }


@app.get("/api/search")
async def api_search(q: str, ktv_mode: bool = True):
    if not q.strip():
        return {"results": []}
    search_query = (
        f"{q.strip()} KTV 伴奏"
        if ktv_mode and "ktv" not in q.lower() and "伴奏" not in q
        else q.strip()
    )
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, search_youtube_sync, search_query)
    return {"query": search_query, "results": results}


@app.get("/api/stream/{video_id}")
async def serve_cached_or_download_stream(video_id: str):
    """提供本地快取的無廣告原版 MP4 檔案"""
    if not is_video_cached(video_id):
        loop = asyncio.get_event_loop()
        ok = await loop.run_in_executor(None, download_video_sync, video_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Stream cache not ready")

    mp4_path = CACHE_DIR / f"{video_id}.mp4"
    return FileResponse(
        path=str(mp4_path),
        media_type="video/mp4",
        headers={"Access-Control-Allow-Origin": "*"},
    )


@app.get("/api/stream_inst/{video_id}")
async def serve_ai_instrumental_stream(video_id: str):
    """提供經由 Meta Demucs AI 分離後的 100% 純伴奏 MP4 檔案"""
    if not is_ai_inst_cached(video_id):
        raise HTTPException(status_code=404, detail="AI instrumental not ready yet")

    inst_path = CACHE_DIR / f"{video_id}_inst.mp4"
    return FileResponse(
        path=str(inst_path),
        media_type="video/mp4",
        headers={"Access-Control-Allow-Origin": "*"},
    )


@app.get("/api/stream_vocal/{video_id}")
async def serve_ai_vocal_stream(video_id: str):
    """提供經由 Meta Demucs AI 分離後的純人聲導唱 M4A 音軌"""
    vocal_path = CACHE_DIR / f"{video_id}_vocal.m4a"
    if not vocal_path.exists():
        raise HTTPException(status_code=404, detail="AI vocal track not ready yet")

    return FileResponse(
        path=str(vocal_path),
        media_type="audio/mp4",
        headers={"Access-Control-Allow-Origin": "*"},
    )


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connected_clients.append(ws)
    await ws.send_text(json.dumps(room.to_dict(), ensure_ascii=False))

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            action = msg.get("action")

            if action == "add_song":
                song = msg.get("song", {})
                priority = msg.get("priority", False)
                vid = song.get("video_id", "")
                if room.current_song is None:
                    room.current_song = song
                    room.is_playing = True
                    room.vocal_cut = False
                    room.vocal_level = 100
                    room.pitch_semitones = 0
                else:
                    if priority:
                        room.queue.insert(0, song)
                    else:
                        room.queue.append(song)

                await ensure_cached_async(vid)
                await broadcast_state()
                await broadcast(
                    {
                        "type": "toast",
                        "text": f"{'⚡ 插播成功' if priority else '🎵 已點歌曲'}：{song.get('title', '')[:28]}",
                    }
                )

            elif action == "next_song":
                if room.queue:
                    room.current_song = room.queue.pop(0)
                    room.is_playing = True
                    room.vocal_cut = False
                    room.vocal_level = 100
                    room.pitch_semitones = 0
                    await ensure_cached_async(room.current_song.get("video_id", ""))
                else:
                    room.current_song = None
                await broadcast_state()
                await broadcast({"type": "command", "command": "next_song"})

            elif action == "toggle_play":
                room.is_playing = not room.is_playing
                await broadcast_state()
                await broadcast(
                    {
                        "type": "command",
                        "command": "toggle_play",
                        "is_playing": room.is_playing,
                    }
                )

            elif action == "replay":
                await broadcast({"type": "command", "command": "replay"})
                await broadcast({"type": "toast", "text": "🔄 重新開始播放本曲"})

            elif action == "toggle_vocal" or action == "set_vocal_level":
                if action == "set_vocal_level" and "level" in msg:
                    room.vocal_level = max(0, min(100, int(msg["level"])))
                else:
                    # 循環切換：100% 原唱 -> 50% 半導唱 -> 20% 微導唱 -> 0% 純伴奏 -> 100% 原唱
                    cycle = {100: 50, 50: 20, 20: 0, 0: 100}
                    room.vocal_level = cycle.get(room.vocal_level, 0)

                room.vocal_cut = room.vocal_level < 100
                cur_vid = (
                    room.current_song.get("video_id", "") if room.current_song else ""
                )
                await broadcast_state()
                if room.vocal_level < 100 and cur_vid:
                    if is_ai_inst_cached(cur_vid):
                        label_map = {
                            50: "🎤 已切換為：50% 人聲半導唱 + 100% 伴奏",
                            20: "🎤 已切換為：20% 人聲微導唱 + 100% 伴奏",
                            0: "🤖 已切換為：0% 人聲（100% AI 純伴奏）",
                        }
                        await broadcast(
                            {
                                "type": "toast",
                                "text": label_map.get(
                                    room.vocal_level,
                                    f"🎤 已切換為：{room.vocal_level}% 人聲導唱",
                                ),
                            }
                        )
                    else:
                        await ensure_ai_inst_async(cur_vid)
                else:
                    await broadcast(
                        {
                            "type": "toast",
                            "text": "🎵 已切換為：100% 原唱模式",
                        }
                    )

            elif action == "set_pitch":
                delta = int(msg.get("delta", 0))
                if delta == 0:
                    room.pitch_semitones = 0
                else:
                    room.pitch_semitones = max(-6, min(6, room.pitch_semitones + delta))
                await broadcast_state()
                pitch_label = (
                    "原調 (0)"
                    if room.pitch_semitones == 0
                    else f"{'+' if room.pitch_semitones > 0 else ''}{room.pitch_semitones} 半音"
                )
                await broadcast({"type": "toast", "text": f"🎼 升降調：{pitch_label}"})

            elif action == "update_mic":
                if "mic_enabled" in msg:
                    room.mic_enabled = bool(msg["mic_enabled"])
                if "mic_volume" in msg:
                    room.mic_volume = max(0, min(200, int(msg["mic_volume"])))
                if "reverb_level" in msg:
                    room.reverb_level = max(0, min(100, int(msg["reverb_level"])))
                if "volume" in msg:
                    room.volume = max(0, min(100, int(msg["volume"])))
                if "anti_howl" in msg:
                    room.anti_howl = bool(msg["anti_howl"])
                await broadcast_state()
                if "toast" in msg:
                    await broadcast({"type": "toast", "text": msg["toast"]})

            elif action == "remove_song":
                idx = int(msg.get("index", -1))
                if 0 <= idx < len(room.queue):
                    removed = room.queue.pop(idx)
                    await broadcast_state()
                    await broadcast(
                        {
                            "type": "toast",
                            "text": f"🗑️ 已移除：{removed.get('title', '')[:20]}",
                        }
                    )

            elif action == "promote_song":
                idx = int(msg.get("index", -1))
                if 0 < idx < len(room.queue):
                    song = room.queue.pop(idx)
                    room.queue.insert(0, song)
                    await ensure_cached_async(song.get("video_id", ""))
                    await broadcast_state()
                    await broadcast(
                        {
                            "type": "toast",
                            "text": f"⚡ 已插播至下一首：{song.get('title', '')[:20]}",
                        }
                    )

            elif action == "reaction":
                await broadcast(
                    {
                        "type": "reaction",
                        "emoji": msg.get("emoji", "👏"),
                        "label": msg.get("label", "好聽！"),
                        "sound": msg.get("sound", "applause"),
                        "sender": msg.get("sender", "包廂好友"),
                    }
                )

            elif action == "barrage":
                text = msg.get("text", "").strip()
                if text:
                    await broadcast(
                        {
                            "type": "barrage",
                            "text": text[:50],
                            "sender": msg.get("sender", "包廂好友"),
                        }
                    )

    except WebSocketDisconnect:
        if ws in connected_clients:
            connected_clients.remove(ws)


@app.get("/", response_class=HTMLResponse)
async def serve_controller():
    return FileResponse(str(BASE_DIR / "static" / "controller.html"))


@app.get("/tv", response_class=HTMLResponse)
async def serve_tv():
    return FileResponse(str(BASE_DIR / "static" / "tv.html"))


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
