"""HW5 application: retain the HW4 reader and replace recognition input."""

import argparse
import re
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

import cv2
from PIL import Image, ImageDraw, ImageTk

from hand_detection import CameraHandDetector, create_landmarker
from reader_ui import COMMANDS, COMMAND_LABELS, DocumentReaderUI

APP_DIR = Path(__file__).resolve().parent


class TouchlessReaderApp:
    def __init__(self, root, camera_index=0, confidence=0.5, no_camera=False):
        self.root = root
        self.root.title('Touchless Document Reader — HW5')
        self.root.geometry('1280x820')
        self.root.minsize(900, 640)
        self.experiment_window = None
        self.reader = DocumentReaderUI(root, on_state_change=self._refresh_experiment_state)
        self.detector = CameraHandDetector(camera_index, confidence, open_camera=not no_camera)
        self.last_snapshot = None
        self.last_frame_at = 0.0
        self.neutral_frames = 0
        self.snapshot_observers = []
        self.trigger_observers = []
        self.saved_trigger_zones = set()
        self.detector_settings_locked = False
        self.diagnostics = None
        self.after_id = None
        self._build_menu()
        self.open_diagnostics()
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.after_id = root.after(25, self._update_camera)

    def _build_menu(self):
        bar = tk.Menu(self.root)
        for label, entries in (
            ('File', [('Save Evidence Screenshot', lambda: self.capture_evidence('manual')), ('Quit', self.close)]),
            ('Camera', [('Camera Diagnostics', self.open_diagnostics), ('Retry Camera', self.retry_camera)]),
            ('Reader', [('Menu', lambda: self.reader.execute_command('menu', 'Toolbar')),
                        ('Settings', lambda: self.reader.execute_command('settings', 'Toolbar'))]),
            ('Experiment', [('Open Experiment Runner', self.open_experiment_runner)]),
        ):
            menu = tk.Menu(bar, tearoff=False)
            for title, callback in entries:
                menu.add_command(label=title, command=callback)
            bar.add_cascade(label=label, menu=menu)
        self.root.config(menu=bar)

    def open_diagnostics(self):
        if self.diagnostics is not None and self.diagnostics.winfo_exists():
            self.diagnostics.deiconify()
            self.diagnostics.lift()
            return
        window = self.diagnostics = tk.Toplevel(self.root)
        window.title('Hand / Wrist — HW5 Diagnostics')
        window.geometry('1120x680')
        container = ttk.Frame(window, padding=14)
        container.pack(fill='both', expand=True)
        ttk.Label(container, text='Hand Detection Diagnostics', font=('Arial', 18, 'bold')).pack(anchor='w')
        ttk.Label(container, text='僅伸出一隻手，以紅色 WRIST #0 對準操作區；停留完成後，離開原區域再操作。', wraplength=1000).pack(anchor='w', pady=8)
        row = ttk.Frame(container)
        row.pack(fill='both', expand=True)
        self.preview_labels = []
        for title in ('Mirrored Camera Input', 'Hand Landmarks / Wrist / Zones'):
            column = ttk.LabelFrame(row, text=title)
            column.pack(side='left', fill='both', expand=True, padx=4)
            label = ttk.Label(column, text='Waiting for camera…', anchor='center')
            label.pack(fill='both', expand=True)
            self.preview_labels.append(label)
        self.camera_status_var = tk.StringVar(value='Camera starting…')
        ttk.Label(container, textvariable=self.camera_status_var, wraplength=1050).pack(anchor='w', pady=10)
        controls = ttk.Frame(container)
        controls.pack(fill='x')
        self.consecutive_value = tk.IntVar(value=self.detector.consecutive_frames)
        self.cooldown_value = tk.DoubleVar(value=self.detector.cooldown_seconds)
        self.setting_widgets = []
        for label, var, low, high, increment in (
            ('Dwell (frames)', self.consecutive_value, 1, 120, 1),
            ('Cooldown (seconds)', self.cooldown_value, 0, 10, .1),
        ):
            ttk.Label(controls, text=label).pack(side='left', padx=6)
            box = ttk.Spinbox(controls, textvariable=var, from_=low, to=high, increment=increment, width=6, command=self._change_settings)
            box.pack(side='left')
            box.bind('<FocusOut>', self._change_settings)
            box.bind('<Return>', self._change_settings)
            self.setting_widgets.append(box)
        ttk.Label(controls, text='Detection / Presence / Tracking confidence: {:.2f} (fixed)'.format(self.detector.confidence)).pack(side='left', padx=14)
        actions = ttk.Frame(container)
        actions.pack(fill='x', pady=14)
        for title, callback in [('Retry Camera', self.retry_camera), ('Save Evidence Screenshot', lambda: self.capture_evidence('manual')), ('Open Experiment Runner', self.open_experiment_runner)]:
            ttk.Button(actions, text=title, command=callback).pack(side='left', padx=4)
        window.protocol('WM_DELETE_WINDOW', window.withdraw)

    def _change_settings(self, _event=None):
        if not self.detector_settings_locked:
            try:
                self.detector.configure(self.consecutive_value.get(), self.cooldown_value.get())
            except (ValueError, tk.TclError):
                pass
        self.consecutive_value.set(self.detector.consecutive_frames)
        self.cooldown_value.set(self.detector.cooldown_seconds)

    def lock_settings(self, locked):
        self.detector_settings_locked = locked
        for widget in self.setting_widgets:
            widget.configure(state='disabled' if locked else 'normal')

    def apply_dwell(self, k):
        self.detector.configure(consecutive_frames=k)
        self.consecutive_value.set(k)

    def retry_camera(self):
        if self.experiment_window and self.experiment_window.active_trial:
            messagebox.showinfo('試驗進行中', '請先停止流程再重新連接攝影機。', parent=self.root)
            return
        self.last_snapshot = None
        self.neutral_frames = 0
        opened = self.detector.open()
        self.reader.set_camera_status('Camera connected' if opened else 'Camera unavailable')

    @property
    def camera_ready(self):
        return self.detector.is_open and self.last_snapshot is not None and time.monotonic() - self.last_frame_at < 0.5

    def _update_camera(self):
        self.after_id = None
        try:
            snapshot = self.detector.read()
        except Exception as error:
            # Do not silently turn an inference/runtime error into a detection failure.
            if self.experiment_window:
                self.experiment_window.stop_session()
            self.camera_status_var.set('辨識錯誤：{}；請重新啟動程式。'.format(error))
            self.reader.set_camera_status('Detector error')
            return
        if snapshot is None:
            self.neutral_frames = 0
            self.last_snapshot = None
            self.reader.set_hand_feedback(None, self.detector.consecutive_frames)
            status = 'Camera unavailable / no frame — check permission or Retry Camera'
            self.reader.set_camera_status(status)
            self.camera_status_var.set(status)
            if self.experiment_window:
                self.experiment_window.on_camera_unavailable()
        else:
            self.last_snapshot = snapshot
            self.last_frame_at = snapshot.timestamp
            self.neutral_frames = self.neutral_frames + 1 if not snapshot.hand_detected else 0
            self.reader.set_hand_feedback(snapshot, self.detector.consecutive_frames)
            self.reader.set_camera_status(snapshot.status)
            # Capture eligibility before observers advance or finish a trial.
            apply = self.experiment_window is None or self.experiment_window.should_apply_reader_command()
            for observer in list(self.snapshot_observers):
                observer(snapshot)
            if snapshot.triggered_zone:
                if apply:
                    self.reader.execute_command(COMMANDS[snapshot.triggered_zone])
                for observer in list(self.trigger_observers):
                    observer(snapshot.triggered_zone, snapshot.timestamp)
                if apply and snapshot.triggered_zone not in self.saved_trigger_zones:
                    self.saved_trigger_zones.add(snapshot.triggered_zone)
                    self.capture_evidence('trigger-' + snapshot.triggered_zone)
            wrist = 'none' if snapshot.wrist is None else '({:.3f}, {:.3f})'.format(*snapshot.wrist)
            self.camera_status_var.set('{} | hands {} | wrist {} | zone {} | K {} | {:.1f} FPS'.format(
                snapshot.status, snapshot.hand_count, wrist, snapshot.detected_zone or '-', self.detector.consecutive_frames, snapshot.fps))
            if self.diagnostics.state() != 'withdrawn':
                self.preview_photos = []
                for label, frame in zip(self.preview_labels, (snapshot.frame_bgr, snapshot.annotated_bgr)):
                    image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    image.thumbnail((510, 390))
                    photo = ImageTk.PhotoImage(image)
                    label.configure(image=photo, text='')
                    self.preview_photos.append(photo)
        self.after_id = self.root.after(25, self._update_camera)

    def capture_evidence(self, name, title='HW5 Hand Detection / Wrist #0'):
        self.reader._render()
        image = self.reader._last_rendered_image.copy()
        width, height = image.size
        panel_width = (width - 48) // 2
        panel_height = int(panel_width * .75)
        output = Image.new('RGB', (width, height + panel_height + 72), '#f8fafc')
        output.paste(image, (0, 0))
        draw = ImageDraw.Draw(output)
        draw.text((16, height + 8), title, font=self.reader._font(17), fill='#1e293b')
        if self.last_snapshot:
            for i, frame in enumerate((self.last_snapshot.frame_bgr, self.last_snapshot.annotated_bgr)):
                preview = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                preview.thumbnail((panel_width, panel_height))
                x = 16 + i * (panel_width + 16)
                draw.text((x, height + 32), ('Mirrored camera', 'Landmarks / Wrist #0 / Zones')[i], font=self.reader._font(15), fill='#334155')
                output.paste(preview, (x, height + 56))
        directory = APP_DIR / 'screenshots'
        directory.mkdir(exist_ok=True)
        name = re.sub(r'[^A-Za-z0-9_-]+', '-', name)
        path = directory / '{}-{}.png'.format(name, datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        output.save(path)
        return path

    def add_trigger_observer(self, callback):
        self.trigger_observers.append(callback)

    def add_snapshot_observer(self, callback):
        self.snapshot_observers.append(callback)

    def remove_trigger_observer(self, callback):
        self.trigger_observers.remove(callback)

    def remove_snapshot_observer(self, callback):
        self.snapshot_observers.remove(callback)

    def open_experiment_runner(self):
        from experiment_runner import ExperimentRunnerWindow
        if self.experiment_window:
            self.experiment_window.window.deiconify()
            self.experiment_window.window.lift()
        else:
            self.experiment_window = ExperimentRunnerWindow(self)

    def _refresh_experiment_state(self):
        if self.experiment_window:
            self.experiment_window.refresh_state()

    def close(self):
        if self.after_id:
            self.root.after_cancel(self.after_id)
        if self.experiment_window:
            self.experiment_window.close()
        self.detector.release()
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description='HW5 hand-based touchless document reader')
    parser.add_argument('--camera', type=int, default=0)
    parser.add_argument('--confidence', type=float, default=.5)
    parser.add_argument('--no-camera', action='store_true', help='Preview UI without opening webcam')
    parser.add_argument('--check-runtime', action='store_true', help='Check model/inference without GUI or camera')
    args = parser.parse_args()
    if args.check_runtime:
        import numpy as np
        with create_landmarker(confidence=args.confidence) as detector:
            result = detector.detect_for_video(mp_image(np.zeros((480, 640, 3), dtype=np.uint8)), 0)
            print('Runtime OK; blank-frame hands:', len(result.hand_landmarks))
        return
    root = tk.Tk()
    try:
        TouchlessReaderApp(root, args.camera, args.confidence, args.no_camera)
    except Exception as error:
        messagebox.showerror('無法啟動', str(error), parent=root)
        root.destroy()
        raise SystemExit(1)
    root.mainloop()


def mp_image(rgb):
    import mediapipe as mp
    return mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)


if __name__ == '__main__':
    main()
