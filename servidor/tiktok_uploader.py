"""Upload automático no TikTok Studio (tiktok.com/tiktokstudio/upload) via Playwright."""
import time
from pathlib import Path

STUDIO_URL = "https://www.tiktok.com/tiktokstudio/upload"


def profile_dir(base_dir: Path) -> Path:
    return base_dir / "tiktok_profile"


def is_configured(base_dir: Path) -> bool:
    p = profile_dir(base_dir)
    return p.is_dir() and any(p.iterdir())


def authorize_interactive(base_dir: Path) -> str:
    """Abre o TikTok Studio no Chromium para você fazer login uma única vez e salvar a sessão."""
    from playwright.sync_api import sync_playwright

    pdir = profile_dir(base_dir)
    pdir.mkdir(parents=True, exist_ok=True)
    print("Abrindo TikTok Studio... Faça login na sua conta e aguarde a tela de upload aparecer.")
    print("Quando estiver logado, FECHE a janela do navegador para salvar a sessão.")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(pdir),
            headless=False,
            viewport={"width": 1280, "height": 820},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(STUDIO_URL, wait_until="domcontentloaded", timeout=60000)
        # Aguarda o usuário fechar a janela após concluir o login
        try:
            page.wait_for_event("close", timeout=0)
        except Exception:
            pass
        ctx.close()
    return "Sessão do TikTok Studio salva com sucesso em tiktok_profile/!"


def upload_tiktok(
    base_dir: Path,
    video_path: Path,
    caption: str,
    mode: str = "publish",
    headless: bool = False,
) -> dict:
    """Envia o MP4 para o TikTok Studio, preenche legenda e publica (ou salva rascunho)."""
    from playwright.sync_api import sync_playwright

    if not video_path.is_file():
        raise FileNotFoundError(f"Vídeo não encontrado: {video_path}")
    if not is_configured(base_dir):
        raise RuntimeError(
            "TikTok Studio não conectado. Execute conectar_tiktok.bat no PC primeiro."
        )

    pdir = profile_dir(base_dir)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(pdir),
            headless=headless,
            viewport={"width": 1280, "height": 860},
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(STUDIO_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(4)

            if "login" in page.url.lower():
                raise RuntimeError("Sessão do TikTok expirou. Rode conectar_tiktok.bat novamente.")

            # 1. Selecionar arquivo MP4 no input file do TikTok Studio
            file_input = page.locator('input[type="file"]').first
            file_input.wait_for(state="attached", timeout=30000)
            file_input.set_input_files(str(video_path.resolve()))

            # 2. Aguardar carregamento e preencher a legenda
            time.sleep(8)
            editor = page.locator('div[contenteditable="true"]').first
            try:
                editor.wait_for(state="visible", timeout=25000)
                editor.click()
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
                page.keyboard.insert_text(caption[:2100])
            except Exception:
                pass

            # 3. Aguardar processamento do vídeo
            time.sleep(6)

            # 4. Clicar em Publicar ou Salvar rascunho
            if mode == "draft":
                btn = page.locator(
                    'button:has-text("Salvar rascunho"), button:has-text("Save draft")'
                ).first
            else:
                btn = page.locator(
                    'button[data-e2e="post_video_button"], '
                    'button:has-text("Publicar"), button:has-text("Post")'
                ).last

            btn.wait_for(state="visible", timeout=30000)
            btn.scroll_into_view_if_needed()
            btn.click()
            time.sleep(8)

            # Caso apareça modal de confirmação ("Publicar agora")
            confirm = page.locator('button:has-text("Publicar agora"), button:has-text("Post now")')
            if confirm.count() > 0 and confirm.first.is_visible():
                confirm.first.click()
                time.sleep(6)

            return {
                "status": "draft" if mode == "draft" else "published",
                "url": "https://www.tiktok.com/tiktokstudio/content",
            }
        finally:
            ctx.close()


if __name__ == "__main__":
    print(authorize_interactive(Path(__file__).parent.resolve()))
