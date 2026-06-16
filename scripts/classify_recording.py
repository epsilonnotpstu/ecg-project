import sys
import os
import numpy as np
import pandas as pd
from collections import Counter
from scipy.signal import butter, filtfilt, iirnotch, find_peaks

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FS = 125          # ESP8266 now runs at 125Hz — no resampling needed
BEAT_PRE = 90
BEAT_POST = 97
BEAT_LEN = 187

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        model_path = os.path.join(ROOT, "models", "ecg_model_int8.tflite")
        if not os.path.exists(model_path):
            return None
        from ml.inference_engine import InferenceEngine
        cfg = {"ALERT_CLASSES": [2, 3], "ALERT_CONFIDENCE_THRESHOLD": 0.70, "TIMER_LOG": False}
        _engine = InferenceEngine(model_path, cfg)
    return _engine


def load_signal(csv_path):
    """Load CSV and return signal at 125Hz (no resampling needed)."""
    df = pd.read_csv(csv_path)
    df = df[df["lead_ok"] == 1].reset_index(drop=True)
    return df["value"].values.astype(float)


def filter_signal(sig, fs=FS):
    b_notch, a_notch = iirnotch(50.0 / (fs / 2), 30.0)
    sig = filtfilt(b_notch, a_notch, sig)
    b, a = butter(4, [0.5 / (fs / 2), 40.0 / (fs / 2)], btype="band")
    return filtfilt(b, a, sig)


def segment_beats(sig, fs=FS):
    s = sig - np.mean(sig)
    min_dist = int(0.4 * fs)   # 0.4s minimum between beats = max 150 BPM
    peaks, _ = find_peaks(s, height=np.std(s) * 1.5, distance=min_dist)

    beats = []
    for p in peaks:
        start, end = p - BEAT_PRE, p + BEAT_POST
        beat = np.zeros(BEAT_LEN, dtype=np.float32)
        src_start = max(0, start)
        src_end = min(len(sig), end)
        dst_start = src_start - start
        n = src_end - src_start
        beat[dst_start:dst_start + n] = sig[src_start:src_end]

        bmin, bmax = beat.min(), beat.max()
        span = bmax - bmin
        if span < 1e-8:
            continue
        beat = (beat - bmin) / span
        beats.append(beat.astype(np.float32))

    return np.array(beats), peaks


def classify_recording(raw_csv_path):
    sig = load_signal(raw_csv_path)
    filtered = filter_signal(sig)
    beats, peaks = segment_beats(filtered)

    engine = _get_engine()
    if engine is None:
        return {
            "available": False,
            "reason": "model not found at models/ecg_model_int8.tflite",
            "num_beats": len(beats),
            "beats": [],
        }

    results = [engine.predict(b) for b in beats]
    class_counts = Counter(r["class_name"] for r in results)
    dominant = class_counts.most_common(1)[0][0] if results else None
    alert_count = sum(1 for r in results if r["alert"])

    return {
        "available": True,
        "num_beats": len(results),
        "dominant_class": dominant,
        "class_distribution": dict(class_counts),
        "alert_count": alert_count,
        "beats": results,
    }


if __name__ == "__main__":
    import json
    if len(sys.argv) < 2:
        print("Usage: python scripts/classify_recording.py <raw_csv_path>")
        sys.exit(1)
    result = classify_recording(sys.argv[1])
    print(json.dumps(result, indent=2))