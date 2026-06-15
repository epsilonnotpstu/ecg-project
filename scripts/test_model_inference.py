import sys
import os
import numpy as np
import pandas as pd
from scipy.signal import butter, filtfilt, iirnotch, find_peaks, resample_poly

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SOURCE_FS = 250   # our ESP8266 sampling rate
TARGET_FS = 125   # model's expected sampling rate (matches signal_processor.py)
BEAT_PRE = 90
BEAT_POST = 97
BEAT_LEN = 187


def load_and_resample(csv_path):
    df = pd.read_csv(csv_path)
    df = df[df["lead_ok"] == 1].reset_index(drop=True)
    raw = df["value"].values.astype(float)
    # 250Hz -> 125Hz (decimate by 2, with anti-aliasing)
    resampled = resample_poly(raw, up=1, down=2)
    return resampled


def filter_signal(sig, fs=TARGET_FS):
    # 50Hz notch (matches signal_processor.py NOTCH_HZ=50, NOTCH_Q=30)
    b_notch, a_notch = iirnotch(50.0 / (fs / 2), 30.0)
    sig = filtfilt(b_notch, a_notch, sig)
    # 0.5-40Hz bandpass, order=4 (matches BP_LOW/BP_HIGH/BP_ORDER)
    b, a = butter(4, [0.5 / (fs / 2), 40.0 / (fs / 2)], btype="band")
    sig = filtfilt(b, a, sig)
    return sig


def segment_beats(sig, fs=TARGET_FS):
    s = sig - np.mean(sig)
    peaks, _ = find_peaks(s, height=np.std(s) * 1.5, distance=int(0.4 * fs))

    beats = []
    for p in peaks:
        start, end = p - BEAT_PRE, p + BEAT_POST
        beat = np.zeros(BEAT_LEN, dtype=np.float32)

        src_start, src_end = max(0, start), min(len(sig), end)
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


def main(csv_path):
    print(f"Loading: {csv_path}")
    resampled = load_and_resample(csv_path)
    print(f"Resampled: {len(resampled)} samples @ {TARGET_FS}Hz "
          f"(~{len(resampled)/TARGET_FS:.1f}s)")

    filtered = filter_signal(resampled)
    beats, peaks = segment_beats(filtered)
    print(f"Beats segmented: {len(beats)}")

    if len(beats) == 0:
        print("No beats found ? check signal quality.")
        return

    model_path = os.path.join(ROOT, "models", "ecg_model_int8.tflite")
    if not os.path.exists(model_path):
        print(f"\nModel NOT found at: {model_path}")
        print("Run ml/train.py + ml/quantize.py on a dev machine, then copy")
        print("the resulting .tflite file to models/ on this Pi.")
        return

    from ml.inference_engine import InferenceEngine
    cfg = {"ALERT_CLASSES": [2, 3], "ALERT_CONFIDENCE_THRESHOLD": 0.70, "TIMER_LOG": False}
    engine = InferenceEngine(model_path, cfg)

    print(f"\n{'Beat':<6}{'Class':<18}{'Confidence':<12}{'Alert'}")
    print("-" * 45)
    for i, beat in enumerate(beats):
        r = engine.predict(beat)
        alert = "YES" if r["alert"] else ""
        print(f"{i+1:<6}{r['class_name']:<18}{r['confidence']:<12.3f}{alert}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_model_inference.py <csv_path>")
        sys.exit(1)
    main(sys.argv[1])
