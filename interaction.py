"""Camera-independent zone geometry and consecutive-frame confirmation."""

import math
from dataclasses import dataclass
from typing import Optional

ZONE_ORDER = ('Z1', 'Z2', 'Z3', 'Z4', 'Z5', 'Z6')


def zone_rectangles(width, height):
    split = int(height * 0.78)
    return {'Z1': (0, 0, width // 2, split),
            'Z2': (width // 2, 0, width, split),
            **{zone: (int(i * width / 4), split, int((i + 1) * width / 4), height)
               for i, zone in enumerate(ZONE_ORDER[2:])}}


def point_to_zone(x, y):
    """Normalized coordinates; half-open boundaries prevent overlapping zones."""
    if not (math.isfinite(x) and math.isfinite(y) and 0 <= x <= 1 and 0 <= y <= 1):
        return None
    if y < 0.78:
        return 'Z1' if x < 0.5 else 'Z2'
    return ZONE_ORDER[2 + min(3, int(x * 4))]


@dataclass(frozen=True)
class Confirmation:
    active_zone: Optional[str]
    triggered_zone: Optional[str]
    frames: int
    progress: float
    status: str


class DwellConfirmation:
    """Require K uninterrupted processed frames, cooldown, and exit to re-arm."""

    def __init__(self, consecutive_frames=6, cooldown_seconds=1.0):
        self.configure(consecutive_frames, cooldown_seconds)

    def configure(self, consecutive_frames=None, cooldown_seconds=None):
        k = self.consecutive_frames if consecutive_frames is None else consecutive_frames
        cooldown = self.cooldown_seconds if cooldown_seconds is None else cooldown_seconds
        if isinstance(k, bool) or int(k) != k or not 1 <= k <= 120:
            raise ValueError('連續影格數必須是 1–120 的整數')
        if not math.isfinite(cooldown) or not 0 <= cooldown <= 10:
            raise ValueError('冷卻時間必須介於 0–10 秒')
        self.consecutive_frames = int(k)
        self.cooldown_seconds = float(cooldown)
        self.reset()

    def reset(self):
        self.active_zone = None
        self.frames = 0
        self.latched_zone = None
        self.cooldown_until = 0.0
        self.last_time = None

    def update(self, zone, now):
        # A long acquisition gap also breaks consecutiveness.
        if self.last_time is not None and now - self.last_time > 0.5:
            self.active_zone, self.frames = None, 0
        self.last_time = now
        if zone != self.latched_zone:
            self.latched_zone = None
        if zone is None:
            self.active_zone, self.frames = None, 0
            return Confirmation(None, None, 0, 0.0, 'No hand / no valid wrist')
        if now < self.cooldown_until or zone == self.latched_zone:
            self.active_zone, self.frames = zone, 0
            status = 'Cooldown' if now < self.cooldown_until else 'Move wrist out to re-arm'
            return Confirmation(zone, None, 0, 0.0, status)
        self.frames = self.frames + 1 if zone == self.active_zone else 1
        self.active_zone = zone
        progress = min(1.0, self.frames / self.consecutive_frames)
        if self.frames >= self.consecutive_frames:
            self.cooldown_until = now + self.cooldown_seconds
            self.latched_zone = zone
            return Confirmation(zone, zone, self.frames, 1.0, 'Triggered ' + zone)
        return Confirmation(zone, None, self.frames, progress, 'Dwell {}/{}'.format(self.frames, self.consecutive_frames))
