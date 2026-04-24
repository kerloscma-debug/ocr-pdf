"""Convert PDF/image to list of JPEG paths for Vision API."""
import asyncio, subprocess, tempfile
from pathlib import Path
from app.config import settings

async def pdf_to_images(pdf_path: Path, out_dir: Path) -> list[Path]:
    prefix = str(out_dir / "pg")
    cmd = ["pdftoppm", "-jpeg", "-r", str(settings.PAGE_DPI), str(pdf_path), prefix]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"pdftoppm error: {err.decode()}")
    all_imgs = sorted(out_dir.glob("pg-*.jpg"))
    # Drop tiny CamScanner watermarks (< 20 KB)
    return [p for p in all_imgs if p.stat().st_size > 20_000] or all_imgs

async def image_to_pages(img_path: Path, out_dir: Path) -> list[Path]:
    """Single image file → list with one item."""
    dest = out_dir / "pg-001.jpg"
    from PIL import Image
    img = Image.open(img_path).convert("RGB")
    img.save(dest, "JPEG", quality=90)
    return [dest]

async def to_page_images(file_path: Path, out_dir: Path) -> list[Path]:
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        return await pdf_to_images(file_path, out_dir)
    elif suffix in (".jpg", ".jpeg", ".png"):
        return await image_to_pages(file_path, out_dir)
    raise ValueError(f"Unsupported file type: {suffix}")
