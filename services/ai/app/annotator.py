from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

MIN_KEYPOINT_CONFIDENCE = 0.5

PERSON_COLOUR = (255, 155, 107)
OBJECT_COLOUR = (68, 181, 242)
WRIST_COLOUR = (99, 92, 255)
JOINT_COLOUR = (255, 255, 255)
BAR_COLOUR = (36, 28, 178)
TEXT_COLOUR = (255, 255, 255)

BONES: tuple[tuple[int, int], ...] = (
    (0, 1),
    (0, 2),
    (1, 3),
    (2, 4),
    (5, 6),
    (5, 7),
    (7, 9),
    (6, 8),
    (8, 10),
    (5, 11),
    (6, 12),
    (11, 12),
    (11, 13),
    (13, 15),
    (12, 14),
    (14, 16),
)


def _dashed_rect(
    frame: np.ndarray,
    bbox: tuple[float, float, float, float],
    colour: tuple[int, int, int],
    thickness: int,
) -> None:
    x1, y1, x2, y2 = (round(value) for value in bbox)
    step = 14
    for x in range(x1, x2, step):
        end = min(x + 8, x2)
        cv2.line(frame, (x, y1), (end, y1), colour, thickness)
        cv2.line(frame, (x, y2), (end, y2), colour, thickness)
    for y in range(y1, y2, step):
        end = min(y + 8, y2)
        cv2.line(frame, (x1, y), (x1, end), colour, thickness)
        cv2.line(frame, (x2, y), (x2, end), colour, thickness)


def _draw_bar(frame: np.ndarray, caption: str) -> None:
    height, width = frame.shape[:2]
    scale = width / 1280
    bar_height = max(round(56 * scale), 28)
    font_scale = 0.9 * scale
    thickness = max(round(2 * scale), 1)
    top = height - bar_height
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, top), (width, height), BAR_COLOUR, -1)
    cv2.addWeighted(overlay, 0.82, frame, 0.18, 0, frame)
    (_text_width, text_height), _ = cv2.getTextSize(
        caption, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
    )
    x = round(24 * scale)
    y = top + (bar_height + text_height) // 2
    cv2.putText(
        frame,
        caption,
        (x, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        TEXT_COLOUR,
        thickness,
        cv2.LINE_AA,
    )


def draw_annotated(
    frame: np.ndarray,
    path: Path,
    caption: str,
    person_bbox: tuple[float, float, float, float] | None,
    keypoints: list[tuple[float, float, float]],
    object_bbox: tuple[float, float, float, float] | None,
    wrist_index: int,
) -> bool:
    try:
        width = frame.shape[1]
        thickness = max(round(2 * width / 1280), 1)
        radius = max(round(4 * width / 1280), 2)
        if person_bbox is not None:
            x1, y1, x2, y2 = (round(value) for value in person_bbox)
            cv2.rectangle(frame, (x1, y1), (x2, y2), PERSON_COLOUR, thickness)
        if object_bbox is not None:
            _dashed_rect(frame, object_bbox, OBJECT_COLOUR, thickness)
        visible = [point[2] >= MIN_KEYPOINT_CONFIDENCE for point in keypoints]
        for start, end in BONES:
            if start >= len(keypoints) or end >= len(keypoints):
                continue
            if not visible[start] or not visible[end]:
                continue
            first = (round(keypoints[start][0]), round(keypoints[start][1]))
            second = (round(keypoints[end][0]), round(keypoints[end][1]))
            cv2.line(frame, first, second, PERSON_COLOUR, thickness)
        for index, point in enumerate(keypoints):
            if not visible[index]:
                continue
            centre = (round(point[0]), round(point[1]))
            if index == wrist_index:
                cv2.circle(frame, centre, radius + 2, WRIST_COLOUR, -1)
            else:
                cv2.circle(frame, centre, radius, JOINT_COLOUR, -1)
        _draw_bar(frame, caption)
        written = cv2.imwrite(
            str(path),
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), settings.ANNOTATED_SNAPSHOT_QUALITY],
        )
    except (cv2.error, ValueError, OSError) as exc:
        logger.error("annotated snapshot failed: %s", exc)
        return False
    if not written:
        logger.error("annotated snapshot not written %s", path.name)
        return False
    logger.info(
        "annotated snapshot written %s bytes=%d",
        path.name,
        path.stat().st_size if path.is_file() else 0,
    )
    return True
