import serial
import csv
import time
import os
import argparse
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from motion_detector import MotionArtifactDetector

SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE = 115200
OUTPUT_DIR = "raw/esp"

def record(duration_sec, session_name="session"):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(OUTPUT_DIR, f"{session_name}_{timestamp_str}.csv")

    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2)
    except serial.SerialException as e:
        raise RuntimeError(f"Cannot open serial port {SERIAL_PORT}: {e}")

    time.sleep(2)
    motion = MotionArtifactDetector(threshold=0.15, window=25)

    print(f"Recording {duration_sec}s -> {filename}")
    print("Stay still, breathe normally...")

    start_time = time.time()
    row_count = 0
    motion_count = 0
    consecutive_errors = 0

    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp_ms", "value", "lead_ok",
                          "ax100", "ay100", "az100", "motion_flag"])

        while time.time() - start_time < duration_sec:
            try:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                consecutive_errors = 0
            except serial.SerialException as e:
                consecutive_errors += 1
                if consecutive_errors >= 5:
                    break
                time.sleep(0.1)
                continue

            if not line:
                continue

            parts = line.split(",")

            # MPU6050 ??: 6 columns
            # MPU6050 ?????: 3 columns (backward compatible)
            if len(parts) == 6:
                try:
                    ts     = int(parts[0])
                    val    = int(parts[1])
                    lok    = int(parts[2])
                    ax100  = int(parts[3])
                    ay100  = int(parts[4])
                    az100  = int(parts[5])
                    motion.add_sample(ax100, ay100, az100)
                    mflag  = 1 if motion.is_motion() else 0
                    if mflag:
                        motion_count += 1
                    writer.writerow([ts, val, lok, ax100, ay100, az100, mflag])
                    row_count += 1
                except ValueError:
                    continue

            elif len(parts) == 3:
                # MPU6050 ?? ?????? ??? ????
                try:
                    ts  = int(parts[0])
                    val = int(parts[1])
                    lok = int(parts[2])
                    writer.writerow([ts, val, lok, 0, 0, 100, 0])
                    row_count += 1
                except ValueError:
                    continue

    ser.close()
    elapsed = time.time() - start_time
    motion_pct = round(motion_count / max(row_count, 1) * 100, 1)
    print(f"Done. {row_count} samples, {motion_count} motion ({motion_pct}%) -> {filename}")

    if row_count < 100:
        raise RuntimeError(
            f"Only {row_count} samples collected. Check ESP8266 connection."
        )

    return filename, motion_pct

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=15)
    parser.add_argument("--name", type=str, default="session")
    args = parser.parse_args()
    filename, motion_pct = record(args.duration, args.name)
    print(f"Motion during recording: {motion_pct}%")
