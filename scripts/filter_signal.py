import pandas as pd
import numpy as np
from scipy.signal import butter, filtfilt, iirnotch
import matplotlib
matplotlib.use("Agg")   # non-interactive backend — fixes tkinter crash in Flask thread
import matplotlib.pyplot as plt
import os
import sys

FS = 125          # ESP8266 now runs at 125Hz (delay 8ms, with MPU6050)
NOTCH_FREQ = 50.0
NOTCH_Q = 30.0

def notch_filter(signal, fs=FS, freq=NOTCH_FREQ, Q=NOTCH_Q):
    b, a = iirnotch(freq / (fs / 2), Q)
    return filtfilt(b, a, signal)

def bandpass_filter(signal, fs=FS, lowcut=0.5, highcut=40, order=2):
    nyq = fs / 2
    b, a = butter(order, [lowcut / nyq, highcut / nyq], btype="band")
    return filtfilt(b, a, signal)

def process_file(csv_path):
    df = pd.read_csv(csv_path)
    df = df[df["lead_ok"] == 1].reset_index(drop=True)

    if len(df) < FS:
        print("Warning: very little usable data (lead-off most of the time).")

    raw = df["value"].values.astype(float)

    step1 = notch_filter(raw)
    filtered = bandpass_filter(step1)

    base_name = os.path.splitext(os.path.basename(csv_path))[0]

    plot_path = os.path.join("raw", "esp", f"{base_name}_compare.png")
    fig, axs = plt.subplots(2, 1, figsize=(12, 6))
    axs[0].plot(raw, color="gray", linewidth=0.8)
    axs[0].set_title("Raw Signal")
    axs[1].plot(filtered, color="blue", linewidth=0.8)
    axs[1].set_title("Filtered Signal (50Hz notch + 0.5-40Hz bandpass)")
    axs[1].set_xlabel("Sample")
    plt.tight_layout()
    plt.savefig(plot_path)
    plt.close("all")   # close ALL figures — prevents tkinter resource leak
    print("Comparison plot saved:", plot_path)

    out_dir = os.path.join("filtered", "esp")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{base_name}_filtered.csv")
    pd.DataFrame({"value": filtered}).to_csv(out_path, index=False)
    print("Filtered CSV saved:", out_path)

    return out_path, plot_path

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python filter_signal.py <path_to_raw_csv>")
        sys.exit(1)
    process_file(sys.argv[1])