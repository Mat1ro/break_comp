import contextlib
import io
import types
import unittest
from unittest.mock import Mock, patch

import main


class CursorTests(unittest.TestCase):
    def test_unavailable_screen_recovers_without_exiting(self):
        clock = [0.0]
        moments = []
        gui = types.SimpleNamespace(
            size=Mock(side_effect=[(0, 0), (0, 0), (1728, 1117), (1728, 1117)]),
        )

        def sleep(seconds):
            self.assertGreaterEqual(seconds, 0)
            clock[0] += seconds

        def move(gui, x, y):
            self.assertTrue(0 < x < 1727 and 0 < y < 1116)
            moments.append(clock[0])
            if len(moments) == 2:
                raise KeyboardInterrupt
            return True

        with patch.dict("sys.modules", pyautogui=gui), \
                patch.object(main.time, "monotonic", lambda: clock[0]), \
                patch.object(main.time, "sleep", sleep), \
                patch.object(main, "move_cursor", move), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main.main(), 0)
        self.assertEqual(moments, [540.0, 720.0])
        self.assertIn("подтверждено", output.getvalue())

    def test_macos_warp_checks_actual_position_and_return_code(self):
        gui = types.SimpleNamespace(position=Mock(return_value=(100, 200)))
        quartz = types.SimpleNamespace(kCGErrorSuccess=0, CGWarpMouseCursorPosition=Mock(return_value=0))
        with patch.object(main.sys, "platform", "darwin"), patch.dict("sys.modules", Quartz=quartz):
            self.assertTrue(main.move_cursor(gui, 100, 200))
            quartz.CGWarpMouseCursorPosition.assert_called_once_with((100, 200))
            gui.position.return_value = (300, 400)
            self.assertFalse(main.move_cursor(gui, 100, 200))
            quartz.CGWarpMouseCursorPosition.return_value = 1002
            gui.position.return_value = (100, 200)
            self.assertFalse(main.move_cursor(gui, 100, 200))

    def test_top_right_corner_does_not_stop_program(self):
        for platform in ("darwin", "win32"):
            with self.subTest(platform=platform):
                position = [1727, 0]
                gui = types.SimpleNamespace(
                    FAILSAFE=True,
                    size=lambda: (1728, 1117),
                    position=lambda: tuple(position),
                    failSafeCheck=Mock(side_effect=AssertionError("Corner stop called")),
                )

                def warp(target):
                    position[:] = target
                    return 0

                def move_to(x, y, duration):
                    self.assertFalse(gui.FAILSAFE)
                    warp((x, y))

                gui.moveTo = Mock(side_effect=move_to)
                quartz = types.SimpleNamespace(
                    kCGErrorSuccess=0, CGWarpMouseCursorPosition=Mock(side_effect=warp)
                )
                with patch.object(main.sys, "platform", platform), \
                        patch.dict("sys.modules", pyautogui=gui, Quartz=quartz), \
                        patch.object(main.time, "sleep", side_effect=[None, KeyboardInterrupt]), \
                        contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(main.main(), 0)
                self.assertFalse(gui.FAILSAFE)
                gui.failSafeCheck.assert_not_called()
                self.assertNotEqual(position, [1727, 0])
                self.assertIn("подтверждено", output.getvalue())
                self.assertIn("Остановлено.", output.getvalue())

    def test_other_platforms_keep_pyautogui(self):
        gui = types.SimpleNamespace(moveTo=Mock(), position=lambda: (100, 200))
        with patch.object(main.sys, "platform", "win32"):
            self.assertTrue(main.move_cursor(gui, 100, 200))
        gui.moveTo.assert_called_once_with(100, 200, duration=0)


if __name__ == "__main__":
    unittest.main()
