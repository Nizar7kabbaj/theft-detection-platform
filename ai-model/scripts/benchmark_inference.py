import time
import json
import torch
import torch.nn as nn
import numpy as np
from pathlib import Path

ROOT       = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT / "ai-model" / "models" / "shoplifting_classifier.pt"

class ShoplifterLSTM(nn.Module):
    def __init__(self, input_size=51, hidden_size=64, num_layers=2,
                 num_classes=2, dropout=0.3):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers,
                            batch_first=True,
                            dropout=dropout if num_layers > 1 else 0.0)
        self.classifier = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(hidden_size, num_classes),
        )

    def forward(self, x):
        _, (hn, _) = self.lstm(x)
        return self.classifier(hn[-1])


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")
    if device.type == "cuda":
        print(f"GPU:    {torch.cuda.get_device_name(0)}")

    ckpt = torch.load(MODEL_PATH, map_location=device, weights_only=True)
    cfg  = ckpt["model_config"]
    model = ShoplifterLSTM(**cfg).to(device)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    print(f"Model loaded from {MODEL_PATH}")
    print(f"Architecture: {cfg}")

    dummy = torch.randn(1, 30, 51, device=device)

    print("\nWarmup (50 iterations)...")
    with torch.no_grad():
        for _ in range(50):
            _ = model(dummy)
    if device.type == "cuda":
        torch.cuda.synchronize()

    N = 1000
    print(f"Benchmarking {N} forward passes...")
    latencies_ms = []
    with torch.no_grad():
        for _ in range(N):
            if device.type == "cuda":
                torch.cuda.synchronize()
            t0 = time.perf_counter()
            _ = model(dummy)
            if device.type == "cuda":
                torch.cuda.synchronize()
            t1 = time.perf_counter()
            latencies_ms.append((t1 - t0) * 1000.0)

    arr = np.array(latencies_ms)
    mean_ms   = float(arr.mean())
    median_ms = float(np.median(arr))
    p95_ms    = float(np.percentile(arr, 95))
    p99_ms    = float(np.percentile(arr, 99))
    fps_mean  = 1000.0 / mean_ms

    print("\n=== INFERENCE BENCHMARK ===")
    print(f"Iterations:     {N}")
    print(f"Mean latency:   {mean_ms:.3f} ms")
    print(f"Median latency: {median_ms:.3f} ms")
    print(f"p95 latency:    {p95_ms:.3f} ms")
    print(f"p99 latency:    {p99_ms:.3f} ms")
    print(f"Mean FPS:       {fps_mean:.1f}")
    print(f"Demo target:    > 15 FPS  -->  {'PASS' if fps_mean > 15 else 'FAIL'}")

    out = {
        "device":       str(device),
        "gpu":          torch.cuda.get_device_name(0) if device.type == "cuda" else "CPU",
        "iterations":   N,
        "mean_ms":      round(mean_ms, 3),
        "median_ms":    round(median_ms, 3),
        "p95_ms":       round(p95_ms, 3),
        "p99_ms":       round(p99_ms, 3),
        "fps_mean":     round(fps_mean, 1),
        "demo_target_fps": 15,
        "demo_target_met": fps_mean > 15,
    }
    out_dir  = ROOT / "ai-model" / "outputs" / "evaluation"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "inference_benchmark.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nSaved -> {out_path}")


if __name__ == "__main__":
    main()