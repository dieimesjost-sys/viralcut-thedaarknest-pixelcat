"""ViralCut AI v2.0 - Servidor Local (Cortes Virais + Agente Dark Autônomo + YouTube Shorts)."""
import base64
import io
import json
import os
import re
import shutil
import subprocess
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import instagram_uploader
import thumbs
import tiktok_uploader
import youtube_uploader
from agente_dark import VOICES, DarkAgent

BASE = Path(__file__).parent.resolve()
DOWNLOADS = BASE / "downloads"
CLIPS = BASE / "clips"
DOWNLOADS.mkdir(exist_ok=True)
CLIPS.mkdir(exist_ok=True)

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")  # use "base" em PCs mais fracos
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
KEEP_DOWNLOADS = os.getenv("KEEP_DOWNLOADS", "0") == "1"

SIZES = {"9:16": (1080, 1920), "1:1": (1080, 1080), "16:9": (1920, 1080)}
MARGIN_V = {"9:16": 420, "1:1": 90, "16:9": 60}
FONT_SIZE = {"9:16": 84, "1:1": 72, "16:9": 64}
COLORS = {"yellow": "&H0000FFFF&", "green": "&H0000FF44&"}
CHUNK_SIZE = 3

app = FastAPI(title="ViralCut AI v2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/clips", StaticFiles(directory=CLIPS), name="clips")

JOBS: dict = {}
LOCK = threading.Lock()
_whisper = None

AGENT = DarkAgent(BASE, lambda: GEMINI_KEY, GEMINI_MODEL)


class AnalyzeRequest(BaseModel):
    url: str
    format: str = "9:16"
    subtitles: bool = True
    num_clips: int = 5
    min_seconds: int = 20
    max_seconds: int = 60
    highlight_color: str = "yellow"


class DarkConfigRequest(BaseModel):
    enabled: bool = True
    niche: str = "Curiosidades e Mistérios"
    voice: str = "pt-BR-AntonioNeural"
    schedule_time: str = "06:00"
    auto_post: bool = False
    privacy: str = "public"
    pixabay_api_key: str = ""
    pexels_api_key: str = ""
    highlight_color: str = "yellow"
    videos_per_run: int = 1
    duration_mode: str = "completo_curto"
    post_youtube: bool = True
    post_instagram: bool = False
    post_tiktok: bool = False
    ig_user_id: str = ""
    ig_access_token: str = ""
    tiktok_mode: str = "publish"


class DarkRunRequest(BaseModel):
    topic: str = ""


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": "2.3",
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "gemini": bool(GEMINI_KEY),
        "whisper_model": WHISPER_MODEL,
        "youtube_connected": youtube_uploader.is_configured(BASE),
        "instagram_connected": instagram_uploader.is_configured(AGENT.config),
        "tiktok_connected": tiktok_uploader.is_configured(BASE),
        "pixabay": bool(AGENT.config.get("pixabay_api_key")),
        "pexels": bool(AGENT.config.get("pexels_api_key")),
        "agent_running": AGENT.state["running"],
    }


# ============================================================ ROTAS AGENTE DARK

@app.get("/api/dark/config")
def dark_get_config():
    return {
        "config": AGENT.config,
        "voices": VOICES,
        "youtube_connected": youtube_uploader.is_configured(BASE),
        "instagram_connected": instagram_uploader.is_configured(AGENT.config),
        "tiktok_connected": tiktok_uploader.is_configured(BASE),
        "youtube_has_secrets": youtube_uploader.has_secrets(BASE),
    }


@app.post("/api/dark/config")
def dark_save_config(req: DarkConfigRequest):
    saved = AGENT.save_config(req.model_dump())
    return {"ok": True, "config": saved}


@app.post("/api/dark/run")
def dark_run(req: DarkRunRequest):
    if not GEMINI_KEY:
        raise HTTPException(500, "GEMINI_API_KEY não configurada no iniciar.bat.")
    if not shutil.which("ffmpeg"):
        raise HTTPException(500, "FFmpeg não encontrado no PC.")
    return AGENT.trigger_run(req.topic)


@app.get("/api/dark/status")
def dark_status():
    return AGENT.state


