import csv
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from interaction import DwellConfirmation, point_to_zone, zone_rectangles
from experiment_runner import ExperimentRecorder, TrialObservation, build_trial_schedule
from analyze_results import build_report, summarize


class ZonesAndDwellTests(unittest.TestCase):
    def test_shared_geometry_and_boundary_ownership(self):
        self.assertEqual([point_to_zone(x, .9) for x in (0, .25, .5, .75, 1)], ['Z3', 'Z4', 'Z5', 'Z6', 'Z6'])
        self.assertEqual(point_to_zone(.499, .779), 'Z1')
        self.assertEqual(point_to_zone(.5, .779), 'Z2')
        self.assertEqual(point_to_zone(0, .78), 'Z3')
        for point in ((-.01, .5), (.2, 1.01), (float('nan'), .1)):
            self.assertIsNone(point_to_zone(*point))
        self.assertEqual(zone_rectangles(640, 480)['Z3'], (0, 374, 160, 480))

    def test_crossing_loss_and_long_gap_break_consecutive_frames(self):
        gate = DwellConfirmation(3, 1)
        sequence = [('Z1', 0), ('Z1', .03), ('Z2', .06), (None, .09), ('Z2', .12), ('Z2', .15), ('Z2', .9), ('Z2', .93)]
        for zone, now in sequence:
            self.assertIsNone(gate.update(zone, now).triggered_zone)
        self.assertEqual(gate.update('Z2', .96).triggered_zone, 'Z2')

    def test_holding_never_retriggers_even_after_cooldown(self):
        gate = DwellConfirmation(2, .5)
        gate.update('Z3', 0)
        self.assertEqual(gate.update('Z3', .03).triggered_zone, 'Z3')
        for i in range(1, 100):
            self.assertIsNone(gate.update('Z3', .03 + i * .03).triggered_zone)
        gate.update(None, 3.1)
        self.assertIsNone(gate.update('Z3', 3.13).triggered_zone)
        self.assertEqual(gate.update('Z3', 3.16).triggered_zone, 'Z3')

    def test_exit_during_cooldown_does_not_accumulate(self):
        gate = DwellConfirmation(2, 1)
        gate.update('Z1', 0)
        gate.update('Z1', .01)
        gate.update(None, .1)
        for i in range(2, 10):
            self.assertEqual(gate.update('Z2', i / 10).frames, 0)
        self.assertIsNone(gate.update('Z2', 1.02).triggered_zone)
        self.assertEqual(gate.update('Z2', 1.05).triggered_zone, 'Z2')

    def test_setting_change_starts_fresh_confirmation(self):
        gate = DwellConfirmation(6, 1)
        for i in range(5):
            gate.update('Z1', i / 30)
        gate.configure(consecutive_frames=3)
        self.assertIsNone(gate.update('Z1', .2).triggered_zone)
        for value in (0, -1, 1.5, True):
            with self.assertRaises(ValueError):
                gate.configure(consecutive_frames=value)


class ExperimentTests(unittest.TestCase):
    def test_all_75_trials_balanced_and_frozen(self):
        e1 = build_trial_schedule('experiment1')
        e2 = build_trial_schedule('experiment2')
        e3 = build_trial_schedule('experiment3')
        self.assertEqual([len(e1), len(e2), len(e3)], [30, 27, 18])
        self.assertEqual(Counter(t.target_zone for t in e1), dict.fromkeys(('Z1', 'Z2', 'Z3', 'Z4', 'Z5', 'Z6'), 5))
        self.assertEqual(set(Counter((t.target_zone, t.dwell_frames) for t in e2).values()), {3})
        self.assertEqual(set(Counter((t.target_zone, t.lighting) for t in e3).values()), {3})
        self.assertEqual({t.dwell_frames for t in e1 + e3}, {6})
        self.assertEqual(len({t.trial_id for t in e1 + e2 + e3}), 75)
        with self.assertRaises(ValueError):
            build_trial_schedule('experiment2', dwell_levels={'Short': 6, 'Medium': 3, 'Long': 10})

    def test_timeout_is_distinct_from_wrong_zone_and_detection_failure(self):
        observation = TrialObservation()
        self.assertTrue(observation.outcome('Z1', None, None)['detection_failure'])
        for detected in (True, False, False, True):
            observation.observe(SimpleNamespace(hand_detected=detected, hand_count=int(detected), detected_zone='Z2' if detected else None, wrist=(.6, .2) if detected else None, fps=25))
        timeout = observation.outcome('Z1', None, None)
        wrong = observation.outcome('Z1', 'Z2', 500)
        self.assertFalse(timeout['detection_failure'])
        self.assertTrue(timeout['missed_trigger'])
        self.assertEqual(timeout['trigger_time_ms'], '')
        self.assertTrue(wrong['false_trigger'])
        self.assertFalse(wrong['missed_trigger'])
        self.assertEqual(wrong['tracking_loss_count'], 1)
        self.assertEqual(wrong['no_hand_frames'], 2)

    def test_immediate_csv_write_preserves_blank_latency_and_booleans(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = ExperimentRecorder(directory)
            path = recorder.start('experiment1')
            recorder.record({'trial_id': 'E1-001', **TrialObservation().outcome('Z1', None, None)})
            with path.open(encoding='utf-8-sig') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['detection_failure'], 'true')
            self.assertEqual(rows[0]['trigger_time_ms'], '')


class AnalysisTests(unittest.TestCase):
    def test_timeout_does_not_become_zero_latency(self):
        rows = [
            dict(correct='true', false_trigger='false', missed_trigger='false', detection_failure='false', trigger_time_ms='800'),
            dict(correct='false', false_trigger='false', missed_trigger='true', detection_failure='true', trigger_time_ms=''),
            dict(correct='false', false_trigger='true', missed_trigger='false', detection_failure='false', trigger_time_ms='300'),
        ]
        self.assertEqual(summarize(rows), [3, '33.3%', 1, 1, 1, '800.0'])

    def test_duplicate_session_trial_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = ExperimentRecorder(directory)
            path = recorder.start('experiment1')
            recorder.record({'session_id': 's', 'trial_id': 'E1-001', 'experiment': 'experiment1',
                             'target_command': 'Previous Page', **TrialObservation().outcome('Z1', None, None)})
            self.assertIn('全程未偵測', build_report([path]))
            with self.assertRaises(ValueError):
                build_report([path, path])


if __name__ == '__main__':
    unittest.main()
