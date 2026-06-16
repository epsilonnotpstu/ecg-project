import collections
import numpy as np

class MotionArtifactDetector:
    """
    MPU6050 accelerometer data দিয়ে motion artifact detect করে।
    Rolling window-এ acceleration magnitude-এর STD threshold check করে।
    Rest: |a| ≈ 1g (gravity), std ≈ 0
    Motion: |a| fluctuates, std বাড়ে
    """

    def __init__(self, threshold=0.15, window=25):
        self.threshold = threshold  # g units
        self.window = window        # samples (~0.2s at 125Hz)
        self._buffer = collections.deque(maxlen=window)
        self._enabled = False

    def add_sample(self, ax100, ay100, az100):
        # ax100 = int(accel_g * 100)
        ax = ax100 / 100.0
        ay = ay100 / 100.0
        az = az100 / 100.0
        magnitude = float(np.sqrt(ax**2 + ay**2 + az**2))
        self._buffer.append(magnitude)
        self._enabled = True

    def is_motion(self):
        if not self._enabled or len(self._buffer) < 3:
            return False
        return float(np.std(list(self._buffer))) > self.threshold

    def motion_level(self):
        if not self._enabled or len(self._buffer) < 3:
            return 0.0
        std = float(np.std(list(self._buffer)))
        return min(1.0, std / (self.threshold * 3.0))

    def has_sensor(self):
        return self._enabled

    def reset(self):
        self._buffer.clear()
        self._enabled = False
