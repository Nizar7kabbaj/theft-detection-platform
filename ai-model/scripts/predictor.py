"""
ShoplifterPredictor — TDP-89

Loads the trained ShoplifterLSTM checkpoint and produces a binary
(normal / anomaly) prediction per tracked person, over a sliding window
of 30 normalized keypoint frames.

Normalization is byte-for-byte identical to training (lesson #58):
  cx = (x1 + x2) / 2
  cy = (y1 + y2) / 2
  half_w = max((x2 - x1) / 2, 1.0)
  half_h = max((y2 - y1) / 2, 1.0)
  x_norm = (x - cx) / half_w
  y_norm = (y - cy) / half_h
  conf stays raw

The model class layout is byte-for-byte identical to training (lesson #57):
  classifier = nn.Sequential(Dropout, Linear)  -- NOT a bare nn.Linear
"""

from collections import deque
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn


# ---------------------------------------------------------------------------
# Model class -- MUST match the training notebook byte-for-byte (lesson #57)
# ---------------------------------------------------------------------------
class ShoplifterLSTM(nn.Module):
    def __init__(self, input_size, hidden_size, num_layers, dropout, num_classes):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            dropout=dropout,
            batch_first=True,
        )
        self.classifier = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(hidden_size, num_classes),
        )

    def forward(self, x):
        # x: (batch, seq_len=30, input_size=51)
        out, _ = self.lstm(x)
        # take the last time step
        last = out[:, -1, :]
        return self.classifier(last)


# ---------------------------------------------------------------------------
# Predictor
# ---------------------------------------------------------------------------
class ShoplifterPredictor:
    """
    Per-person sliding-window classifier.

    Usage:
        pred = ShoplifterPredictor("ai-model/models/shoplifting_classifier.pt")
        label, conf = pred.update(track_id=3, bbox_xyxy=(x1,y1,x2,y2), keypoints=kp)
        # label is one of: "warming up", "normal", "anomaly"
        # conf is None during warmup, else float in [0, 1]
    """

    def __init__(self, model_path, device=None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.device = torch.device(self.device)

        ckpt = torch.load(Path(model_path), map_location=self.device, weights_only=True)

        self.model_config = ckpt["model_config"]
        self.preproc = ckpt["preprocessing"]
        self.labels = ckpt["labels"]  # {0: "normal", 1: "anomaly"}

        self.window = int(self.preproc["window"])              # 30
        self.num_kp = int(self.preproc["num_keypoints"])       # 17
        self.feat_per_kp = int(self.preproc["feat_per_keypoint"])  # 3
        self.feat_dim = self.num_kp * self.feat_per_kp         # 51

        # Build the model with the exact training-time config
        self.model = ShoplifterLSTM(**self.model_config).to(self.device)
        self.model.load_state_dict(ckpt["state_dict"])
        self.model.eval()

        # Per-track sliding deques of (51,) float32 vectors
        self._buffers = {}  # track_id -> deque[np.ndarray (51,)]

    # -----------------------------------------------------------------------
    # Normalization (lesson #58 -- subtract center AND divide by half size)
    # -----------------------------------------------------------------------
    def _normalize(self, bbox_xyxy, keypoints):
        """
        bbox_xyxy: iterable of 4 floats (x1, y1, x2, y2)
        keypoints: ndarray shape (17, 3), columns = (x, y, conf)
        Returns: ndarray shape (51,) float32
        """
        x1, y1, x2, y2 = bbox_xyxy
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        half_w = max((x2 - x1) / 2.0, 1.0)
        half_h = max((y2 - y1) / 2.0, 1.0)

        kp = np.asarray(keypoints, dtype=np.float32).copy()
        if kp.shape != (self.num_kp, self.feat_per_kp):
            # If the upstream gave us a wrong shape, return zeros to avoid crashes
            return np.zeros(self.feat_dim, dtype=np.float32)

        kp[:, 0] = (kp[:, 0] - cx) / half_w
        kp[:, 1] = (kp[:, 1] - cy) / half_h
        # confidence column stays raw

        # NaN sanitization (lesson #51) -- any non-finite keypoint -> zero vector
        bad = ~np.isfinite(kp).all(axis=1)
        if bad.any():
            kp[bad] = 0.0

        return kp.reshape(-1).astype(np.float32)

    # -----------------------------------------------------------------------
    # Update one track and return the latest prediction (or warmup)
    # -----------------------------------------------------------------------
    def update(self, track_id, bbox_xyxy, keypoints):
        """
        Push one frame for one tracked person, return (label, confidence).

        track_id    -- int, from YOLOv8 model.track(); MUST NOT be None.
        bbox_xyxy   -- (x1, y1, x2, y2)
        keypoints   -- ndarray (17, 3)

        Returns:
            ("warming up", None) while the deque is filling
            ("normal", conf)     once full and predicted normal
            ("anomaly", conf)    once full and predicted anomaly
        """
        feat = self._normalize(bbox_xyxy, keypoints)

        buf = self._buffers.get(track_id)
        if buf is None:
            buf = deque(maxlen=self.window)
            self._buffers[track_id] = buf
        buf.append(feat)

        if len(buf) < self.window:
            return None, None

        # Build (1, 30, 51) tensor and run inference
        seq = np.stack(buf, axis=0)  # (30, 51)
        x = torch.from_numpy(seq).unsqueeze(0).to(self.device)  # (1, 30, 51)

        with torch.no_grad():
            logits = self.model(x)                   # (1, 2)
            probs = torch.softmax(logits, dim=1)[0]  # (2,)
            p_normal  = float(probs[0].item())
            p_anomaly = float(probs[1].item())

        # Return both probabilities; caller decides the threshold.
        return p_normal, p_anomaly

    # -----------------------------------------------------------------------
    # Optional: forget a track that hasn't been seen in a while
    # -----------------------------------------------------------------------
    def drop_track(self, track_id):
        self._buffers.pop(track_id, None)

    def active_track_ids(self):
        return list(self._buffers.keys())


# ---------------------------------------------------------------------------
# Self-test: run this file directly to verify the checkpoint loads cleanly
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    model_path = "ai-model/models/shoplifting_classifier.pt"
    print(f"Loading {model_path} ...")
    pred = ShoplifterPredictor(model_path)
    print(f"  device       : {pred.device}")
    print(f"  window       : {pred.window}")
    print(f"  feat_dim     : {pred.feat_dim}")
    print(f"  labels       : {pred.labels}")
    print(f"  model_config : {pred.model_config}")

    # Feed 35 fake frames for one track and confirm:
    #   - frames 1..29  -> warmup (update() returns None, None)
    #   - frames 30..35 -> two real probabilities that sum to ~1.0
    rng = np.random.default_rng(0)
    bbox = (100, 100, 300, 500)  # arbitrary
    print("\nSimulating 35 frames for track_id=1 ...")
    for i in range(1, 36):
        kp = rng.uniform(low=100, high=500, size=(17, 3)).astype(np.float32)
        kp[:, 2] = rng.uniform(0.0, 1.0, size=17)
        p_normal, p_anomaly = pred.update(track_id=1, bbox_xyxy=bbox, keypoints=kp)
        if i in (1, 15, 29, 30, 31, 35):
            if p_normal is None:
                print(f"  frame {i:3d}: warming up")
            else:
                print(f"  frame {i:3d}: p_normal={p_normal:.3f}  p_anomaly={p_anomaly:.3f}")

    print("\nOK -- predictor.py self-test passed.")
    sys.exit(0)