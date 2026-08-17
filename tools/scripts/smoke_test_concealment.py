from __future__ import annotations

import sys
from pathlib import Path

import grpc

sys.path.insert(0, "/app")

from app.grpc_gen import inference_pb2, inference_pb2_grpc

BASE = Path("/app/ai-model/outputs/webcam-validation")
HOLDING_PATH = BASE / "phase_holding.jpg"
HIDDEN_PATH = BASE / "phase_hidden.jpg"
CAMERA_ID = "concealment-cam"
SESSION_ID = 77
HOLDING_FRAMES = 40
HIDDEN_FRAMES = 50


def main() -> int:
    for path in (HOLDING_PATH, HIDDEN_PATH):
        if not path.exists():
            print(f"image not found: {path}", file=sys.stderr)
            return 2

    holding = HOLDING_PATH.read_bytes()
    hidden = HIDDEN_PATH.read_bytes()

    credentials = grpc.ssl_channel_credentials(
        root_certificates=Path("/run/secrets/ai_tls_ca").read_bytes(),
        private_key=Path("/run/secrets/ai_tls_key").read_bytes(),
        certificate_chain=Path("/run/secrets/ai_tls_cert").read_bytes(),
    )
    channel = grpc.secure_channel("ai:50051", credentials)
    stub = inference_pb2_grpc.InferenceServiceStub(channel)

    sequence = [(holding, "holding")] * HOLDING_FRAMES + [(hidden, "hidden")] * HIDDEN_FRAMES
    fired = 0

    for frame_index, (payload, phase) in enumerate(sequence):
        frame = inference_pb2.Frame(
            payload=payload,
            session_id=SESSION_ID,
            frame_index=frame_index,
            camera_id=CAMERA_ID,
        )
        response = stub.Analyze(frame, timeout=30.0)
        marker = ""
        if response.concealments:
            fired += len(response.concealments)
            marker = "  <-- CONCEALMENT"
        if frame_index % 5 == 0 or response.concealments:
            print(
                f"  frame {frame_index:3d} {phase:8s} persons={len(response.persons)} "
                f"objects={len(response.objects)}{marker}"
            )
        for verdict in response.concealments:
            print(
                f"    object track {verdict.object_track_id} {verdict.object_class} "
                f"missing={verdict.missing_frames} last_seen={verdict.last_seen_frame}"
            )
            print(
                f"    taken by person {verdict.person_track_id} wrist {verdict.wrist_index} "
                f"at ({verdict.wrist_x:.0f}, {verdict.wrist_y:.0f}) "
                f"grab_distance={verdict.grab_distance:.2f} torso lengths"
            )

    print(f"concealment verdicts: {fired}")
    return 0 if fired else 1


if __name__ == "__main__":
    sys.exit(main())
