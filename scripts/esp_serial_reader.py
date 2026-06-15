import serial
import csv
import time
import os

SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE = 115200
OUTPUT_DIR = "raw/esp"

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(OUTPUT_DIR, f"ecg_{timestamp_str}.csv")

    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)  # ESP reset wait

    print(f"Recording to {filename}. Press Ctrl+C to stop.")

    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp_ms", "value", "lead_ok"])

        try:
            while True:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                parts = line.split(",")
                if len(parts) == 3:
                    try:
                        ts = int(parts[0])
                        val = int(parts[1])
                        lead_ok = int(parts[2])
                        writer.writerow([ts, val, lead_ok])
                        print(ts, val, lead_ok)
                    except ValueError:
                        continue
        except KeyboardInterrupt:
            print("\nStopped. File saved:", filename)
        finally:
            ser.close()

if __name__ == "__main__":
    main()