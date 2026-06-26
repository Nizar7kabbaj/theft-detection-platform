from __future__ import annotations

import sys
from pathlib import Path

import grpc

sys.path.insert(0, "/app")

from app.grpc_gen import inference_pb2, inference_pb2_grpc


def main() -> int:
    image_path = Path("/app/ai-model/outputs/webcam-validation/opencv_index_0.jpg")
    if not image_path.exists():
        print(f"image not found: {image_path}", file=sys.stderr)
        return 2

    payload = image_path.read_bytes()
    print(f"loaded {len(payload)} bytes from {image_path.name}")

    channel = grpc.insecure_channel("localhost:50051")
    stub = inference_pb2_grpc.InferenceServiceStub(channel)

    frame = inference_pb2.Frame(
        payload=payload,
        session_id=42,
        frame_index=0,
    )

    print("calling Analyze...")
    response = stub.Analyze(frame, timeout=30.0)

    print("response received:")
    print(f"  alert_type : {response.alert_type!r}")
    print(f"  score      : {response.score}")
    print(f"  bbox       : ({response.bbox.x1}, {response.bbox.y1}, {response.bbox.x2}, {response.bbox.y2})")
    print(f"  keypoints  : {len(response.keypoints)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
