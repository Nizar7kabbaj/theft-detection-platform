from pathlib import Path
import numpy as np
import torch
import torch.nn as nn


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
        out, _ = self.lstm(x)
        last = out[:, -1, :]
        return self.classifier(last)
class ShoplifterPredictor:
    def __init__(self, model_path, device=None, store=None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.device = torch.device(self.device)
        ckpt = torch.load(Path(model_path), map_location=self.device, weights_only=True)
        self.model_config = ckpt["model_config"]
        self.preproc = ckpt["preprocessing"]
        self.labels = ckpt["labels"]
        self.window = int(self.preproc["window"])
        self.num_kp = int(self.preproc["num_keypoints"])
        self.feat_per_kp = int(self.preproc["feat_per_keypoint"])
        self.feat_dim = self.num_kp * self.feat_per_kp
        self.model = ShoplifterLSTM(**self.model_config).to(self.device)
        self.model.load_state_dict(ckpt["state_dict"])
        self.model.eval()
        self._store = store
    def _normalize(self, bbox_xyxy, keypoints):
        x1, y1, x2, y2 = bbox_xyxy
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        half_w = max((x2 - x1) / 2.0, 1.0)
        half_h = max((y2 - y1) / 2.0, 1.0)
        kp = np.asarray(keypoints, dtype=np.float32).copy()
        if kp.shape != (self.num_kp, self.feat_per_kp):
            return np.zeros(self.feat_dim, dtype=np.float32)
        kp[:, 0] = (kp[:, 0] - cx) / half_w
        kp[:, 1] = (kp[:, 1] - cy) / half_h
        bad = ~np.isfinite(kp).all(axis=1)
        if bad.any():
            kp[bad] = 0.0
        return kp.reshape(-1).astype(np.float32)
    def update(self, camera_id, track_id, bbox_xyxy, keypoints, frame_index):
        if self._store is None:
            raise RuntimeError("predictor has no tracker store")
        self._store.append(
            camera_id=camera_id,
            track_id=track_id,
            frame_index=frame_index,
            bbox_xyxy=bbox_xyxy,
            keypoints=keypoints,
        )
        window = self._store.read_window(camera_id=camera_id, track_id=track_id)
        if len(window) < self.window:
            return None, None
        seq = np.stack(
            [self._normalize(bbox, kp) for bbox, kp in window],
            axis=0,
        )
        x = torch.from_numpy(seq).unsqueeze(0).to(self.device)
        with torch.no_grad():
            logits = self.model(x)
            probs = torch.softmax(logits, dim=1)[0]
            p_normal  = float(probs[0].item())
            p_anomaly = float(probs[1].item())
        return p_normal, p_anomaly
    def drop_track(self, camera_id, track_id):
        if self._store is not None:
            self._store.drop(camera_id=camera_id, track_id=track_id)
