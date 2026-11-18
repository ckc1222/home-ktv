import asyncio
import json
import os
import re
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
CACHE_DIR.mkdir(exist_ok=True)

# 將獨立版 yt-dlp 與 deno 加入環境變數 PATH
os.environ["PATH"] = f"{BIN_DIR}:{os.environ.get('PATH', '')}"

app = FastAPI(title="Home KTV Party Server")


def get_local_ip() -> str:
    """取得 MacBook Air 在區域網路 (Wi-Fi / 熱點) 的 IP 位址"""
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


class KTVRoomState:
    def __init__(self):
        self.queue: List[Dict] = []
        self.current_song: Optional[Dict] = None
        self.is_playing: bool = True
        self.vocal_cut: bool = False  # False = 原唱, True = 伴唱(消人聲)
        self.pitch_semitones: int = 0  # -6 ~ +6 半音
        self.volume: int = 85          # 伴奏音量 (0 ~ 100)
        self.mic_enabled: bool = False
        self.mic_volume: int = 100     # 麥克風人聲音量 (0 ~ 200)
        self.reverb_level: int = 45    # KTV 迴音強度 (0 ~ 100)
        self.anti_howl: bool = False   # 防喇叭嘯叫模式 (筆電外放時可開)

    def to_dict(self):
        cur = None
        if self.current_song:
            vid = self.current_song.get("video_id", "")
            cur = {
                **self.current_song,
                "cached": is_video_cached(vid),
            }
        q_list = [
            {**s, "cached": is_video_cached(s.get("video_id", ""))}
            for s in self.queue
        ]
        return {
            "type": "state_update",
            "current_song": cur,
            "queue": q_list,
            "is_playing": self.is_playing,
            "vocal_cut": self.vocal_cut,
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
    """使用最新獨立版 yt-dlp + deno 在背景下載高品質 MP4 供消人聲與升降 Key 使用"""
    if not re.match(r"^[A-Za-z0-9_-]{6,20}$", video_id):
        return False
    target = CACHE_DIR / f"{video_id}.mp4"
    if is_video_cached(video_id):
        return True

    temp_target = CACHE_DIR / f"{video_id}.temp.mp4"
    yt_dlp_bin = str(BIN_DIR / "yt-dlp") if (BIN_DIR / "yt-dlp").exists() else "yt-dlp"
    cmd = [
        yt_dlp_bin,
        "--no-playlist",
        "--no-Sleep" if False else "--sleep-interval", "0",
        "-f",
        "18/best[ext=mp4][acodec!=none][vcodec!=none]/best[ext=mp4]",
        "-o",
        str(temp_target),
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    try:
        subprocess.run(cmd, check=True, timeout=120)
        if temp_target.exists() and temp_target.stat().st_size > 100_000:
            temp_target.rename(target)
            return True
    except Exception as e:
        print(f"[yt-dlp cache] Failed for {video_id}: {e}")
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
    """提供本地快取的無廣告 MP4 檔案（支援完整 Range 拖曳、WebAudio 即時消人聲與升降 Key）"""
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
                    room.pitch_semitones = 0
                else:
                    if priority:
                        room.queue.insert(0, song)
                    else:
                        room.queue.append(song)

                # 立即在背景預載 MP4（支援無廣告 + 消人聲 + 升降Key）
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

            elif action == "toggle_vocal":
                room.vocal_cut = not room.vocal_cut
                await broadcast_state()
                await broadcast(
                    {
                        "type": "toast",
                        "text": (
                            "🎤 已切換為：伴唱（消人聲模式）"
                            if room.vocal_cut
                            else "🎵 已切換為：原唱導唱模式"
                        ),
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
