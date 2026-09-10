import contextlib
import io
import unittest
from unittest.mock import Mock, patch

import brightness_controller as brightness


class BrightnessTests(unittest.TestCase):
    def setUp(self):
        self.clock = 60.0
        self.backend = Mock()
        self.backend.get.return_value = 0.42
        for target, options in (
            ('sys.platform', {'new': 'darwin'}),
            ('BuiltinBrightness', {'return_value': self.backend}),
            ('time.monotonic', {'side_effect': lambda: self.clock}),
        ):
            mocked = patch('brightness_controller.' + target, **options)
            mocked.start()
            self.addCleanup(mocked.stop)

    def test_min_max_every_three_seconds_and_restore_on_close(self):
        changes = []
        self.backend.set.side_effect = lambda value: changes.append((self.clock, value))
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            cycle = brightness.BrightnessCycle()
            self.backend.get.assert_not_called()
            self.backend.set.assert_not_called()
            cycle.start()
            for moment in (60.1, 62.9, 63.0, 65.9, 66.0, 69.0):
                self.clock = moment
                cycle.update()
            self.assertEqual(changes, [(60.0, 0.0), (63.0, 1.0), (66.0, 0.0), (69.0, 1.0)])
            cycle.close()
            self.assertEqual(changes[-1], (69.0, 0.42))
            cycle.close()
            self.assertEqual(len(changes), 5)
            self.assertEqual(stdout.getvalue(), '')

    def test_no_burst_of_missed_changes_after_sleep(self):
        cycle = brightness.BrightnessCycle()
        cycle.start()
        self.clock = 100
        cycle.update()
        self.assertEqual(self.backend.set.call_count, 2)
        self.assertEqual(cycle.next_switch, 103)
        self.clock = 100.1
        cycle.update()
        self.assertEqual(self.backend.set.call_count, 2)

    def test_never_changes_screen_if_original_brightness_cannot_be_read(self):
        self.backend.get.side_effect = RuntimeError
        cycle = brightness.BrightnessCycle()
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            cycle.start()
            cycle.update()
            cycle.close()
        self.backend.set.assert_not_called()
        self.assertIn('недоступно', stderr.getvalue())

    def test_failed_change_retries_same_level_then_restores_original(self):
        self.backend.set.side_effect = [RuntimeError, None, None]
        cycle = brightness.BrightnessCycle()
        with contextlib.redirect_stderr(io.StringIO()):
            cycle.start()
        self.clock = 63
        cycle.update()
        cycle.close()
        self.assertEqual([call.args[0] for call in self.backend.set.call_args_list], [0.0, 0.0, 0.42])

    def test_restore_failure_is_reported_without_blocking_cleanup(self):
        cycle = brightness.BrightnessCycle()
        cycle.start()
        self.backend.set.side_effect = RuntimeError
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            cycle.close()
            cycle.close()
        self.assertIn('восстановить', stderr.getvalue())
        self.assertIsNone(cycle.backend)

    def test_stop_before_start_and_other_platforms_do_not_change_screen(self):
        cycle = brightness.BrightnessCycle()
        cycle.close()
        with patch.object(brightness.sys, 'platform', 'win32'):
            cycle.start()
            cycle.update()
            cycle.close()
        self.backend.get.assert_not_called()
        self.backend.set.assert_not_called()


if __name__ == '__main__':
    unittest.main()