@app.get("/api/dark/queue")
def dark_queue():
    return {
        "items": AGENT.list_queue(),
        "youtube_connected": youtube_uploader.is_configured(BASE),
        "instagram_connected": instagram_uploader.is_configured(AGENT.config),
        "tiktok_connected": tiktok_uploader.is_configured(BASE),
    }


@app.post("/api/dark/approve/{item_id}")
def dark_approve(item_id: str):
    try:
        updated = AGENT.approve_and_post(item_id)
        return {"ok": True, "item": updated}
    except Exception as exc:
        raise HTTPException(400, str(exc))


@app.delete("/api/dark/queue/{item_id}")
def dark_delete(item_id: str):
    ok = AGENT.delete_item(item_id)
    if not ok:
        raise HTTPException(404, "Item não encontrado.")
    return {"ok": True}


@app.get("/api/dark/video/{name}")
def dark_video(name: str):
    path = AGENT.queue_dir / Path(name).name
    if not path.is_file():
        raise HTTPException(404, "Vídeo não encontrado.")
    return FileResponse(path, media_type="video/mp4")


@app.get("/api/dark/download/{name}")
def dark_download(name: str):
    path = AGENT.queue_dir / Path(name).name
    if not path.is_file():
        raise HTTPException(404, "Arquivo não encontrado.")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


# ============================================================ ROTAS THUMBNAILS

THUMBS_DIR = AGENT.queue_dir / "thumbs"
THUMBS_DIR.mkdir(exist_ok=True)
LOGO = BASE / "logo_canal.png"


class LogoReq(BaseModel):
    data: str


class ThumbReq(BaseModel):
    item_id: str
    title: str = ""
    fmt: str = "9:16"
    position: float = 0.35


@app.get("/api/thumb/info")
def thumb_info():
    return {"has_logo": LOGO.is_file()}


@app.get("/api/thumb/logo")
def thumb_logo():
    if not LOGO.is_file():
        raise HTTPException(404, "Logo não enviada.")
    return FileResponse(LOGO, media_type="image/png")


@app.post("/api/thumb/logo")
def thumb_set_logo(req: LogoReq):
    from PIL import Image
    try:
        raw = base64.b64decode(req.data.split(",", 1)[-1])
        img = Image.open(io.BytesIO(raw)).convert("RGBA")
        img.thumbnail((800, 800))
        img.save(LOGO, "PNG")
    except Exception as exc:
        raise HTTPException(400, f"Imagem inválida: {exc}")
    return {"ok": True}


@app.post("/api/thumb/generate")
def thumb_generate(req: ThumbReq):
    item = next((x for x in AGENT.list_queue() if x["id"] == req.item_id), None)
    if not item:
        raise HTTPException(404, "Vídeo não encontrado na fila.")
    fmt = req.fmt if req.fmt in thumbs.SIZES else "9:16"
    name = f"thumb_{item['id']}_{fmt.replace(':', 'x')}.jpg"
    try:
        thumbs.make_thumbnail(AGENT.queue_dir / item["filename"], req.title.strip() or item["title"],
                              LOGO if LOGO.is_file() else None, THUMBS_DIR / name, fmt, req.position)
    except Exception as exc:
        raise HTTPException(500, f"Falha ao gerar thumbnail: {exc}")
    return {"ok": True, "url": f"/api/thumb/file/{name}", "download": f"/api/thumb/download/{name}",
            "has_logo": LOGO.is_file()}


@app.get("/api/thumb/file/{name}")
def thumb_file(name: str):
    path = THUMBS_DIR / Path(name).name
    if not path.is_file():
        raise HTTPException(404, "Thumbnail não encontrada.")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/thumb/download/{name}")
def thumb_download(name: str):
    path = THUMBS_DIR / Path(name).name
    if not path.is_file():
        raise HTTPException(404, "Thumbnail não encontrada.")
    return FileResponse(path, media_type="image/jpeg", filename=path.name)


# ============================================================ ROTAS CORTES VIRAIS

@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    if not re.match(r"^https?://", req.url.strip()):
        raise HTTPException(400, "Link inválido. Use um endereço http(s).")
    if req.format not in SIZES:
        raise HTTPException(400, "Formato inválido. Use 9:16, 1:1 ou 16:9.")
    if not GEMINI_KEY:
        raise HTTPException(500, "GEMINI_API_KEY não configurada no iniciar.bat.")
    if not shutil.which("ffmpeg"):
        raise HTTPException(500, "FFmpeg não encontrado. Reabra o terminal após instalar.")
    job_id = uuid.uuid4().hex[:10]
    JOBS[job_id] = {"id": job_id, "status": "queued", "progress": 0,
                    "message": "Na fila", "clips": [], "error": None}
    threading.Thread(target=_run_job, args=(job_id, req), daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "Tarefa não encontrada.")
    return JOBS[job_id]


