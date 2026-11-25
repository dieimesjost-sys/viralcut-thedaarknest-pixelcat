"""ViralCut - Gerador de thumbnails: frame do vídeo + título + logo do canal no canto inferior direito."""
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

SIZES = {"9:16": (1080, 1920), "16:9": (1280, 720)}
YELLOW = (255, 225, 26)
FONTS = [
    "C:/Windows/Fonts/ariblk.ttf", "C:/Windows/Fonts/impact.ttf", "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _font(size):
    for f in FONTS:
        try:
            return ImageFont.truetype(f, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _duration(video: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(video)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except Exception:
        return 10.0


def _wrap(words, font, maxw):
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if font.getlength(t) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _fit(text, maxw, maxlines, start, minsz=56):
    words = text.upper().split() or ["VÍDEO"]
    for sz in range(start, minsz - 1, -6):
        f = _font(sz)
        lines = _wrap(words, f, maxw)
        if len(lines) <= maxlines and all(f.getlength(l) <= maxw for l in lines):
            return f, lines
    f = _font(minsz)
    return f, _wrap(words, f, maxw)[:maxlines]


def make_thumbnail(video_path: Path, title: str, logo_path, out_path: Path,
                   fmt: str = "9:16", position: float = 0.35) -> Path:
    W, H = SIZES.get(fmt, SIZES["9:16"])
    t = max(0.5, _duration(video_path) * min(max(position, 0.02), 0.98))
    tmp = out_path.with_suffix(".frame.jpg")
    subprocess.run(["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(video_path), "-frames:v", "1",
                    "-q:v", "2", str(tmp)], capture_output=True, check=True)
    frame = Image.open(tmp).convert("RGB")
    tmp.unlink(missing_ok=True)

    if fmt == "16:9":
        bg = ImageOps.fit(frame, (W, H)).filter(ImageFilter.GaussianBlur(30))
        bg = Image.blend(bg, Image.new("RGB", (W, H), (8, 8, 24)), 0.55)
        fh = H - 40
        fw = int(frame.width * fh / frame.height)
        fg = frame.resize((fw, fh), Image.LANCZOS)
        canvas = bg.copy()
        px = W - fw - 50
        ImageDraw.Draw(canvas).rectangle([px - 6, 14, px + fw + 6, 26 + fh], fill=(0, 0, 0))
        canvas.paste(fg, (px, 20))
        box = (50, 40, px - 40, H - 40)
    else:
        canvas = ImageOps.fit(frame, (W, H), Image.LANCZOS)
        grad = Image.new("L", (1, H))
        for y in range(H):
            grad.putpixel((0, y), int(215 * max(0, (y - H * 0.35) / (H * 0.65)) ** 1.3))
        canvas.paste(Image.new("RGB", (W, H), (0, 0, 0)), (0, 0), grad.resize((W, H)))
        box = (60, int(H * 0.52), W - 60, int(H * 0.86))

    bw, bh = box[2] - box[0], box[3] - box[1]
    font, lines = _fit(title, bw, 4 if fmt == "16:9" else 3, 150 if fmt == "9:16" else 110)
    lh = int(font.size * 1.12)
    y = box[1] + (bh - lh * len(lines)) // 2 + lh // 2
    d = ImageDraw.Draw(canvas)
    for i, line in enumerate(lines):
        x = box[0] + (bw // 2 if fmt == "9:16" else 0)
        d.text((x, y), line, font=font, anchor="mm" if fmt == "9:16" else "lm",
               fill=YELLOW if i == len(lines) - 1 else (255, 255, 255),
               stroke_width=max(6, font.size // 12), stroke_fill=(0, 0, 0))
        y += lh

    if logo_path and Path(logo_path).is_file():
        logo = Image.open(logo_path).convert("RGBA")
        lw = int(W * (0.22 if fmt == "9:16" else 0.13))
        logo = logo.resize((lw, int(logo.height * lw / logo.width)), Image.LANCZOS)
        m = int(W * 0.035)
        pos = (W - logo.width - m, H - logo.height - m)
        shadow = Image.new("RGBA", logo.size, (0, 0, 0, 0))
        shadow.putalpha(logo.getchannel("A").point(lambda a: int(a * 0.6)))
        shadow = shadow.filter(ImageFilter.GaussianBlur(6))
        canvas.paste(Image.new("RGB", logo.size, (0, 0, 0)), (pos[0] + 4, pos[1] + 6), shadow.getchannel("A"))
        canvas.paste(logo, pos, logo)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, "JPEG", quality=92)
    return out_path
