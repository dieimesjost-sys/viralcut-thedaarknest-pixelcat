"""Upload automático para Instagram Reels via Instagram Graph API."""
import os
import time
from pathlib import Path

import requests

GRAPH_BASE = "https://graph.facebook.com/v21.0"


def is_configured(cfg: dict) -> bool:
    uid = (cfg.get("ig_user_id") or os.getenv("IG_USER_ID", "")).strip()
    tok = (cfg.get("ig_access_token") or os.getenv("IG_ACCESS_TOKEN", "")).strip()
    return bool(uid and tok)


def _upload_temp_public_url(video_path: Path) -> str:
    """Envia o MP4 temporariamente (expira em 60 min) para gerar URL HTTPS pública exigida pelo Instagram."""
    with open(video_path, "rb") as fp:
        r = requests.post(
            "https://tmpfiles.org/api/v1/upload",
            files={"file": (video_path.name, fp, "video/mp4")},
            timeout=90,
        )
    r.raise_for_status()
    data = r.json()
    raw_url = data.get("data", {}).get("url", "")
    if not raw_url:
        raise RuntimeError("Falha ao gerar link temporário público para o Instagram.")
    # Converte https://tmpfiles.org/12345/video.mp4 -> https://tmpfiles.org/dl/12345/video.mp4
    return raw_url.replace("tmpfiles.org/", "tmpfiles.org/dl/", 1)


def upload_reel(
    video_path: Path,
    caption: str,
    ig_user_id: str,
    access_token: str,
    public_video_url: str = "",
) -> dict:
    """Publica um vídeo 9:16 como Instagram Reel."""
    if not video_path.is_file():
        raise FileNotFoundError(f"Vídeo não encontrado: {video_path}")
    if not ig_user_id or not access_token:
        raise RuntimeError("Configure o Instagram User ID e Access Token nas configurações do Agente.")

    video_url = public_video_url.strip() or _upload_temp_public_url(video_path)

    # 1. Criar container do Reel
    create_resp = requests.post(
        f"{GRAPH_BASE}/{ig_user_id}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption[:2150],
            "share_to_feed": "true",
            "access_token": access_token,
        },
        timeout=45,
    )
    create_data = create_resp.json()
    if "id" not in create_data:
        err = create_data.get("error", {}).get("message", str(create_data))
        raise RuntimeError(f"Instagram recusou o container do Reel: {err}")

    creation_id = create_data["id"]

    # 2. Aguardar processamento do vídeo nos servidores da Meta
    for _ in range(30):
        time.sleep(3)
        st = requests.get(
            f"{GRAPH_BASE}/{creation_id}",
            params={"fields": "status_code,status", "access_token": access_token},
            timeout=20,
        ).json()
        code = st.get("status_code", "")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram falhou ao processar o vídeo: {st}")
    else:
        raise RuntimeError("Tempo limite aguardando o Instagram processar o Reel.")

    # 3. Publicar o Reel
    pub_resp = requests.post(
        f"{GRAPH_BASE}/{ig_user_id}/media_publish",
        data={"creation_id": creation_id, "access_token": access_token},
        timeout=45,
    )
    pub_data = pub_resp.json()
    if "id" not in pub_data:
        err = pub_data.get("error", {}).get("message", str(pub_data))
        raise RuntimeError(f"Falha ao publicar Reel no Instagram: {err}")

    media_id = pub_data["id"]
    return {
        "media_id": media_id,
        "url": f"https://www.instagram.com/reel/",
        "status": "published",
    }
