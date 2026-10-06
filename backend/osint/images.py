import asyncio
import base64
import io

import httpx
from PIL import Image

from .settings import CFG

MAX_BYTES = 2_000_000
_sem = asyncio.Semaphore(8)


def dhash(img: Image.Image) -> str | None:
    """64-bit difference hash as hex. None for tiny or flat images (placeholders)."""
    if min(img.size) < 32:
        return None
    px = list(img.convert("L").resize((9, 8)).tobytes())
    if max(px) - min(px) < 8:
        return None
    bits = 0
    for y in range(8):
        for x in range(8):
            bits = bits << 1 | (px[y * 9 + x] > px[y * 9 + x + 1])
    return f"{bits:016x}"


def thumb_b64(img: Image.Image) -> str:
    """128px JPEG thumbnail, base64: stored with the finding so the UI never depends on the remote URL."""
    t = img.convert("RGB")
    t.thumbnail((128, 128))
    buf = io.BytesIO()
    t.save(buf, "JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


def hamming(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


async def phash_url(client: httpx.AsyncClient, url: str) -> tuple[str, str] | None:
    """Download a public avatar -> (hash, thumbnail b64). Any failure -> None (avatars are best-effort)."""
    if not CFG["fetch_avatars"]:
        return None
    async with _sem:
        try:
            async with client.stream("GET", url) as r:
                if r.status_code != 200:
                    return None
                data = b""
                async for chunk in r.aiter_bytes():
                    data += chunk
                    if len(data) > MAX_BYTES:
                        return None
            img = Image.open(io.BytesIO(data))
            h = dhash(img)
            return (h, thumb_b64(img)) if h else None
        except Exception:
            return None
