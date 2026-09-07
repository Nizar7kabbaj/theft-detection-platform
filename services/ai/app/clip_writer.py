from __future__ import annotations

import logging
from fractions import Fraction
from pathlib import Path

import av

from app.core.config import settings

logger = logging.getLogger(__name__)

TIME_BASE = Fraction(1, 1000)


def _target_size(width: int, height: int) -> tuple[int, int]:
    if width <= 0 or height <= 0:
        return width, height
    target_width = min(settings.CLIP_WIDTH, width)
    scale = target_width / width
    target_height = round(height * scale)
    return target_width - (target_width % 2), target_height - (target_height % 2)


def write_clip(
    frames: list[tuple[float, bytes]],
    path: Path,
    width: int,
    height: int,
) -> bool:
    if not frames:
        return False
    out_width, out_height = _target_size(width, height)
    if out_width <= 0 or out_height <= 0:
        logger.error("clip encode skipped, bad size %dx%d", width, height)
        return False
    start = frames[0][0]
    max_rate = f"{settings.CLIP_MAX_BITRATE_KBPS}k"
    buf_size = f"{settings.CLIP_MAX_BITRATE_KBPS * 2}k"
    temp_path = path.with_suffix(".mp4.part")
    container = None
    try:
        container = av.open(
            str(temp_path), mode="w", format="mp4", options={"movflags": "+faststart"}
        )
        stream = container.add_stream("libx264", rate=30)
        stream.width = out_width
        stream.height = out_height
        stream.pix_fmt = "yuv420p"
        stream.codec_context.time_base = TIME_BASE
        stream.options = {
            "preset": settings.CLIP_PRESET,
            "crf": str(settings.CLIP_CRF),
            "maxrate": max_rate,
            "bufsize": buf_size,
        }
        for captured_at, image_bytes in frames:
            packet = av.Packet(image_bytes)
            decoded = av.codec.CodecContext.create("mjpeg", "r").decode(packet)
            if not decoded:
                continue
            frame = decoded[0].reformat(width=out_width, height=out_height, format="yuv420p")
            frame.pts = int((captured_at - start) / TIME_BASE)
            frame.time_base = TIME_BASE
            for encoded in stream.encode(frame):
                container.mux(encoded)
        for encoded in stream.encode():
            container.mux(encoded)
    except (av.AVError, ValueError, OSError) as exc:
        logger.error("clip encode failed: %s", exc)
        temp_path.unlink(missing_ok=True)
        return False
    finally:
        if container is not None:
            container.close()
    if not temp_path.is_file():
        return False
    temp_path.replace(path)
    logger.info(
        "clip written %s %dx%d bytes=%d",
        path.name,
        out_width,
        out_height,
        path.stat().st_size if path.is_file() else 0,
    )
    return path.is_file()
