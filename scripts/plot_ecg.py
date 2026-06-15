import serial
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from collections import deque

SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE = 115200
WINDOW_SIZE = 250  # ~1 second window at 250Hz

ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)

data = deque([512] * WINDOW_SIZE, maxlen=WINDOW_SIZE)

fig, ax = plt.subplots()
line, = ax.plot(range(WINDOW_SIZE), data)
ax.set_ylim(0, 1024)
ax.set_title("Live ECG Signal (ESP8266 + AD8232)")
ax.set_xlabel("Sample")
ax.set_ylabel("Raw ADC Value")

def update(frame):
    raw_line = ser.readline().decode("utf-8", errors="ignore").strip()
    parts = raw_line.split(",")
    if len(parts) == 3:
        try:
            value = int(parts[1])
            lead_ok = int(parts[2])
            if lead_ok == 1:
                data.append(value)
            else:
                data.append(data[-1])  # leads off ??? last value repeat
        except ValueError:
            pass
    line.set_ydata(data)
    return line,

ani = animation.FuncAnimation(fig, update, interval=4, blit=True)
plt.show()