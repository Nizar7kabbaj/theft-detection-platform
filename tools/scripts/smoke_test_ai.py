from __future__ import annotations

import sys
from pathlib import Path

import grpc

sys.path.insert(0, "/app")

from app.grpc_gen import inference_pb2, inference_pb2_grpc

IMAGE_PATH = Path("/app/ai-model/outputs/webcam-validation/opencv_index_0.jpg")
CAMERA_ID = "smoke-cam"
SESSION_ID = 42
FRAME_COUNT = 35


def main() -> int:
    if not IMAGE_PATH.exists():
        print(f"image not found: {IMAGE_PATH}", file=sys.stderr)
        return 2

    payload = IMAGE_PATH.read_bytes()
    print(f"loaded {len(payload)} bytes from {IMAGE_PATH.name}")

    channel = grpc.insecure_channel("localhost:50051")
    stub = inference_pb2_grpc.InferenceServiceStub(channel)

    print(f"sending {FRAME_COUNT} frames on camera {CAMERA_ID}")

    classified = 0
    last = None
    for frame_index in range(FRAME_COUNT):
        frame = inference_pb2.Frame(
            payload=payload,
            session_id=SESSION_ID,
            frame_index=frame_index,
            camera_id=CAMERA_ID,
        )
        response = stub.Analyze(frame, timeout=30.0)
        state = inference_pb2.InferenceState.Name(response.inference_state)
        print(
            f"  frame {frame_index:2d}  present={response.detection_present}  "
            f"state={state}  score={response.score:.3f}  track_id={response.track_id}"
        )
        if response.inference_state in (
            inference_pb2.INFERENCE_STATE_NORMAL,
            inference_pb2.INFERENCE_STATE_ANOMALY,
        ):
            classified += 1
        last = response

    if last is None:
        print("no response received", file=sys.stderr)
        return 1

    print(f"frames classified past warmup: {classified} of {FRAME_COUNT}")
    print("final detection:")
    print(f"  detection_present : {last.detection_present}")
    print(f"  inference_state   : {inference_pb2.InferenceState.Name(last.inference_state)}")
    print(f"  score             : {last.score:.4f}")
    print(f"  track_id          : {last.track_id}")
    print(f"  bbox              : ({last.bbox.x1}, {last.bbox.y1}, {last.bbox.x2}, {last.bbox.y2})")
    print(f"  keypoints         : {len(last.keypoints)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
