"""ViralCut AI v2.0 - Agente Dark Autônomo.

Pesquisa tendências virais (Google Trends + Google News RSS),
gera roteiro com Gemini, narra com Edge-TTS, sincroniza legendas karaokê .ass,
busca clipes de fundo no Pexels (ou gera fundo cinematográfico via FFmpeg),
monta o Short 9:16 e coloca na fila de aprovação (ou posta automaticamente).
"""
import asyncio
import json
import os
import random
import re
import subprocess
import threading
import urllib.parse
import uuid
from datetime import datetime
from pathlib import Path

import feedparser
import requests

import instagram_uploader
import tiktok_uploader
import youtube_uploader

DEFAULT_CONFIG = {
    "enabled": True,
    "niche": "Curiosidades e Mistérios",
    "voice": "pt-BR-AntonioNeural",
    "schedule_time": "06:00",
    "auto_post": False,
    "privacy": "public",
    "pixabay_api_key": "",
    "pexels_api_key": "",
    "highlight_color": "yellow",
    "videos_per_run": 1,
    "duration_mode": "completo_curto",
    "watermark": True,
    "channel_name": "theDaarkNest",
    "post_youtube": True,
    "post_instagram": False,
    "post_tiktok": False,
    "ig_user_id": "",
    "ig_access_token": "",
    "tiktok_mode": "publish",
}

VOICES = {
    "pt-BR-AntonioNeural": "Antônio (Masculina grave)",
    "pt-BR-FranciscaNeural": "Francisca (Feminina envolvente)",
    "pt-BR-FabioNeural": "Fábio (Masculina narrativa)",
    "pt-BR-ThalitaNeural": "Thalita (Feminina dinâmica)",
}

COLORS = {"yellow": "&H0000FFFF&", "green": "&H0000FF44&", "cyan": "&H00FFFF00&"}

DURATION_SPECS = {
    "completo_curto": {
        "label": "50 a 58 segundos (135 a 165 palavras)",
        "scenes": 5,
    },
    "completo_medio": {
        "label": "1 minuto e 30 segundos a 2 minutos e 30 segundos (240 a 380 palavras)",
        "scenes": 7,
    },
    "completo_longo": {
        "label": "3 a 5 minutos (480 a 750 palavras)",
        "scenes": 10,
    },
}



