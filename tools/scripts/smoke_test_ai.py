from __future__ import annotations

import sys
from pathlib import Path

import grpc

sys.path.insert(0, "/app")

from app.grpc_gen import inference_pb2, inference_pb2_grpc

IMAGE_PATH = Path("/app/ai-model/outputs/webcam-validation/concealment_test.jpg")
CAMERA_ID = "smoke-cam"
SESSION_ID = 42
FRAME_COUNT = 35


def main() -> int:
    if not IMAGE_PATH.exists():
        print(f"image not found: {IMAGE_PATH}", file=sys.stderr)
        return 2

    payload = IMAGE_PATH.read_bytes()
    print(f"loaded {len(payload)} bytes from {IMAGE_PATH.name}")

    credentials = grpc.ssl_channel_credentials(
        root_certificates=Path("/run/secrets/ai_tls_ca").read_bytes(),
        private_key=Path("/run/secrets/ai_tls_key").read_bytes(),
        certificate_chain=Path("/run/secrets/ai_tls_cert").read_bytes(),
    )
    channel = grpc.secure_channel("ai:50051", credentials)
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
            f"state={state}  score={response.score:.3f}  "
            f"persons={len(response.persons)}  objects={len(response.objects)}"
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
    print(f"  frame size        : {last.frame_width} x {last.frame_height}")
    print(f"  persons           : {len(last.persons)}")
    for person in last.persons:
        visible = sum(1 for kp in person.keypoints if kp.confidence >= 0.5)
        print(
            f"    track {person.track_id}  state="
            f"{inference_pb2.InferenceState.Name(person.inference_state)}  "
            f"score={person.score:.3f}  keypoints={len(person.keypoints)}  visible={visible}"
        )
        print(
            f"      bbox ({person.bbox.x1:.0f}, {person.bbox.y1:.0f}) "
            f"({person.bbox.x2:.0f}, {person.bbox.y2:.0f})"
        )
        for index in (9, 10):
            if index < len(person.keypoints):
                wrist = person.keypoints[index]
                side = "left" if index == 9 else "right"
                print(
                    f"      {side} wrist ({wrist.x:.0f}, {wrist.y:.0f}) "
                    f"conf={wrist.confidence:.2f}"
                )
    print(f"  objects           : {len(last.objects)}")
    for obj in last.objects:
        print(
            f"    track {obj.track_id}  {obj.class_name}  conf={obj.confidence:.2f}  "
            f"bbox ({obj.bbox.x1:.0f}, {obj.bbox.y1:.0f}) ({obj.bbox.x2:.0f}, {obj.bbox.y2:.0f})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
