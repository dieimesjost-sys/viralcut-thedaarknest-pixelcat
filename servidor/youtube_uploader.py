"""Módulo de upload automático para YouTube Shorts via YouTube Data API v3."""
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def get_paths(base_dir: Path):
    return base_dir / "client_secrets.json", base_dir / "youtube_token.json"


def is_configured(base_dir: Path) -> bool:
    secrets, token = get_paths(base_dir)
    return secrets.is_file() and token.is_file()


def has_secrets(base_dir: Path) -> bool:
    secrets, _ = get_paths(base_dir)
    return secrets.is_file()


def authorize_interactive(base_dir: Path) -> str:
    """Abre o navegador no Windows uma única vez para autorizar a conta do YouTube."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    secrets, token = get_paths(base_dir)
    if not secrets.is_file():
        raise FileNotFoundError(
            "Arquivo client_secrets.json não encontrado na pasta servidor/. "
            "Siga o passo 4 do MANUAL_INSTALACAO.md para baixá-lo do Google Cloud."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    token.write_text(creds.to_json(), encoding="utf-8")
    return "YouTube conectado com sucesso! Token salvo em youtube_token.json."


def _get_service(base_dir: Path):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    _, token = get_paths(base_dir)
    if not token.is_file():
        raise RuntimeError(
            "YouTube não autorizado ainda. Execute conectar_youtube.bat no PC primeiro."
        )
    creds = Credentials.from_authorized_user_file(str(token), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds)


def upload_short(
    base_dir: Path,
    video_path: Path,
    title: str,
    description: str,
    tags: list[str] | None = None,
    privacy: str = "public",
) -> dict:
    """Faz upload do vídeo vertical 9:16 como YouTube Short."""
    from googleapiclient.http import MediaFileUpload

    if not video_path.is_file():
        raise FileNotFoundError(f"Vídeo não encontrado: {video_path}")

    service = _get_service(base_dir)
    clean_title = title.strip()[:95]
    if "#shorts" not in clean_title.lower() and len(clean_title) <= 88:
        clean_title = f"{clean_title} #Shorts"

    clean_desc = description.strip()
    if "#shorts" not in clean_desc.lower():
        clean_desc += "\n\n#Shorts #Curiosidades #Viral"

    body = {
        "snippet": {
            "title": clean_title,
            "description": clean_desc[:4900],
            "tags": (tags or ["shorts", "viral", "curiosidades"])[:15],
            "categoryId": "24",
            "defaultLanguage": "pt-BR",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        _, response = request.next_chunk()

    vid = response.get("id", "")
    return {
        "video_id": vid,
        "url": f"https://youtube.com/shorts/{vid}" if vid else "",
        "privacy": privacy,
    }


if __name__ == "__main__":
    print(authorize_interactive(Path(__file__).parent.resolve()))
