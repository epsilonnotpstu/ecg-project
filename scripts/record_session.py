import serial
import csv
import time
import os
import argparse

SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE = 115200
OUTPUT_DIR = "raw/esp"

def record(duration_sec, session_name="session"):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(OUTPUT_DIR, f"{session_name}_{timestamp_str}.csv")

    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)

    print(f"Recording {duration_sec} seconds -> {filename}")
    print("Stay still, breathe normally...")

    start_time = time.time()
    row_count = 0

    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp_ms", "value", "lead_ok"])

        while time.time() - start_time < duration_sec:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            parts = line.split(",")
            if len(parts) == 3:
                try:
                    ts = int(parts[0])
                    val = int(parts[1])
                    lead_ok = int(parts[2])
                    writer.writerow([ts, val, lead_ok])
                    row_count += 1
                except ValueError:
                    continue

    ser.close()
    elapsed = time.time() - start_time
    print(f"Done. {row_count} samples saved in {elapsed:.1f}s -> {filename}")
    return filename

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Record ECG session from ESP8266")
    parser.add_argument("--duration", type=int, default=15, help="Recording duration in seconds")
    parser.add_argument("--name", type=str, default="session", help="Session/patient name tag")
    args = parser.parse_args()
    record(args.duration, args.name)