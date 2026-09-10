import contextlib
import io
import types
import unittest
from unittest.mock import Mock, patch

import main


class CursorTests(unittest.TestCase):
    def setUp(self):
        # Проверки логики курсора не должны менять GUI тестового процесса.
        background = patch.object(main, "hide_dock_icon", return_value=True)
        background.start()
        self.addCleanup(background.stop)
        audio = patch.object(main, "RepeatingAudio")
        self.audio = audio.start().return_value
        self.addCleanup(audio.stop)
        click = patch.object(main, "double_click", side_effect=lambda gui, x, y:
                             gui.click(x=x, y=y, clicks=2, interval=0, button="left"))
        click.start()
        self.addCleanup(click.stop)

    def test_unavailable_screen_recovers_without_exiting(self):
        clock = [0.0]
        moments = []
        gui = types.SimpleNamespace(
            size=Mock(side_effect=[(0, 0), (0, 0), (1728, 1117), (1728, 1117)]),
            click=Mock(),
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
        self.assertEqual(moments, [3 * main.INTERVAL_SECONDS, 4 * main.INTERVAL_SECONDS])
        self.audio.start.assert_called_once()
        self.audio.close.assert_called_once()
        self.assertEqual(gui.click.call_count, 1)
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
                    click=Mock(),
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

    def test_double_left_click_after_each_successful_move_only(self):
        events = []
        gui = types.SimpleNamespace(
            size=lambda: (1728, 1117),
            click=Mock(side_effect=lambda **kwargs: events.append(("click", kwargs))),
        )

        def move(gui, x, y):
            events.append(("move", x, y))
            return x != 100

        with patch.dict("sys.modules", pyautogui=gui), \
                patch.object(main, "move_cursor", side_effect=move), \
                patch.object(main.random, "randrange", side_effect=[100, 200, 300, 400, 500, 600]), \
                patch.object(main.time, "sleep", side_effect=[None, None, None, KeyboardInterrupt]), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main.main(), 0)
        self.assertEqual(events, [
            ("move", 100, 200),
            ("move", 300, 400),
            ("click", {"x": 300, "y": 400, "clicks": 2, "interval": 0, "button": "left"}),
            ("move", 500, 600),
            ("click", {"x": 500, "y": 600, "clicks": 2, "interval": 0, "button": "left"}),
        ])

    def test_other_platforms_keep_pyautogui(self):
        gui = types.SimpleNamespace(moveTo=Mock(), position=lambda: (100, 200))
        with patch.object(main.sys, "platform", "win32"):
            self.assertTrue(main.move_cursor(gui, 100, 200))
        gui.moveTo.assert_called_once_with(100, 200, duration=0)


class DoubleClickTests(unittest.TestCase):
    def test_macos_sends_two_down_up_pairs_with_click_counts(self):
        created = []
        posted = []

        def create(source, event_type, point, button):
            event = {"type": event_type, "point": point, "button": button}
            created.append(event)
            return event

        quartz = types.SimpleNamespace(
            kCGEventLeftMouseDown="down", kCGEventLeftMouseUp="up",
            kCGMouseButtonLeft="left", kCGMouseEventClickState="count", kCGHIDEventTap="tap",
            CGEventCreateMouseEvent=create,
            CGEventSetIntegerValueField=lambda event, key, value: event.update({key: value}),
            CGEventPost=lambda tap, event: posted.append((tap, event.copy())),
        )
        with patch.object(main.sys, "platform", "darwin"), patch.dict("sys.modules", Quartz=quartz):
            main.double_click(Mock(), 100, 200)
        self.assertEqual([(event["type"], event["count"]) for _, event in posted],
                         [("down", 1), ("up", 1), ("down", 2), ("up", 2)])
        self.assertTrue(all(tap == "tap" and event["point"] == (100, 200)
                            and event["button"] == "left" for tap, event in posted))

    def test_other_platforms_click_twice_without_delay(self):
        gui = Mock()
        with patch.object(main.sys, "platform", "win32"):
            main.double_click(gui, 100, 200)
        gui.click.assert_called_once_with(x=100, y=200, clicks=2, interval=0, button="left")


if __name__ == "__main__":
    unittest.main()
