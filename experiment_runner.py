"""HW5 trial schedules, observable outcomes, and the adapted HW4 experiment UI."""

import csv
import random
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from reader_ui import COMMANDS, COMMAND_LABELS

APP_DIR = Path(__file__).resolve().parent
TRIAL_COLUMNS = (
    'session_id', 'trial_id', 'experiment', 'condition', 'lighting', 'dwell_level',
    'dwell_frames', 'cooldown_seconds', 'detection_confidence', 'presence_confidence',
    'tracking_confidence', 'detector', 'mediapipe_version', 'model_sha256',
    'target_zone', 'target_command', 'hand_detected', 'detected_zone',
    'triggered_zone', 'triggered_command', 'correct', 'trigger_time_ms',
    'false_trigger', 'missed_trigger', 'detection_failure', 'total_frames',
    'no_hand_frames', 'multi_hand_frames', 'tracking_loss_count', 'mean_fps',
    'wrist_x', 'wrist_y', 'repetition', 'timeout_seconds', 'notes', 'started_at', 'completed_at',
)


def timestamp():
    return datetime.now().astimezone().isoformat(timespec='milliseconds')


@dataclass
class Trial:
    number: int
    experiment_id: str
    target_zone: str
    lighting: str
    dwell_level: str
    dwell_frames: int
    repetition: int

    @property
    def trial_id(self):
        return '{}-{:03d}'.format(self.experiment_id.replace('experiment', 'E'), self.number)

    @property
    def target_command(self):
        return COMMANDS[self.target_zone]


def validate_dwell(value):
    if isinstance(value, bool) or int(value) != value or not 1 <= value <= 120:
        raise ValueError('K 必須是 1–120 的整數')
    return int(value)


def build_trial_schedule(experiment_id, baseline_dwell=6, dwell_levels=None):
    baseline_dwell = validate_dwell(baseline_dwell)
    levels = dwell_levels or {'Short': 3, 'Medium': 6, 'Long': 10}
    if set(levels) != {'Short', 'Medium', 'Long'}:
        raise ValueError('必須設定 Short、Medium、Long')
    levels = {key: validate_dwell(value) for key, value in levels.items()}
    if not levels['Short'] < levels['Medium'] < levels['Long']:
        raise ValueError('必須符合 Short < Medium < Long')
    trials = []
    if experiment_id == 'experiment1':
        conditions = [('Normal Lighting', 'Baseline', baseline_dwell, list(COMMANDS), 5)]
    elif experiment_id == 'experiment2':
        conditions = [('Normal Lighting', name, levels[name], ['Z1', 'Z2', 'Z3'], 3) for name in ('Short', 'Medium', 'Long')]
    elif experiment_id == 'experiment3':
        lighting = ['Normal Lighting', 'Dim Lighting']
        random.shuffle(lighting)
        conditions = [(light, 'Baseline', baseline_dwell, ['Z1', 'Z2', 'Z3'], 3) for light in lighting]
    else:
        raise ValueError('未知實驗')
    for light, level, k, zones, repetitions in conditions:
        block = [Trial(0, experiment_id, zone, light, level, k, repeat)
                 for zone in zones for repeat in range(1, repetitions + 1)]
        random.shuffle(block)
        trials.extend(block)
    if experiment_id == 'experiment2':
        random.shuffle(trials)
    for number, trial in enumerate(trials, 1):
        trial.number = number
    return trials


