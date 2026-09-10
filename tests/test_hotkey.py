import contextlib
import io
import types
import unittest
from unittest.mock import Mock, patch

import main


class HotkeyTests(unittest.TestCase):
    def test_all_three_keys_required_with_either_modifier_side(self):
        for control in (59, 62):
            for option in (58, 61):
                combination = {12, control, option}
                for missing in (None, 12, control, option):
                    pressed = combination - {missing}
                    quartz = types.SimpleNamespace(
                        kCGEventSourceStateCombinedSessionState=0,
                        CGEventSourceKeyState=lambda state, key: key in pressed,
                    )
                    with self.subTest(pressed=pressed), \
                            patch.object(main.sys, 'platform', 'darwin'), \
                            patch.dict('sys.modules', Quartz=quartz):
                        self.assertEqual(main.stop_requested(), missing is None)

    def test_hotkey_stops_main_during_delay_and_during_effects(self):
        for pressed_at in (0.06, 60.06):
            clock = [0.0]
            gui = types.SimpleNamespace(size=lambda: (1728, 1117), click=Mock())

            def sleep(seconds):
                self.assertGreater(seconds, 0)
                self.assertLessEqual(seconds, main.HOTKEY_POLL_SECONDS)
                clock[0] += seconds

            with self.subTest(pressed_at=pressed_at), \
                    patch.object(main.sys, 'platform', 'darwin'), \
                    patch.dict('sys.modules', pyautogui=gui), \
                    patch.object(main, 'hide_dock_icon', return_value=True), \
                    patch.object(main, 'RepeatingAudio') as audio_class, \
                    patch.object(main, 'BrightnessCycle') as brightness_class, \
                    patch.object(main, 'move_cursor', return_value=True) as move, \
                    patch.object(main, 'stop_requested', side_effect=lambda: clock[0] >= pressed_at), \
                    patch.object(main.time, 'monotonic', side_effect=lambda: clock[0]), \
                    patch.object(main.time, 'sleep', side_effect=sleep), \
                    contextlib.redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main.main(), 0)
                self.assertEqual(stdout.getvalue(), '')
                audio_class.return_value.close.assert_called_once()
                brightness_class.return_value.close.assert_called_once()
                if pressed_at < 60:
                    audio_class.return_value.start.assert_not_called()
                    brightness_class.return_value.start.assert_not_called()
                    move.assert_not_called()
                else:
                    audio_class.return_value.start.assert_called_once()
                    brightness_class.return_value.start.assert_called_once()
                    self.assertGreater(move.call_count, 0)
                gui.click.assert_not_called()
                self.assertLessEqual(clock[0] - pressed_at, main.HOTKEY_POLL_SECONDS + 1e-8)

    def test_hotkey_checked_even_when_next_action_is_already_due(self):
        with patch.object(main.sys, 'platform', 'darwin'), \
                patch.object(main, 'stop_requested', return_value=True):
            with self.assertRaises(KeyboardInterrupt):
                main.wait_or_stop(0)

    def test_other_platforms_keep_normal_sleep(self):
        with patch.object(main.sys, 'platform', 'win32'), \
                patch.object(main.time, 'sleep') as sleep:
            self.assertFalse(main.stop_requested())
            main.wait_or_stop(0.1)
            sleep.assert_called_once_with(0.1)


if __name__ == '__main__':
    unittest.main()
