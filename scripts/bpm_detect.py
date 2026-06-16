import pandas as pd
import numpy as np
from scipy.signal import find_peaks
import matplotlib
matplotlib.use("Agg")   # non-interactive backend — fixes tkinter crash in Flask thread
import matplotlib.pyplot as plt
import os
import sys
import json

FS = 125  # ESP8266 now runs at 125Hz (delay 8ms, with MPU6050)

def detect_peaks(signal, fs=FS, max_bpm=180):
    sig = signal - np.mean(signal)
    min_distance = int((60 / max_bpm) * fs)
    threshold = np.std(sig) * 1.5
    peaks, _ = find_peaks(sig, height=threshold, distance=min_distance)
    return peaks, sig

def calculate_bpm(peaks, fs=FS):
    if len(peaks) < 2:
        return None, None
    rr_intervals = np.diff(peaks) / fs
    bpm = 60 / np.mean(rr_intervals)
    return bpm, rr_intervals

def classify_bpm(bpm):
    if bpm is None:
        return "Unknown - insufficient peaks"
    if bpm < 60:
        return "Bradycardia (below normal)"
    elif bpm > 100:
        return "Tachycardia (above normal)"
    else:
        return "Normal range"

def analyze_file(filtered_csv_path):
    df = pd.read_csv(filtered_csv_path)
    signal = df["value"].values.astype(float)

    peaks, sig = detect_peaks(signal)
    bpm, rr_intervals = calculate_bpm(peaks)

    plot_path = filtered_csv_path.replace(".csv", "_bpm.png")

    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(sig, linewidth=0.8)
    if len(peaks) > 0:
        ax.plot(peaks, sig[peaks], "rx", markersize=8)

    title = f"R-peaks: {len(peaks)}"
    if bpm:
        title += f" | BPM: {bpm:.1f} | {classify_bpm(bpm)}"
    ax.set_title(title)
    ax.set_xlabel("Sample")
    plt.tight_layout()
    plt.savefig(plot_path)
    plt.close("all")   # close ALL figures — prevents tkinter resource leak

    result = {
        "file": filtered_csv_path,
        "num_peaks": int(len(peaks)),
        "bpm": round(bpm, 1) if bpm else None,
        "status": classify_bpm(bpm),
        "rr_intervals_sec": [round(x, 3) for x in rr_intervals] if rr_intervals is not None else [],
        "plot": plot_path
    }
    return result

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python bpm_detect.py <filtered_csv_path>")
        sys.exit(1)
    result = analyze_file(sys.argv[1])
    print(json.dumps(result, indent=2))