@dataclass
class TrialObservation:
    total_frames: int = 0
    no_hand_frames: int = 0
    multi_hand_frames: int = 0
    tracking_loss_count: int = 0
    hand_detected: bool = False
    detected_zone: str = ''
    wrist: object = None
    fps_values: list = field(default_factory=list)
    previous_detected: bool = False

    def observe(self, snapshot):
        self.total_frames += 1
        self.no_hand_frames += int(not snapshot.hand_detected)
        self.multi_hand_frames += int(snapshot.hand_count > 1)
        self.tracking_loss_count += int(self.previous_detected and not snapshot.hand_detected)
        self.previous_detected = snapshot.hand_detected
        self.hand_detected |= snapshot.hand_detected
        self.detected_zone = snapshot.detected_zone or ''
        self.wrist = snapshot.wrist
        if snapshot.fps > 0:
            self.fps_values.append(snapshot.fps)

    def outcome(self, target_zone, triggered_zone, elapsed_ms):
        missed = triggered_zone is None
        return {
            'hand_detected': self.hand_detected,
            'detected_zone': self.detected_zone,
            'triggered_zone': triggered_zone or '',
            'triggered_command': COMMAND_LABELS[COMMANDS[triggered_zone]] if triggered_zone else '',
            'correct': triggered_zone == target_zone,
            'trigger_time_ms': '' if missed else round(elapsed_ms, 1),
            'false_trigger': bool(triggered_zone and triggered_zone != target_zone),
            'missed_trigger': missed,
            # Operational definition: timeout with no detected hand on any valid frame.
            'detection_failure': missed and not self.hand_detected,
            'total_frames': self.total_frames,
            'no_hand_frames': self.no_hand_frames,
            'multi_hand_frames': self.multi_hand_frames,
            'tracking_loss_count': self.tracking_loss_count,
            'mean_fps': round(sum(self.fps_values) / len(self.fps_values), 2) if self.fps_values else '',
            'wrist_x': self.wrist[0] if self.wrist else '',
            'wrist_y': self.wrist[1] if self.wrist else '',
        }


class ExperimentRecorder:
    def __init__(self, base_dir=APP_DIR):
        self.base_dir = Path(base_dir)
        self.path = None

    def start(self, name):
        directory = self.base_dir / ('pilot-data' if name == 'pilot' else 'results')
        directory.mkdir(parents=True, exist_ok=True)
        self.session_id = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        self.path = directory / '{}_{}.csv'.format(name, self.session_id)
        return self.path

    def record(self, row):
        exists = self.path.exists()
        with self.path.open('a', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=TRIAL_COLUMNS)
            if not exists:
                writer.writeheader()
            writer.writerow({key: str(value).lower() if isinstance(value, bool) else value for key, value in row.items()})


