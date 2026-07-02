from __future__ import annotations

import base64
import os

import grpc
import pytest
from google.protobuf.timestamp_pb2 import Timestamp

from app.grpc_gen import inference_pb2 as inf_pb
from app.grpc_gen.inference_pb2_grpc import InferenceServiceStub


pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]

_TINY_JPEG_B64 = (
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a"
    "HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIy"
    "MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAAIAAgDASIA"
    "AhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQA"
    "AAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3"
    "ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWm"
    "p6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/9oADAMB"
    "AAIRAxEAPwD3+iiigD//2Q=="
)


def _tiny_jpeg() -> bytes:
    return base64.b64decode(_TINY_JPEG_B64)


def _build_frame(
    payload: bytes,
    session_id: int = 1,
    frame_index: int = 0,
) -> inf_pb.Frame:
    ts = Timestamp()
    ts.GetCurrentTime()
    return inf_pb.Frame(
        payload=payload,
        session_id=session_id,
        frame_index=frame_index,
        timestamp=ts,
    )


def _is_valid_detection(det: inf_pb.Detection) -> bool:
    if not isinstance(det.score, float):
        return False
    if not isinstance(det.inference_state, int):
        return False
    if not isinstance(det.track_id, int):
        return False
    if not isinstance(det.detection_present, bool):
        return False
    return True


async def test_analyze_returns_detection_shape(
    inference_stub: InferenceServiceStub,
) -> None:
    frame = _build_frame(_tiny_jpeg())

    det = await inference_stub.Analyze(frame)

    assert _is_valid_detection(det)
    assert 0.0 <= det.score <= 1.0
    assert isinstance(det.bbox.x1, float)
    assert isinstance(det.bbox.y1, float)
    assert isinstance(det.bbox.x2, float)
    assert isinstance(det.bbox.y2, float)


async def test_analyze_empty_frame_tolerated(
    inference_stub: InferenceServiceStub,
) -> None:
    frame = _build_frame(b"")

    try:
        det = await inference_stub.Analyze(frame)
    except grpc.aio.AioRpcError as exc:
        assert exc.code() in (
            grpc.StatusCode.INVALID_ARGUMENT,
            grpc.StatusCode.INTERNAL,
            grpc.StatusCode.UNKNOWN,
        )
        return

    assert _is_valid_detection(det)
    assert det.score == 0.0 or det.score < 0.1
    assert det.detection_present is False


async def test_analyze_malformed_bytes_tolerated(
    inference_stub: InferenceServiceStub,
) -> None:
    frame = _build_frame(os.urandom(256))

    try:
        det = await inference_stub.Analyze(frame)
    except grpc.aio.AioRpcError as exc:
        assert exc.code() in (
            grpc.StatusCode.INVALID_ARGUMENT,
            grpc.StatusCode.INTERNAL,
            grpc.StatusCode.UNKNOWN,
        )
        return

    assert _is_valid_detection(det)
    assert det.score < 0.1
