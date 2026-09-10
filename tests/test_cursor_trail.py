import subprocess
import unittest
from unittest.mock import Mock, patch

from cursor_trail import CursorTrail, LIFETIME_SECONDS, TrailPoints


class TrailTests(unittest.TestCase):
    def test_teleport_interpolates_bounded_points_and_old_points_expire(self):
        trail = TrailPoints()
        trail.update((10, 20), 0)
        trail.update((1010, 520), 0.1)
        self.assertEqual(len(trail.points), 25)
        self.assertEqual(trail.points[-1][:2], (1010, 520))
        self.assertTrue(all(0 <= point[3] < 1 for point in trail.points))
        trail.update((1010, 520), 0.2)
        self.assertEqual(len(trail.points), 25)
        trail.update((-500, 100), 10)
        self.assertEqual(len(trail.points), 1)  # Нет длинного следа после сна.
        self.assertEqual(trail.points[0][:2], (-500, 100))

    def test_memory_stays_bounded_during_rapid_movement(self):
        trail = TrailPoints()
        for index in range(10000):
            trail.update((index % 2 * 2000, index), index * 0.001)
        self.assertLessEqual(len(trail.points), 600)
        self.assertTrue(all(9.999 - point[2] < LIFETIME_SECONDS for point in trail.points))

    def test_stationary_cursor_fades_out_without_repeated_dots(self):
        trail = TrailPoints()
        for index in range(31):
            trail.update((100, 200), index / 30)
        self.assertEqual(len(trail.points), 0)

    def test_close_sends_eof_and_waits_for_child(self):
        with patch('cursor_trail.sys.platform', 'darwin'), \
                patch('cursor_trail.subprocess.Popen') as spawn:
            trail = CursorTrail()
            trail.start()
            child = spawn.return_value
            self.assertEqual(spawn.call_args.kwargs['stdin'], subprocess.PIPE)
            trail.close()
            child.stdin.close.assert_called_once()
            child.wait.assert_called_once_with(timeout=2)
            child.kill.assert_not_called()
            trail.close()

    def test_stuck_renderer_is_cleaned_up(self):
        trail = CursorTrail()
        child = Mock()
        child.wait.side_effect = [subprocess.TimeoutExpired('renderer', 2), None]
        trail.process = child
        trail.close()
        child.kill.assert_called_once()
        self.assertIsNone(trail.process)

    def test_no_child_on_other_platforms(self):
        with patch('cursor_trail.sys.platform', 'win32'), \
                patch('cursor_trail.subprocess.Popen') as spawn:
            trail = CursorTrail()
            trail.start()
            trail.close()
            spawn.assert_not_called()


if __name__ == '__main__':
    unittest.main()