class ExperimentRunnerWindow:
    EXPERIMENT_CHOICES = (('Pilot（不計入正式試驗）', 'pilot'),
                          ('Experiment 1 — Basic Accuracy (30)', 'experiment1'),
                          ('Experiment 2 — Dwell Settings (27)', 'experiment2'),
                          ('Experiment 3 — Lighting (18)', 'experiment3'))

    def __init__(self, app):
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title('HW5 Experiment Runner')
        self.window.geometry('1000x700')
        self.window.minsize(950, 650)
        self.recorder = ExperimentRecorder()
        self.active_experiment_id = None
        self.active_trial = None
        self.trials = []
        self.pilot_active = False
        self.timeout_after_id = None
        self.baseline = app.detector.consecutive_frames
        self.prepared_lighting = None
        self.counts = Counter()
        self.selection_var = tk.StringVar(value=self.EXPERIMENT_CHOICES[0][0])
        self.timeout_value = tk.IntVar(value=8)
        self.dwell_vars = {name: tk.StringVar(value=str(k)) for name, k in [('Short', 3), ('Medium', 6), ('Long', 10)]}
        self.trial_var = tk.StringVar(value='尚未開始')
        self.condition_var = tk.StringVar(value='')
        self.progress_var = tk.StringVar(value='')
        self.status_var = tk.StringVar(value='先在正常光線進行 Pilot，檢查手腕位置、處理 FPS 與適合的 K。')
        self.output_var = tk.StringVar(value='')
        self.notes_var = tk.StringVar()
        self._build_ui()
        self.app.add_snapshot_observer(self._on_snapshot)
        self.app.add_trigger_observer(self._on_trigger)
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh_state()

    def _build_ui(self):
        frame = ttk.Frame(self.window, padding=16)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='HW5 Experiment Runner', font=('Arial', 19, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='每次試驗：移出手部 → 確認光線 → 開始計時 → 手腕移入目標區停留；第一個觸發或逾時即記錄。', wraplength=950).pack(anchor='w', pady=10)
        row = ttk.Frame(frame)
        row.pack(fill='x')
        self.selection_box = ttk.Combobox(row, textvariable=self.selection_var, values=[x[0] for x in self.EXPERIMENT_CHOICES], state='readonly', width=43)
        self.selection_box.pack(side='left')
        self.begin_button = ttk.Button(row, text='開始流程 / Pilot', command=self.start_selected)
        self.begin_button.pack(side='left', padx=8)
        ttk.Label(row, text='逾時（秒）').pack(side='left')
        self.timeout_box = ttk.Spinbox(row, from_=3, to=30, textvariable=self.timeout_value, width=5)
        self.timeout_box.pack(side='left')
        box = ttk.LabelFrame(frame, text='Experiment 2：連續影格確認（依 Pilot 微調，正式流程開始後鎖定）', padding=12)
        box.pack(fill='x', pady=16)
        self.entries = []
        for name, variable in self.dwell_vars.items():
            ttk.Label(box, text=name + ' K =').pack(side='left', padx=4)
            entry = ttk.Entry(box, textvariable=variable, width=6)
            entry.pack(side='left', padx=(0, 20))
            self.entries.append(entry)
        ttk.Label(frame, text='正式實驗固定 detector、confidence、cooldown；實驗一與三固定目前 K。實驗二只改變 K。', wraplength=930).pack(anchor='w')
        box = ttk.LabelFrame(frame, text='目前試驗', padding=14)
        box.pack(fill='x', pady=16)
        ttk.Label(box, textvariable=self.trial_var, font=('Arial', 16, 'bold')).pack(anchor='w')
        ttk.Label(box, textvariable=self.condition_var).pack(anchor='w', pady=8)
        ttk.Label(box, text='備註（操作前填寫，會隨此筆保存）').pack(anchor='w')
        ttk.Entry(box, textvariable=self.notes_var).pack(fill='x', pady=4)
        actions = ttk.Frame(frame)
        actions.pack(fill='x')
        self.prepare_button = ttk.Button(actions, text='已調整為指定光線', command=self.prepare_condition)
        self.prepare_button.pack(side='left')
        self.trial_button = ttk.Button(actions, text='我已準備好，開始計時', command=self.start_trial)
        self.trial_button.pack(side='left', padx=8)
        self.stop_button = ttk.Button(actions, text='停止流程 / Pilot', command=self.stop_session)
        self.stop_button.pack(side='left')
        for variable in (self.progress_var, self.status_var, self.output_var):
            ttk.Label(frame, textvariable=variable, wraplength=940, justify='left').pack(anchor='w', pady=(12, 0))

    def start_selected(self):
        if self.active_experiment_id or self.pilot_active:
            return
        if not self.app.camera_ready:
            self.status_var.set('尚未取得有效攝影機畫面，請先連接攝影機。')
            return
        code = dict(self.EXPERIMENT_CHOICES)[self.selection_var.get()]
        try:
            self.session_timeout = self.timeout_value.get()
            if not 3 <= self.session_timeout <= 30:
                raise ValueError('逾時必須介於 3–30 秒')
            levels = {name: int(var.get()) for name, var in self.dwell_vars.items()}
            self.baseline = self.app.detector.consecutive_frames
            self.trials = [] if code == 'pilot' else build_trial_schedule(code, self.baseline, levels)
        except (ValueError, tk.TclError) as error:
            messagebox.showwarning('設定無效', str(error), parent=self.window)
            return
        import hashlib
        import mediapipe as mp
        from hand_detection import MODEL_PATH
        self.metadata = dict(
            detector='MediaPipe HandLandmarker VIDEO / Wrist #0',
            mediapipe_version=mp.__version__, model_sha256=hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest(),
            detection_confidence=self.app.detector.confidence,
            presence_confidence=self.app.detector.confidence,
            tracking_confidence=self.app.detector.confidence,
            cooldown_seconds=self.app.detector.cooldown_seconds,
        )
        self.output_var.set('記錄檔：' + str(self.recorder.start(code)))
        self.counts = Counter()
        self.pilot_active = code == 'pilot'
        self.active_experiment_id = None if self.pilot_active else code
        self.prepared_lighting = None if code == 'experiment3' else 'Normal Lighting'
        self.app.lock_settings(not self.pilot_active)
        self._show_pending_trial()
        self.refresh_state()

    def _show_pending_trial(self):
        if not self.trials:
            self.trial_var.set('Pilot：可調整診斷視窗的 K，逐次檢查操作穩定性。' if self.pilot_active else '流程已結束')
            return
        trial = self.trials[0]
        self.app.apply_dwell(trial.dwell_frames)
        self.trial_var.set('{} / 目標 {} — {}'.format(trial.trial_id, trial.target_zone, COMMAND_LABELS[trial.target_command]))
        self.condition_var.set('{} | {} K={} | 第 {} 次重複'.format(trial.lighting, trial.dwell_level, trial.dwell_frames, trial.repetition))
        self.status_var.set('請依指定條件調整光線，將手移出畫面至少 3 個影格，再開始計時。')
        self.notes_var.set('')

    def prepare_condition(self):
        if self.trials and self.active_trial is None:
            self.prepared_lighting = self.trials[0].lighting
            self.status_var.set('已確認 {}；請將手移出畫面後開始。'.format(self.prepared_lighting))
            self.app.capture_evidence('lighting-' + self.prepared_lighting.lower().replace(' ', '-'), self.prepared_lighting)
            self.refresh_state()

    def start_trial(self):
        if not self.trials or self.active_trial or not self.app.camera_ready or self.app.neutral_frames < 3:
            return
        trial = self.trials[0]
        if self.prepared_lighting != trial.lighting:
            return
        # Keep boundary commands visibly executable; preparation is outside timing.
        reader = self.app.reader
        reader.page_index = min(1, reader.page_count - 1)
        reader.zoom = 100
        reader.menu_state = None
        reader._menu_hitboxes = []
        reader._schedule_render()
        self.active_trial = self.trials.pop(0)
        self.app.detector.reset_confirmation()
        self.observation = TrialObservation()
        self.trial_started_at = time.monotonic()
        self.trial_started_label = timestamp()
        self.trial_notes = self.notes_var.get()
        self.status_var.set('計時中：將手腕移入 {}，連續停留 {} 個影格。'.format(trial.target_zone, trial.dwell_frames))
        self.timeout_after_id = self.window.after(self.session_timeout * 1000, self._timeout_trial)
        self.refresh_state()

    def _on_snapshot(self, snapshot):
        if self.active_trial:
            # A frame arriving after the deadline cannot win over the timeout callback.
            if snapshot.timestamp - self.trial_started_at >= self.session_timeout:
                self._complete_trial(None, None)
            else:
                self.observation.observe(snapshot)
        self.refresh_state()

    def _on_trigger(self, zone, trigger_time):
        if self.active_trial:
            self._complete_trial(zone, (trigger_time - self.trial_started_at) * 1000)
        elif self.pilot_active:
            snap = self.app.last_snapshot
            row = {**self.metadata, 'session_id': self.recorder.session_id,
                   'experiment': 'pilot', 'trial_id': 'P-{:03d}'.format(self.counts['pilot'] + 1),
                   'lighting': 'Normal Lighting', 'dwell_frames': self.app.detector.consecutive_frames,
                   'triggered_zone': zone, 'triggered_command': COMMAND_LABELS[COMMANDS[zone]],
                   'hand_detected': True, 'detected_zone': snap.detected_zone,
                   'wrist_x': snap.wrist[0], 'wrist_y': snap.wrist[1], 'mean_fps': round(snap.fps, 2),
                   'completed_at': timestamp(), 'notes': self.notes_var.get()}
            self.recorder.record(row)
            self.counts['pilot'] += 1
            self.status_var.set('Pilot 已保存 {} 次觸發；K={}，處理速率 {:.1f} FPS。'.format(self.counts['pilot'], self.app.detector.consecutive_frames, snap.fps))

    def should_apply_reader_command(self):
        return self.active_experiment_id is None or (self.active_trial is not None and time.monotonic() - self.trial_started_at < self.session_timeout)

    def _timeout_trial(self):
        self.timeout_after_id = None
        if self.active_trial:
            self._complete_trial(None, None)

    def _complete_trial(self, zone, elapsed_ms):
        trial = self.active_trial
        if trial is None:
            return
        if self.timeout_after_id:
            self.window.after_cancel(self.timeout_after_id)
            self.timeout_after_id = None
        outcome = self.observation.outcome(trial.target_zone, zone, elapsed_ms)
        self.recorder.record({**self.metadata, **outcome, 'session_id': self.recorder.session_id,
            'trial_id': trial.trial_id, 'experiment': trial.experiment_id,
            'condition': trial.dwell_level if trial.experiment_id == 'experiment2' else trial.lighting,
            'lighting': trial.lighting, 'dwell_level': trial.dwell_level, 'dwell_frames': trial.dwell_frames,
            'target_zone': trial.target_zone, 'target_command': COMMAND_LABELS[trial.target_command],
            'repetition': trial.repetition, 'timeout_seconds': self.session_timeout,
            'notes': self.trial_notes, 'started_at': self.trial_started_label, 'completed_at': timestamp()})
        for key in ('correct', 'false_trigger', 'missed_trigger', 'detection_failure'):
            self.counts[key] += int(outcome[key])
        self.counts['completed'] += 1
        if not outcome['correct']:
            self.app.capture_evidence('error-' + trial.trial_id, 'Target {} / Trigger {} / No detection {}'.format(trial.target_zone, zone or '-', outcome['detection_failure']))
        self.active_trial = None
        self.progress_var.set('已保存 {} 次 | 正確 {} | 誤觸 {} | 逾時 {} | 全程未偵測 {}\n最近：{} → {}'.format(
            self.counts['completed'], self.counts['correct'], self.counts['false_trigger'], self.counts['missed_trigger'], self.counts['detection_failure'], trial.target_zone, zone or 'timeout'))
        if not self.trials:
            self.stop_session(finished=True)
        else:
            self._show_pending_trial()
        self.refresh_state()

    def on_camera_unavailable(self):
        if self.active_experiment_id or self.pilot_active:
            self.stop_session()
            self.status_var.set('攝影機影像中斷，流程已停止；本筆未完成試驗不計分，已保存資料保留。請恢復攝影機後重新開始此實驗。')
        self.refresh_state()

    def stop_session(self, finished=False):
        if self.timeout_after_id:
            self.window.after_cancel(self.timeout_after_id)
            self.timeout_after_id = None
        was_active = self.active_experiment_id is not None or self.pilot_active
        self.active_trial = None
        self.trials = []
        self.active_experiment_id = None
        self.pilot_active = False
        if was_active:
            self.app.apply_dwell(self.baseline)
            self.app.lock_settings(False)
            self.status_var.set('流程完成，所有實際試驗已保存。' if finished else '流程已停止；未完成的試驗未記錄，已完成的 CSV 保留。')
        self.refresh_state()

    def refresh_state(self):
        active = self.active_experiment_id is not None or self.pilot_active
        self.selection_box.configure(state='disabled' if active else 'readonly')
        self.begin_button.configure(state='disabled' if active else 'normal')
        self.timeout_box.configure(state='disabled' if active else 'normal')
        for entry in self.entries:
            entry.configure(state='disabled' if active else 'normal')
        pending = bool(self.trials and self.active_trial is None)
        needs_light = pending and self.prepared_lighting != self.trials[0].lighting
        self.prepare_button.configure(state='normal' if needs_light else 'disabled')
        self.trial_button.configure(state='normal' if pending and not needs_light and self.app.camera_ready and self.app.neutral_frames >= 3 else 'disabled')
        self.stop_button.configure(state='normal' if active else 'disabled')

    def close(self):
        self.stop_session()
        self.app.remove_trigger_observer(self._on_trigger)
        self.app.remove_snapshot_observer(self._on_snapshot)
        self.app.experiment_window = None
        self.window.destroy()
