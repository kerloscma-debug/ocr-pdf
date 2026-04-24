import hashlib, shutil, uuid
from pathlib import Path

UPLOAD_DIR = Path("uploads")

def compute_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def save_upload(data: bytes, filename: str) -> tuple[str, Path]:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    batch_id = str(uuid.uuid4())
    dest = UPLOAD_DIR / f"{batch_id}_{filename}"
    dest.write_bytes(data)
    return batch_id, dest

def cleanup(path: Path):
    try:
        if path and path.exists():
            path.unlink()
    except Exception:
        pass

def cleanup_dir(path: Path):
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass
