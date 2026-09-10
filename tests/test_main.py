import contextlib
import io
import types
import unittest
from unittest.mock import Mock, patch

import main


class CursorTests(unittest.TestCase):
    def setUp(self):
        background = patch.object(main, 'hide_dock_icon', return_value=True)
        background.start()
        self.addCleanup(background.stop)
        audio = patch.object(main, 'RepeatingAudio')
        self.audio_class = audio.start()
        self.audio = self.audio_class.return_value
        self.addCleanup(audio.stop)
        brightness = patch.object(main, 'BrightnessCycle')
        self.brightness = brightness.start().return_value
        self.addCleanup(brightness.stop)
        hotkey = patch.object(main, 'StopHotkey')
        self.hotkey = hotkey.start().return_value
        self.addCleanup(hotkey.stop)
        image = patch.object(main, 'open_image')
        self.open_image = image.start()
        self.addCleanup(image.stop)
        wallpaper = patch.object(main, 'TemporaryWallpaper')
        self.wallpaper = wallpaper.start().return_value
        self.addCleanup(wallpaper.stop)

    def simulate(self, sizes):
        clock = [0.0]
        moments = []
        audio_start = []
        brightness_start = []
        image_opened = []
        wallpaper_start = []
        gui = types.SimpleNamespace(size=Mock(side_effect=sizes), click=Mock())
        self.audio.start.side_effect = lambda: audio_start.append(clock[0])
        self.brightness.start.side_effect = lambda: brightness_start.append(clock[0])
        self.open_image.side_effect = lambda: image_opened.append(clock[0])
        self.wallpaper.start.side_effect = lambda: wallpaper_start.append(clock[0])

        def sleep(seconds):
            self.assertGreaterEqual(seconds, 0)
            if clock[0] < 60:
                self.assertFalse(moments)
                self.audio.start.assert_not_called()
                self.brightness.start.assert_not_called()
                self.open_image.assert_not_called()
                self.wallpaper.start.assert_not_called()
            clock[0] += seconds

        def move(gui, x, y):
            self.assertTrue(0 < x < 1727 and 0 < y < 1116)
            moments.append(clock[0])
            if len(moments) == 3:
                raise KeyboardInterrupt
            return True

        with patch.dict('sys.modules', pyautogui=gui), \
                patch.object(main.time, 'monotonic', lambda: clock[0]), \
                patch.object(self.hotkey, 'wait', sleep), \
                patch.object(main, 'move_cursor', move), \
                contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(main.main(), 0)
        self.assertEqual(stdout.getvalue(), '')
        gui.click.assert_not_called()
        self.audio_class.assert_called_once_with(initial_delay=0)
        self.audio.close.assert_called_once()
        self.assertEqual(brightness_start, [60.0])
        self.brightness.close.assert_called_once()
        self.assertEqual(image_opened, [60.0])
        self.assertEqual(wallpaper_start, [60.0])
        self.wallpaper.close.assert_called_once()
        return moments, audio_start

    def test_cursor_and_audio_wait_one_minute_without_clicking(self):
        moments, audio_start = self.simulate([(1728, 1117)] * 3)
        self.assertEqual(audio_start, [60.0])
        for actual, expected in zip(moments, [60.0, 60.1, 60.2]):
            self.assertAlmostEqual(actual, expected)

    def test_unavailable_screen_recovers_without_exiting(self):
        moments, audio_start = self.simulate([(0, 0), (0, 0)] + [(1728, 1117)] * 3)
        self.assertEqual(audio_start, [60.0])
        for actual, expected in zip(moments, [60.2, 60.3, 60.4]):
            self.assertAlmostEqual(actual, expected)

    def test_cancel_during_startup_delay_prevents_all_activity(self):
        gui = types.SimpleNamespace(size=Mock(), click=Mock())
        with patch.dict('sys.modules', pyautogui=gui), \
                patch.object(self.hotkey, 'wait', side_effect=KeyboardInterrupt), \
                patch.object(main, 'move_cursor') as move, \
                contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(main.main(), 0)
        self.assertEqual(stdout.getvalue(), '')
        self.audio.start.assert_not_called()
        self.open_image.assert_not_called()
        self.wallpaper.start.assert_not_called()
        self.wallpaper.close.assert_called_once()
        self.brightness.start.assert_not_called()
        self.brightness.close.assert_called_once()
        self.audio.close.assert_called_once()
        gui.size.assert_not_called()
        gui.click.assert_not_called()
        move.assert_not_called()

    def test_macos_warp_checks_actual_position_and_return_code(self):
        gui = types.SimpleNamespace(position=Mock(return_value=(100, 200)))
        quartz = types.SimpleNamespace(kCGErrorSuccess=0, CGWarpMouseCursorPosition=Mock(return_value=0))
        with patch.object(main.sys, 'platform', 'darwin'), patch.dict('sys.modules', Quartz=quartz):
            self.assertTrue(main.move_cursor(gui, 100, 200))
            quartz.CGWarpMouseCursorPosition.assert_called_once_with((100, 200))
            gui.position.return_value = (300, 400)
            self.assertFalse(main.move_cursor(gui, 100, 200))
            quartz.CGWarpMouseCursorPosition.return_value = 1002
            gui.position.return_value = (100, 200)
            self.assertFalse(main.move_cursor(gui, 100, 200))

    def test_top_right_corner_does_not_stop_program(self):
        for platform in ('darwin', 'win32'):
            with self.subTest(platform=platform):
                position = [1727, 0]
                gui = types.SimpleNamespace(
                    FAILSAFE=True, click=Mock(), size=lambda: (1728, 1117),
                    position=lambda: tuple(position),
                    failSafeCheck=Mock(side_effect=AssertionError('Corner stop called')),
                )

                def warp(target):
                    position[:] = target
                    return 0

                def move_to(x, y, duration):
                    self.assertFalse(gui.FAILSAFE)
                    warp((x, y))

                gui.moveTo = Mock(side_effect=move_to)
                quartz = types.SimpleNamespace(kCGErrorSuccess=0, CGWarpMouseCursorPosition=Mock(side_effect=warp))
                with patch.object(main.sys, 'platform', platform), \
                        patch.dict('sys.modules', pyautogui=gui, Quartz=quartz), \
                        patch.object(self.hotkey, 'wait', side_effect=[None, None, KeyboardInterrupt]), \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main.main(), 0)
                self.assertFalse(gui.FAILSAFE)
                gui.failSafeCheck.assert_not_called()
                gui.click.assert_not_called()
                self.assertNotEqual(position, [1727, 0])

    def test_other_platforms_keep_pyautogui(self):
        gui = types.SimpleNamespace(moveTo=Mock(), position=lambda: (100, 200))
        with patch.object(main.sys, 'platform', 'win32'):
            self.assertTrue(main.move_cursor(gui, 100, 200))
        gui.moveTo.assert_called_once_with(100, 200, duration=0)


if __name__ == '__main__':
    unittest.main()