class DarkAgent:
    def __init__(self, base_dir: Path, gemini_key_fn, gemini_model: str = "gemini-2.5-flash"):
        self.base = base_dir
        self.gemini_key_fn = gemini_key_fn
        self.gemini_model = gemini_model
        self.queue_dir = base_dir / "fila_dark"
        self.tmp_dir = base_dir / "downloads" / "dark_tmp"
        self.music_dir = base_dir / "musicas"
        self.fundos_dir = base_dir / "fundos"
        self.config_file = base_dir / "dark_config.json"
        self.queue_file = self.queue_dir / "queue.json"

        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.music_dir.mkdir(parents=True, exist_ok=True)
        self.fundos_dir.mkdir(parents=True, exist_ok=True)

        self.lock = threading.Lock()
        self.state = {
            "running": False,
            "progress": 0,
            "message": "Agente em espera",
            "last_run": None,
            "last_error": None,
        }
        self.config = self._load_config()
        self.scheduler = None
        self._start_scheduler()

    def _load_config(self) -> dict:
        cfg = dict(DEFAULT_CONFIG)
        env_pixabay = os.getenv("PIXABAY_API_KEY", "").strip()
        if env_pixabay:
            cfg["pixabay_api_key"] = env_pixabay
        env_pexels = os.getenv("PEXELS_API_KEY", "").strip()
        if env_pexels:
            cfg["pexels_api_key"] = env_pexels
        if self.config_file.is_file():
            try:
                saved = json.loads(self.config_file.read_text(encoding="utf-8"))
                cfg.update(saved)
            except Exception:
                pass
        return cfg

    def save_config(self, new_cfg: dict) -> dict:
        allowed = set(DEFAULT_CONFIG.keys())
        for k, v in new_cfg.items():
            if k in allowed:
                self.config[k] = v
        self.config_file.write_text(
            json.dumps(self.config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._reschedule()
        return self.config

    def _load_queue(self) -> list[dict]:
        if not self.queue_file.is_file():
            return []
        try:
            return json.loads(self.queue_file.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save_queue(self, items: list[dict]):
        self.queue_file.write_text(
            json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def list_queue(self) -> list[dict]:
        items = self._load_queue()
        valid = []
        for it in items:
            vpath = self.queue_dir / it.get("filename", "")
            if vpath.is_file():
                valid.append(it)
        if len(valid) != len(items):
            self._save_queue(valid)
        return sorted(valid, key=lambda x: x.get("created_at", ""), reverse=True)

    def delete_item(self, item_id: str) -> bool:
        items = self._load_queue()
        kept = []
        removed = False
        for it in items:
            if it["id"] == item_id:
                removed = True
                vpath = self.queue_dir / it.get("filename", "")
                if vpath.is_file():
                    vpath.unlink(missing_ok=True)
            else:
                kept.append(it)
        self._save_queue(kept)
        return removed

    def approve_and_post(self, item_id: str, platforms: list[str] | None = None) -> dict:
        items = self._load_queue()
        target = next((x for x in items if x["id"] == item_id), None)
        if not target:
            raise FileNotFoundError("Vídeo não encontrado na fila.")
        vpath = self.queue_dir / target["filename"]

        if platforms is None:
            platforms = []
            if self.config.get("post_youtube", True):
                platforms.append("youtube")
            if self.config.get("post_instagram", False):
                platforms.append("instagram")
            if self.config.get("post_tiktok", False):
                platforms.append("tiktok")

        if not platforms:
            raise RuntimeError("Nenhuma rede social marcada para postagem nas configurações do Agente.")

        posted = dict(target.get("posted_platforms", {}))
        errors = {}
        caption = f"{target['title']}\n\n{target['description']}"

        if "youtube" in platforms:
            try:
                res = youtube_uploader.upload_short(
                    base_dir=self.base,
                    video_path=vpath,
                    title=target["title"],
                    description=target["description"],
                    tags=target.get("tags", []),
                    privacy=self.config.get("privacy", "public"),
                )
                posted["youtube"] = res.get("url") or "OK"
                target["youtube_url"] = res.get("url", "")
            except Exception as exc:
                errors["youtube"] = str(exc)

        if "instagram" in platforms:
            try:
                ig_uid = (self.config.get("ig_user_id") or os.getenv("IG_USER_ID", "")).strip()
                ig_tok = (self.config.get("ig_access_token") or os.getenv("IG_ACCESS_TOKEN", "")).strip()
                res = instagram_uploader.upload_reel(
                    video_path=vpath,
                    caption=caption,
                    ig_user_id=ig_uid,
                    access_token=ig_tok,
                )
                posted["instagram"] = res.get("url") or "OK"
            except Exception as exc:
                errors["instagram"] = str(exc)

        if "tiktok" in platforms:
            try:
                res = tiktok_uploader.upload_tiktok(
                    base_dir=self.base,
                    video_path=vpath,
                    caption=caption,
                    mode=self.config.get("tiktok_mode", "publish"),
                )
                posted["tiktok"] = res.get("status", "published")
            except Exception as exc:
                errors["tiktok"] = str(exc)

        target["posted_platforms"] = posted
        target["post_errors"] = errors
        if posted:
            target["status"] = "posted"
            target["posted_at"] = datetime.now().strftime("%d/%m/%Y %H:%M")
        self._save_queue(items)

        if not posted and errors:
            msg = " | ".join(f"{k.upper()}: {v}" for k, v in errors.items())
            raise RuntimeError(msg)
        return target

    def _start_scheduler(self):
        try:
            from apscheduler.schedulers.background import BackgroundScheduler

            self.scheduler = BackgroundScheduler()
            self.scheduler.start()
            self._reschedule()
        except Exception as exc:
            self.state["last_error"] = f"Agendador indisponível: {exc}"

    def _reschedule(self):
        if not self.scheduler:
            return
        try:
            self.scheduler.remove_all_jobs()
            if not self.config.get("enabled", True):
                return
            hh, mm = (self.config.get("schedule_time", "06:00") + ":00").split(":")[:2]
            self.scheduler.add_job(
                self.trigger_run,
                "cron",
                hour=int(hh),
                minute=int(mm),
                id="daily_dark_agent",
                replace_existing=True,
            )
        except Exception as exc:
            self.state["last_error"] = f"Horário inválido: {exc}"

    def _set_state(self, **kw):
        self.state.update(kw)

    def trigger_run(self, custom_topic: str = "") -> dict:
        if self.state["running"]:
            return {"started": False, "message": "O Agente já está produzindo um vídeo."}
        threading.Thread(
            target=self._run_worker, args=(custom_topic,), daemon=True
        ).start()
        return {"started": True, "message": "Agente Dark iniciado."}

    def _run_worker(self, custom_topic: str = ""):
        if not self.lock.acquire(blocking=False):
            return
        try:
            self._set_state(running=True, progress=5, message="Iniciando Agente Dark...", last_error=None)
            count = max(1, min(3, int(self.config.get("videos_per_run", 1))))
            for idx in range(count):
                prefix = f"[{idx+1}/{count}] " if count > 1 else ""
                self._produce_one(custom_topic if idx == 0 else "", prefix)
            self._set_state(
                running=False,
                progress=100,
                message="Concluído! Vídeo pronto na fila.",
                last_run=datetime.now().strftime("%d/%m/%Y %H:%M"),
            )
        except Exception as exc:
            self._set_state(
                running=False,
                progress=0,
                message="Falha na produção",
                last_error=str(exc),
            )
        finally:
            self.lock.release()

    def _produce_one(self, custom_topic: str, prefix: str = ""):
        gemini_key = self.gemini_key_fn()
        if not gemini_key:
            raise RuntimeError("GEMINI_API_KEY não configurada no iniciar.bat.")

        niche = self.config.get("niche", "Curiosidades e Mistérios")
        job_id = uuid.uuid4().hex[:8]

        self._set_state(progress=12, message=f"{prefix}Pesquisando temas virais ({niche})...")
        trends = self.research_trends(niche)

        self._set_state(progress=28, message=f"{prefix}Gemini escolhendo tema e escrevendo roteiro...")
        script_data = self.generate_script(gemini_key, niche, trends, custom_topic)

        self._set_state(progress=48, message=f"{prefix}Gerando narração neural (Edge-TTS)...")
        audio_path = self.tmp_dir / f"{job_id}.mp3"
        voice = self.config.get("voice", "pt-BR-AntonioNeural")
        words, audio_dur = asyncio.run(self.synthesize_voice(script_data["script"], voice, audio_path))
        if audio_dur < 5:
            audio_dur = 25.0

        self._set_state(progress=60, message=f"{prefix}Sincronizando legendas dinâmicas...")
        ass_path = self.tmp_dir / f"{job_id}.ass"
        self.generate_ass(words, audio_dur, ass_path, self.config.get("highlight_color", "yellow"))

        self._set_state(progress=72, message=f"{prefix}Preparando cenas visuais 9:16...")
        bg_video = self.prepare_background(
            job_id, script_data.get("visual_queries", ["dark mystery night"]), audio_dur
        )

        self._set_state(progress=86, message=f"{prefix}Renderizando vídeo Dark 1080x1920...")
        filename = f"dark_{job_id}.mp4"
        out_path = self.queue_dir / filename
        self.render_final(bg_video, audio_path, ass_path, out_path, audio_dur)

        for p in (audio_path, ass_path, bg_video):
            if p and p.exists():
                p.unlink(missing_ok=True)

        item = {
            "id": job_id,
            "filename": filename,
            "title": script_data["title"],
            "description": script_data["description"],
            "tags": script_data.get("tags", ["shorts", "curiosidades", "viral"]),
            "score": int(script_data.get("viral_score", 92)),
            "hook": script_data.get("hook", ""),
            "niche": niche,
            "duration": round(audio_dur, 1),
            "status": "pending",
            "youtube_url": "",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "created_label": datetime.now().strftime("%d/%m %H:%M"),
            "url": f"/api/dark/video/{filename}",
            "download": f"/api/dark/download/{filename}",
        }
        items = self._load_queue()
        items.insert(0, item)
        self._save_queue(items)

        if self.config.get("auto_post"):
            self._set_state(progress=95, message=f"{prefix}Postando automaticamente nas redes marcadas...")
            try:
                self.approve_and_post(job_id)
            except Exception as exc:
                self.state["last_error"] = f"Vídeo salvo na fila, mas falhou ao postar: {exc}"

    def research_trends(self, niche: str) -> list[str]:
        titles: list[str] = []
        headers = {"User-Agent": "Mozilla/5.0 ViralCutAgent/2.0"}

        try:
            r = requests.get(
                "https://trends.google.com/trending/rss?geo=BR", headers=headers, timeout=8
            )
            feed = feedparser.parse(r.text)
            for entry in feed.entries[:8]:
                if entry.get("title"):
                    titles.append(f"[Trends BR] {entry.title}")
        except Exception:
            pass

        try:
            q = urllib.parse.quote(niche)
            url = f"https://news.google.com/rss/search?q={q}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
            r = requests.get(url, headers=headers, timeout=8)
            feed = feedparser.parse(r.text)
            for entry in feed.entries[:8]:
                if entry.get("title"):
                    titles.append(f"[Notícia] {entry.title}")
        except Exception:
            pass

        if not titles:
            titles = [
                f"Fato surpreendente pouco conhecido sobre {niche}",
                f"O segredo psicológico por trás de {niche}",
                f"Mistério real ligado a {niche} que poucos sabem explicar",
            ]
        return titles[:14]

    def generate_script(self, gemini_key: str, niche: str, trends: list[str], custom_topic: str) -> dict:
        from google import genai

        mode = self.config.get("duration_mode", "completo_curto")
        spec = DURATION_SPECS.get(mode, DURATION_SPECS["completo_curto"])
        trend_txt = "\n".join(f"- {t}" for t in trends)
        topic_instruction = (
            f"O usuário pediu especificamente sobre o tema: '{custom_topic}'."
            if custom_topic.strip()
            else f"Escolha o assunto com maior potencial viral combinando o nicho '{niche}' com as tendências atuais abaixo."
        )

        prompt = f"""Você é um roteirista especialista em canais Dark virais no Brasil (YouTube, Reels e TikTok).
{topic_instruction}

TENDÊNCIAS ATUAIS COLETADAS AGORA:
{trend_txt}

REGRAS OBRIGATÓRIAS (ASSUNTO COMPLETO, SEM CORTES):
- Idioma: Português do Brasil natural, fluido, envolvente e cinematográfico.
- Duração falada alvo: {spec["label"]}.
- CONTE O ASSUNTO COMPLETO DO INÍCIO AO FIM: introdução (gancho forte nos primeiros 2 segundos) -> desenvolvimento completo com fatos e detalhes -> clímax/revelação -> conclusão fechada e satisfatória.
- PROIBIDO cortar a história pela metade, PROIBIDO deixar assunto incompleto, PROIBIDO dizer "parte 2" ou "continua no próximo vídeo".
- Termine sempre com uma frase final completa e fechada que incentive comentários.
- Sem marcações de cena, sem emojis, sem asteriscos no campo "script" (apenas o texto limpo que será narrado continuamente).
- Gere {spec["scenes"]} termos em inglês no campo "visual_queries" representando as cenas na ordem da história.
- Responda SOMENTE com um objeto JSON válido neste formato:
{{
  "title": "Título curto e magnético (máx 70 chars)",
  "hook": "Resumo em 1 frase do assunto completo abordado",
  "viral_score": 93,
  "script": "Texto completo limpo para narração do início ao fim sem cortes...",
  "description": "Descrição completa do vídeo com 4 a 6 hashtags virais relevantes",
  "tags": ["curiosidades", "viral", "fatos", "historia"],
  "visual_queries": ["dark mysterious forest night", "clock ticking shadow", "cinematic city night rain"]
}}"""

        client = genai.Client(api_key=gemini_key)
        resp = client.models.generate_content(
            model=self.gemini_model,
            contents=prompt,
            config={"response_mime_type": "application/json"},
        )
        raw = re.sub(r"^```(?:json)?|```$", "", resp.text.strip()).strip()
        data = json.loads(raw)
        data["title"] = str(data.get("title", f"Segredo sobre {niche}"))[:80]
        data["script"] = re.sub(r"[*_#`]+", "", str(data.get("script", ""))).strip()
        data["description"] = str(data.get("description", data["title"]))[:1500]
        data["viral_score"] = max(70, min(99, int(data.get("viral_score", 90))))
        if not data["script"]:
            raise RuntimeError("Gemini retornou roteiro vazio.")
        return data

    async def synthesize_voice(self, text: str, voice: str, out_mp3: Path):
        import edge_tts

        communicate = edge_tts.Communicate(text, voice=voice, rate="+6%")
        words = []
        with open(out_mp3, "wb") as fp:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    fp.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    start = chunk["offset"] / 10_000_000.0
                    dur = chunk["duration"] / 10_000_000.0
                    wtxt = str(chunk.get("text", "")).strip()
                    if wtxt:
                        words.append({"start": start, "end": start + dur, "word": wtxt})

        total_dur = self._probe_duration(out_mp3)
        if not words:
            tokens = text.split()
            step = total_dur / max(1, len(tokens))
            for idx, tok in enumerate(tokens):
                words.append({"start": idx * step, "end": (idx + 1) * step, "word": tok})
        return words, total_dur

    def _probe_duration(self, media_path: Path) -> float:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(media_path),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        try:
            return float(r.stdout.strip())
        except Exception:
            return 30.0

    def generate_ass(self, words: list[dict], duration: float, path: Path, color: str = "yellow"):
        hl = COLORS.get(color, COLORS["yellow"])
        header = (
            "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 2\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
            "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
            "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Arial,88,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,"
            "-1,0,0,0,100,100,0,0,1,7,0,5,70,70,120,1\n\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )

        def fmt_t(t):
            t = max(t, 0.0)
            return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"

        lines = []
        chunk_size = 3
        for i in range(0, len(words), chunk_size):
            chunk = words[i : i + chunk_size]
            for j, cur in enumerate(chunk):
                start = max(cur["start"], 0.0)
                nxt = chunk[j + 1]["start"] if j + 1 < len(chunk) else cur["end"]
                end = min(max(nxt, start + 0.06), duration)
                parts = []
                for k, wd in enumerate(chunk):
                    txt = wd["word"].upper().replace("{", "").replace("}", "")
                    if k == j:
                        parts.append("{\\c" + hl + "\\fscx112\\fscy112}" + txt + "{\\r}")
                    else:
                        parts.append(txt)
                lines.append(
                    f"Dialogue: 0,{fmt_t(start)},{fmt_t(end)},Default,,0,0,0,," + " ".join(parts)
                )
        path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")

    def prepare_background(self, job_id: str, queries: list[str], duration: float) -> Path:
        out_bg = self.tmp_dir / f"{job_id}_bg.mp4"
        pixabay_key = (self.config.get("pixabay_api_key") or os.getenv("PIXABAY_API_KEY", "")).strip()
        pexels_key = (self.config.get("pexels_api_key") or os.getenv("PEXELS_API_KEY", "")).strip()

        clips: list[Path] = []
        is_local = False

        if pixabay_key:
            clips = self._fetch_pixabay_clips(job_id, queries, pixabay_key)
        if not clips and pexels_key:
            clips = self._fetch_pexels_clips(job_id, queries, pexels_key)
        if not clips:
            local_mp4s = list(self.fundos_dir.glob("*.mp4"))
            if local_mp4s:
                random.shuffle(local_mp4s)
                clips = local_mp4s[:8]
                is_local = True

        if clips:
            concat_txt = self.tmp_dir / f"{job_id}_concat.txt"
            norm_clips = []
            for idx, cp in enumerate(clips):
                norm = self.tmp_dir / f"{job_id}_norm_{idx}.mp4"
                cmd = [
                    "ffmpeg", "-y", "-i", str(cp), "-t", "14",
                    "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,eq=brightness=-0.12:contrast=1.15:saturation=0.85",
                    "-an", "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                    str(norm),
                ]
                if subprocess.run(cmd, capture_output=True).returncode == 0:
                    norm_clips.append(norm)
                if not is_local:
                    cp.unlink(missing_ok=True)
            if norm_clips:
                clip_durs = [max(2.0, self._probe_duration(c)) for c in norm_clips]
                lines = []
                acc_dur = 0.0
                idx_loop = 0
                target_bg_dur = duration + 2.0
                while acc_dur < target_bg_dur:
                    c = norm_clips[idx_loop % len(norm_clips)]
                    lines.append(f"file '{c.name}'")
                    acc_dur += clip_durs[idx_loop % len(norm_clips)]
                    idx_loop += 1
                concat_txt.write_text("\n".join(lines), encoding="utf-8")
                subprocess.run(
                    [
                        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_txt.name,
                        "-t", f"{target_bg_dur:.2f}", "-c", "copy", str(out_bg),
                    ],
                    cwd=str(self.tmp_dir),
                    capture_output=True,
                )
                concat_txt.unlink(missing_ok=True)
                for nc in norm_clips:
                    nc.unlink(missing_ok=True)
                if out_bg.is_file() and out_bg.stat().st_size > 10000:
                    return out_bg

        # Fallback cinematográfico Dark 100% offline via FFmpeg
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"gradients=s=1080x1920:c0=0x07060d:c1=0x1e1345:c2=0x0a2538:speed=0.4:duration={duration + 0.5:.2f}",
            "-vf", "noise=alls=8:allf=t+u,vignette=PI/3.5",
            "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            str(out_bg),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-f", "lavfi",
                    "-i", f"color=c=0x0c0a1d:s=1080x1920:d={duration + 0.5:.2f}",
                    "-vf", "noise=alls=10:allf=t+u,vignette=PI/3.5",
                    "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                    str(out_bg),
                ],
                check=True,
                capture_output=True,
            )
        return out_bg

    def _fetch_pixabay_clips(self, job_id: str, queries: list[str], api_key: str) -> list[Path]:
        downloaded = []
        for idx, q in enumerate(queries[:8]):
            try:
                r = requests.get(
                    "https://pixabay.com/api/videos/",
                    params={"key": api_key, "q": q[:90], "per_page": 5, "safesearch": "true"},
                    timeout=12,
                )
                if r.status_code != 200:
                    continue
                hits = r.json().get("hits", [])
                if not hits:
                    continue
                chosen = random.choice(hits)
                vids = chosen.get("videos", {})
                # Prefere medium (720p/1080p) pela velocidade e qualidade
                vinfo = vids.get("medium") or vids.get("large") or vids.get("small")
                if not vinfo or not vinfo.get("url"):
                    continue
                vr = requests.get(vinfo["url"], timeout=30)
                if vr.status_code == 200:
                    p = self.tmp_dir / f"{job_id}_pb_{idx}.mp4"
                    p.write_bytes(vr.content)
                    downloaded.append(p)
            except Exception:
                continue
        return downloaded

    def _fetch_pexels_clips(self, job_id: str, queries: list[str], api_key: str) -> list[Path]:
        headers = {"Authorization": api_key}
        downloaded = []
        for idx, q in enumerate(queries[:8]):
            try:
                r = requests.get(
                    "https://api.pexels.com/videos/search",
                    headers=headers,
                    params={"query": q, "orientation": "portrait", "per_page": 3},
                    timeout=10,
                )
                if r.status_code != 200:
                    continue
                vids = r.json().get("videos", [])
                if not vids:
                    continue
                chosen = random.choice(vids)
                files = chosen.get("video_files", [])
                best = sorted(files, key=lambda x: abs((x.get("width") or 0) - 720))[0]
                vr = requests.get(best["link"], timeout=25)
                if vr.status_code == 200:
                    p = self.tmp_dir / f"{job_id}_px_{idx}.mp4"
                    p.write_bytes(vr.content)
                    downloaded.append(p)
            except Exception:
                continue
        return downloaded

    def render_final(self, bg_video: Path, audio_path: Path, ass_path: Path, out_path: Path, duration: float):
        musics = list(self.music_dir.glob("*.mp3"))
        wm_anim = self.base / "watermark_anim.apng"
        wm_static = self.base / "watermark.png"
        use_wm = bool(self.config.get("watermark", True)) and (wm_anim.is_file() or wm_static.is_file())
        is_anim_wm = use_wm and wm_anim.is_file()

        total_dur = duration + 0.9
        fade_start = max(0.0, total_dur - 0.6)

        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", str(bg_video),
            "-i", str(audio_path),
        ]
        next_idx = 2
        bgm_idx = None
        wm_idx = None

        if musics:
            bgm = random.choice(musics)
            cmd += ["-stream_loop", "-1", "-i", str(bgm)]
            bgm_idx = next_idx
            next_idx += 1

        if use_wm:
            if is_anim_wm:
                cmd += ["-f", "apng", "-ignore_loop", "0", "-i", str(wm_anim)]
            else:
                cmd += ["-i", str(wm_static)]
            wm_idx = next_idx
            next_idx += 1

        # Marca d'água no canto INFERIOR direito (W-w-30:H-h-36)
        if wm_idx is not None:
            if is_anim_wm:
                v_chain = (
                    f"[0:v]ass={ass_path.name}[vsub];"
                    f"[{wm_idx}:v]scale=210:-1[wm];"
                    f"[vsub][wm]overlay=W-w-30:H-h-36:shortest=1,fade=t=out:st={fade_start:.2f}:d=0.6[vout]"
                )
            else:
                v_chain = (
                    f"[0:v]ass={ass_path.name}[vsub];"
                    f"[{wm_idx}:v]scale=210:-1[wm];"
                    f"[vsub][wm]overlay=W-w-30:'H-h-36+6*sin(2*PI*t/2.5)',fade=t=out:st={fade_start:.2f}:d=0.6[vout]"
                )
        else:
            v_chain = f"[0:v]ass={ass_path.name},fade=t=out:st={fade_start:.2f}:d=0.6[vout]"

        if bgm_idx is not None:
            a_chain = (
                f"[1:a]apad=pad_dur=0.9,volume=1.0[v];"
                f"[{bgm_idx}:a]volume=0.14,afade=t=out:st={fade_start:.2f}:d=0.6[m];"
                f"[v][m]amix=inputs=2:duration=first[aout]"
            )
        else:
            a_chain = "[1:a]apad=pad_dur=0.9[aout]"

        cmd += [
            "-t", f"{total_dur:.2f}",
            "-filter_complex", f"{v_chain};{a_chain}",
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
            str(out_path),
        ]

        r = subprocess.run(cmd, cwd=str(ass_path.parent), capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("FFmpeg falhou ao renderizar vídeo Dark: " + r.stderr[-400:])
