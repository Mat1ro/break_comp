import contextlib
import io
import types
import unittest
from unittest.mock import Mock, patch

import main
import stop_hotkey as keys


class HotkeyTests(unittest.TestCase):
    def setUp(self):
        self.carbon = Mock()
        self.carbon.GetApplicationEventTarget.return_value = 10
        self.carbon.UnregisterEventHotKey.return_value = 0

        def register(key, modifiers, identifier, target, options, reference):
            reference._obj.value = 123
            return 0

        self.carbon.RegisterEventHotKey.side_effect = register
        self.carbon.ReceiveNextEvent.return_value = keys.EVENT_TIMEOUT
        for item in (patch.object(keys.sys, 'platform', 'darwin'),
                     patch.object(keys, 'load_carbon', return_value=self.carbon)):
            item.start()
            self.addCleanup(item.stop)
        self.hotkey = keys.StopHotkey()
        self.addCleanup(self.hotkey.close)

    def deliver(self, signature=keys.HOTKEY_SIGNATURE):
        def receive(count, event_type, timeout, pull, event):
            event._obj.value = 777
            return 0

        def parameter(event, name, value_type, actual_type, size, actual_size, identifier):
            identifier._obj.signature = signature
            identifier._obj.id = 1
            return 0

        self.carbon.ReceiveNextEvent.side_effect = receive
        self.carbon.GetEventParameter.side_effect = parameter

    def test_registers_exclusive_ctrl_option_q_and_releases_it(self):
        self.hotkey.start()
        args = self.carbon.RegisterEventHotKey.call_args.args
        self.assertEqual(args[:2], (12, 6144))
        self.assertEqual(args[4], 1)
        self.hotkey.close()
        self.hotkey.close()
        self.carbon.UnregisterEventHotKey.assert_called_once()

    def test_queued_short_press_stops_even_when_deadline_is_due(self):
        self.hotkey.start()
        self.deliver()
        with self.assertRaises(KeyboardInterrupt):
            self.hotkey.wait(0)
        self.assertTrue(self.hotkey.triggered)
        self.carbon.ReleaseEvent.assert_called_once()

    def test_unrelated_event_is_ignored_and_released(self):
        self.hotkey.start()
        self.deliver(signature=0)
        self.assertFalse(self.hotkey.receive(0))
        self.carbon.ReleaseEvent.assert_called_once()

    def test_cocoa_initial_loop_quit_reenters_event_loop(self):
        self.hotkey.start()
        self.carbon.ReceiveNextEvent.side_effect = [-9876, keys.EVENT_TIMEOUT]
        self.assertFalse(self.hotkey.receive(0.01))
        self.assertEqual(self.carbon.ReceiveNextEvent.call_count, 2)

    def test_repeated_loop_error_aborts(self):
        self.hotkey.start()
        self.carbon.ReceiveNextEvent.side_effect = [-9876, -9876]
        with self.assertRaises(keys.HotkeyError):
            self.hotkey.receive(0.01)

    def test_conflicting_registration_aborts(self):
        self.carbon.RegisterEventHotKey.side_effect = None
        self.carbon.RegisterEventHotKey.return_value = -9878
        with self.assertRaises(keys.HotkeyError):
            self.hotkey.start()
        self.assertFalse(self.hotkey.reference.value)

    def test_other_platforms_keep_sleep_without_registration(self):
        with patch.object(keys.sys, 'platform', 'win32'), patch.object(keys.time, 'sleep') as sleep:
            self.hotkey.start()
            self.hotkey.wait(0.1)
            self.hotkey.close()
            sleep.assert_called_once_with(0.1)
        self.carbon.RegisterEventHotKey.assert_not_called()

    def test_main_stops_before_effects_if_registration_fails(self):
        gui = types.SimpleNamespace()
        with patch.dict('sys.modules', pyautogui=gui), \
                patch.object(main, 'hide_dock_icon', return_value=True), \
                patch.object(main, 'StopHotkey') as hotkey_class, \
                patch.object(main, 'RepeatingAudio') as audio, \
                patch.object(main, 'BrightnessCycle') as brightness, \
                patch.object(main, 'move_cursor') as move, \
                contextlib.redirect_stderr(io.StringIO()) as stderr, \
                contextlib.redirect_stdout(io.StringIO()) as stdout:
            hotkey_class.return_value.start.side_effect = keys.HotkeyError('conflict')
            self.assertEqual(main.main(), 1)
            audio.return_value.start.assert_not_called()
            brightness.return_value.start.assert_not_called()
            move.assert_not_called()
            hotkey_class.return_value.close.assert_called_once()
            self.assertIn('Программа остановлена', stderr.getvalue())
            self.assertEqual(stdout.getvalue(), '')

    def test_main_cleans_up_for_hotkey_during_delay_and_effects(self):
        for wait_results in ([KeyboardInterrupt], [None, None, KeyboardInterrupt]):
            gui = types.SimpleNamespace(size=lambda: (1728, 1117))
            with self.subTest(wait_results=wait_results), \
                    patch.dict('sys.modules', pyautogui=gui), \
                    patch.object(main, 'hide_dock_icon', return_value=True), \
                    patch.object(main, 'StopHotkey') as hotkey_class, \
                    patch.object(main, 'RepeatingAudio') as audio, \
                    patch.object(main, 'BrightnessCycle') as brightness, \
                    patch.object(main, 'move_cursor', return_value=True) as move, \
                    contextlib.redirect_stdout(io.StringIO()) as stdout:
                hotkey_class.return_value.wait.side_effect = wait_results
                self.assertEqual(main.main(), 0)
                audio.return_value.close.assert_called_once()
                brightness.return_value.close.assert_called_once()
                hotkey_class.return_value.close.assert_called_once()
                self.assertEqual(stdout.getvalue(), '')
                if len(wait_results) == 1:
                    audio.return_value.start.assert_not_called()
                    brightness.return_value.start.assert_not_called()
                    move.assert_not_called()
                else:
                    audio.return_value.start.assert_called_once()
                    brightness.return_value.start.assert_called_once()
                    move.assert_called_once()


if __name__ == '__main__':
    unittest.main()
