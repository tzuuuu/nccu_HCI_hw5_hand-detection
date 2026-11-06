"""MediaPipe Tasks VIDEO pipeline; only Wrist (#0) selects a command."""

import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import mediapipe as mp

from interaction import DwellConfirmation, point_to_zone, zone_rectangles

MODEL_PATH = Path(__file__).parent / 'models' / 'hand_landmarker.task'
CONNECTIONS = ((0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7),
               (7, 8), (5, 9), (9, 10), (10, 11), (11, 12), (9, 13),
               (13, 14), (14, 15), (15, 16), (13, 17), (0, 17), (17, 18),
               (18, 19), (19, 20))


@dataclass
class HandSnapshot:
    frame_bgr: object
    annotated_bgr: object
    hand_detected: bool
    hand_count: int
    wrist: object
    detected_zone: object
    active_zone: object
    triggered_zone: object
    dwell_frames: int
    progress: float
    status: str
    timestamp: float
    fps: float


def create_landmarker(model_path=MODEL_PATH, confidence=0.5):
    if not 0 < confidence <= 1:
        raise ValueError('Confidence 必須介於 0（不含）與 1 之間')
    if not Path(model_path).is_file():
        raise FileNotFoundError('缺少手部模型，請先執行 python download_model.py')
    options = mp.tasks.vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path), delegate=mp.tasks.BaseOptions.Delegate.CPU),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_hands=2,
        min_hand_detection_confidence=confidence,
        min_hand_presence_confidence=confidence,
        min_tracking_confidence=confidence,
    )
    return mp.tasks.vision.HandLandmarker.create_from_options(options)


class CameraHandDetector:
    def __init__(self, camera_index=0, confidence=0.5, consecutive_frames=6,
                 cooldown_seconds=1.0, open_camera=True):
        if not 0 < confidence <= 1:
            raise ValueError('Confidence 必須介於 0（不含）與 1 之間')
        self.camera_index = camera_index
        self.confidence = confidence
        self.confirmation = DwellConfirmation(consecutive_frames, cooldown_seconds)
        self.landmarker = create_landmarker(confidence=confidence)
        self.capture = None
        self.timestamp_ms = -1
        self.previous_time = None
        self.fps = 0.0
        if open_camera:
            self.open()

    @property
    def consecutive_frames(self):
        return self.confirmation.consecutive_frames

    @property
    def cooldown_seconds(self):
        return self.confirmation.cooldown_seconds

    @property
    def is_open(self):
        return self.capture is not None and self.capture.isOpened()

    def configure(self, consecutive_frames=None, cooldown_seconds=None):
        self.confirmation.configure(consecutive_frames, cooldown_seconds)

    def reset_confirmation(self):
        self.confirmation.reset()

    def open(self):
        if self.capture is not None:
            self.capture.release()
        self.capture = cv2.VideoCapture(self.camera_index)
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.reset_confirmation()
        return self.is_open

    def read(self):
        if not self.is_open:
            self.confirmation.update(None, time.monotonic())
            return None
        ok, frame = self.capture.read()
        if not ok:
            self.confirmation.update(None, time.monotonic())
            return None
        return self.process_frame(frame)

    def process_frame(self, frame):
        # Mirror BEFORE inference, so normalized wrist and preview share axes.
        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        stamp = max(self.timestamp_ms + 1, int(time.monotonic() * 1000))
        self.timestamp_ms = stamp
        result = self.landmarker.detect_for_video(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), stamp)
        now = time.monotonic()
        if self.previous_time is not None:
            instantaneous = 1 / max(now - self.previous_time, 1e-6)
            self.fps = instantaneous if not self.fps else 0.9 * self.fps + 0.1 * instantaneous
        self.previous_time = now
        count = len(result.hand_landmarks)
        wrist = None
        zone = None
        # Reject two-hand ambiguity instead of allowing identities to switch.
        if count == 1:
            p = result.hand_landmarks[0][0]
            wrist = (p.x, p.y)
            zone = point_to_zone(*wrist)
        confirmed = self.confirmation.update(zone, now)
        status = 'Multiple hands: show one hand' if count > 1 else confirmed.status
        annotated = frame.copy()
        height, width = frame.shape[:2]
        for name, (x1, y1, x2, y2) in zone_rectangles(width, height).items():
            color = (0, 80, 255) if name == confirmed.triggered_zone else (60, 200, 60) if name == zone else (220, 130, 35)
            cv2.rectangle(annotated, (x1, y1), (x2 - 1, y2 - 1), color, 2)
            cv2.putText(annotated, name, (x1 + 8, y1 + 22), cv2.FONT_HERSHEY_SIMPLEX, .55, color, 2)
        for hand in result.hand_landmarks:
            points = [(int(p.x * (width - 1)), int(p.y * (height - 1))) for p in hand]
            for a, b in CONNECTIONS:
                cv2.line(annotated, points[a], points[b], (60, 220, 80), 2)
            for point in points:
                cv2.circle(annotated, point, 3, (255, 200, 0), -1)
            cv2.circle(annotated, points[0], 9, (0, 60, 255), 3)
            cv2.putText(annotated, 'WRIST #0', points[0], cv2.FONT_HERSHEY_SIMPLEX, .5, (0, 60, 255), 2)
        cv2.putText(annotated, status, (8, height - 10), cv2.FONT_HERSHEY_SIMPLEX, .45, (255, 255, 255), 1)
        return HandSnapshot(frame, annotated, count > 0, count, wrist, zone,
                            confirmed.active_zone, confirmed.triggered_zone,
                            confirmed.frames, confirmed.progress, status, now, self.fps)

    def release(self):
        if self.capture is not None:
            self.capture.release()
        self.landmarker.close()