@app.get("/api/download/{name}")
def download(name: str):
    path = CLIPS / Path(name).name
    if not path.is_file():
        raise HTTPException(404, "Arquivo não encontrado.")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


# ----------------------------------------------------------------- pipeline

def _update(job_id, **kw):
    JOBS[job_id].update(kw)


def _run_job(job_id, req):
    with LOCK:
        try:
            _pipeline(job_id, req)
        except Exception as exc:  # noqa: BLE001
            _update(job_id, status="error", error=str(exc), message="Falha no processamento")


def _pipeline(job_id, req):
    _update(job_id, status="running", progress=5, message="Baixando vídeo...")
    video = download_video(req.url, job_id)
    try:
        _update(job_id, progress=25, message="Transcrevendo áudio (pode demorar)...")
        segments, words, duration = transcribe(video)
        if not segments:
            raise RuntimeError("Não foi possível detectar fala neste vídeo.")

        _update(job_id, progress=55, message="IA procurando os melhores trechos...")
        picks = find_clips(segments, duration, req)
        if not picks:
            raise RuntimeError("A IA não encontrou trechos adequados.")

        clips = []
        for i, p in enumerate(picks, 1):
            _update(job_id, progress=60 + int(38 * (i - 1) / len(picks)),
                    message=f"Renderizando corte {i} de {len(picks)}...")
            name = f"{job_id}_{i}.mp4"
            ass = None
            if req.subtitles:
                ass = DOWNLOADS / f"{job_id}_{i}.ass"
                generate_reels_subtitles(words, p["start"], p["end"], req.format, ass,
                                         req.highlight_color)
            cut_clip(video, p["start"], p["end"], req.format, ass, CLIPS / name)
            if ass and ass.exists():
                ass.unlink()
            clips.append({**p, "index": i, "duration": round(p["end"] - p["start"], 1),
                          "video_duration": round(duration, 1),
                          "url": f"/clips/{name}", "download": f"/api/download/{name}"})
        _update(job_id, status="done", progress=100, message="Concluído", clips=clips)
    finally:
        if not KEEP_DOWNLOADS and video.exists():
            video.unlink()


def download_video(url, job_id):
    import yt_dlp

    opts = {
        "format": "bv*[height<=1080]+ba/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "outtmpl": str(DOWNLOADS / f"{job_id}.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url.strip()])
    files = [f for f in DOWNLOADS.glob(f"{job_id}.*") if f.suffix not in (".part", ".ytdl")]
    if not files:
        raise RuntimeError("Falha ao baixar o vídeo. Atualize: pip install -U yt-dlp")
    return files[0]


def transcribe(video):
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        _whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    seg_iter, info = _whisper.transcribe(str(video), word_timestamps=True, vad_filter=True)
    segments, words = [], []
    for s in seg_iter:
        segments.append({"start": s.start, "end": s.end, "text": s.text.strip()})
        for w in s.words or []:
            if w.word.strip():
                words.append({"start": w.start, "end": w.end, "word": w.word.strip()})
    return segments, words, info.duration


def find_clips(segments, duration, req):
    from google import genai

    transcript = "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in segments)
    prompt = f"""Você é editor de vídeos virais para TikTok, Reels e Shorts.
Abaixo está a transcrição com tempos em segundos. Escolha até {req.num_clips} trechos com
maior potencial de retenção (gancho forte nos primeiros 3 segundos, emoção, surpresa,
conclusão satisfatória).

Regras:
- Cada trecho dura entre {req.min_seconds} e {req.max_seconds} segundos.
- Comece no início de uma frase e termine no fim de uma frase.
- Trechos não podem se sobrepor.
- Responda SOMENTE com um array JSON de objetos:
  {{"start": número, "end": número, "title": "título curto e chamativo",
    "score": inteiro de 0 a 100, "reason": "por que viraliza, em uma frase"}}

TRANSCRIÇÃO:
{transcript}"""
    client = genai.Client(api_key=GEMINI_KEY)
    resp = client.models.generate_content(
        model=GEMINI_MODEL, contents=prompt,
        config={"response_mime_type": "application/json"})
    text = re.sub(r"^```(?:json)?|```$", "", resp.text.strip()).strip()
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("clips", [])

    picks = []
    for c in data:
        try:
            start = max(0.0, float(c["start"]))
            end = min(float(duration), float(c["end"]))
        except (KeyError, TypeError, ValueError):
            continue
        if end - start < 5:
            continue
        end = min(end, start + req.max_seconds)
        picks.append({"start": round(start, 2), "end": round(end, 2),
                      "title": str(c.get("title", "Corte"))[:80],
                      "score": max(0, min(100, int(c.get("score", 50)))),
                      "reason": str(c.get("reason", ""))[:200]})
    picks.sort(key=lambda x: x["score"], reverse=True)
    return picks[: req.num_clips]


def _ass_time(t):
    t = max(t, 0.0)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def generate_reels_subtitles(words, clip_start, clip_end, fmt, path,
                             highlight_color="yellow", chunk_size=CHUNK_SIZE):
    w, h = SIZES[fmt]
    hl = COLORS.get(highlight_color, COLORS["yellow"])
    header = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {w}\nPlayResY: {h}\nWrapStyle: 2\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,Arial,{FONT_SIZE[fmt]},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,"
        f"-1,0,0,0,100,100,0,0,1,6,0,2,60,60,{MARGIN_V[fmt]},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    ws = [x for x in words if x["end"] > clip_start and x["start"] < clip_end]
    length = clip_end - clip_start
    lines = []
    for i in range(0, len(ws), chunk_size):
        chunk = ws[i:i + chunk_size]
        for j, cur in enumerate(chunk):
            start = max(cur["start"] - clip_start, 0.0)
            nxt = chunk[j + 1]["start"] if j + 1 < len(chunk) else cur["end"]
            end = min(nxt - clip_start, length)
            if end <= start:
                end = start + 0.05
            parts = []
            for k, wd in enumerate(chunk):
                txt = wd["word"].upper().replace("{", "").replace("}", "")
                if k == j:
                    parts.append("{\\c" + hl + "\\fscx110\\fscy110}" + txt + "{\\r}")
                else:
                    parts.append(txt)
            lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,"
                         + " ".join(parts))
    path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")


def cut_clip(video, start, end, fmt, ass_path, out):
    w, h = SIZES[fmt]
    wm_anim = BASE / "watermark_anim.apng"
    wm_static = BASE / "watermark.png"
    use_wm = wm_anim.is_file() or wm_static.is_file()
    is_anim = use_wm and wm_anim.is_file()

    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
    if ass_path:
        vf += f",ass={ass_path.name}"

    if use_wm:
        wm_w = 210 if fmt == "9:16" else 170
        if is_anim:
            cmd = [
                "ffmpeg", "-y", "-ss", f"{start:.2f}", "-i", str(video),
                "-f", "apng", "-ignore_loop", "0", "-i", str(wm_anim),
                "-t", f"{end - start:.2f}",
                "-filter_complex", f"[0:v]{vf}[vsub];[1:v]scale={wm_w}:-1[wm];[vsub][wm]overlay=W-w-30:H-h-36:shortest=1[vout]",
                "-map", "[vout]", "-map", "0:a?",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart", str(out),
            ]
        else:
            cmd = [
                "ffmpeg", "-y", "-ss", f"{start:.2f}", "-i", str(video),
                "-i", str(wm_static),
                "-t", f"{end - start:.2f}",
                "-filter_complex", f"[0:v]{vf}[vsub];[1:v]scale={wm_w}:-1[wm];[vsub][wm]overlay=W-w-30:'H-h-36+6*sin(2*PI*t/2.5)'[vout]",
                "-map", "[vout]", "-map", "0:a?",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart", str(out),
            ]
    else:
        cmd = [
            "ffmpeg", "-y", "-ss", f"{start:.2f}", "-i", str(video), "-t", f"{end - start:.2f}",
            "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart", str(out),
        ]
    r = subprocess.run(cmd, cwd=str(ass_path.parent) if ass_path else None,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("FFmpeg falhou: " + r.stderr[-400:])
