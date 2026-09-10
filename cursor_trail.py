"""Радужный след на macOS; отдельный GUI-процесс с временем жизни родителя."""

from collections import deque
from pathlib import Path
import math
import select
import subprocess
import sys
import time

FRAME_SECONDS = 1 / 30
LIFETIME_SECONDS = 0.8


class TrailPoints:
    def __init__(self):
        self.points = deque(maxlen=600)
        self.previous = None
        self.last_update = None

    def update(self, position, now):
        while self.points and now - self.points[0][2] >= LIFETIME_SECONDS:
            self.points.popleft()
        # После сна не соединяем новый курсор с давно исчезнувшим следом.
        if self.last_update is not None and now - self.last_update >= LIFETIME_SECONDS:
            self.previous = None
        self.last_update = now
        x, y = position
        if position != self.previous:
            start = self.previous or position
            distance = math.hypot(x - start[0], y - start[1])
            steps = max(1, min(24, math.ceil(distance / 18)))
            for step in range(1, steps + 1):
                fraction = step / steps
                self.points.append((
                    start[0] + (x - start[0]) * fraction,
                    start[1] + (y - start[1]) * fraction,
                    now, (now * 0.3 + fraction * 0.15) % 1,
                ))
            self.previous = position


class CursorTrail:
    def __init__(self):
        self.process = None

    def start(self):
        if sys.platform != "darwin":
            return
        try:
            self.process = subprocess.Popen(
                [sys.executable, "-u", str(Path(__file__).resolve()), "--child"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
            )
        except OSError as error:
            print(f"Не удалось включить след ({type(error).__name__}).", file=sys.stderr)

    def close(self):
        if self.process is None:
            return
        # EOF также придёт при аварийном завершении основного процесса.
        self.process.stdin.close()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.process = None


def run_overlay():
    import AppKit as ak
    import Foundation as foundation
    import objc

    app = ak.NSApplication.sharedApplication()
    # Accessory разрешает окна, но не добавляет приложение в Dock / Cmd+Tab.
    app.setActivationPolicy_(ak.NSApplicationActivationPolicyAccessory)
    app.finishLaunching()
    trail = TrailPoints()

    class RainbowTrailView(ak.NSView):
        def isOpaque(self):
            return False

        def drawRect_(self, rect):
            ak.NSColor.clearColor().set()
            ak.NSRectFillUsingOperation(rect, ak.NSCompositingOperationCopy)
            origin = self.window().frame().origin
            now = time.monotonic()
            for x, y, created, hue in trail.points:
                fade = max(0, 1 - (now - created) / LIFETIME_SECONDS)
                if not fade:
                    continue
                radius = 2 + 4 * fade
                for scale, opacity in ((2.2, 0.12), (1, 0.8)):
                    size = radius * scale
                    ak.NSColor.colorWithCalibratedHue_saturation_brightness_alpha_(
                        hue, 0.85, 1, opacity * fade
                    ).set()
                    ak.NSBezierPath.bezierPathWithOvalInRect_(
                        ((x - origin.x - size, y - origin.y - size), (size * 2, size * 2))
                    ).fill()

    windows = []
    screen_frames = None
    next_screens_check = 0
    try:
        while True:
            # Канал принадлежит только родителю; данные не нужны, ждём EOF.
            if select.select([sys.stdin], [], [], 0)[0] and not sys.stdin.buffer.read(1):
                break
            with objc.autorelease_pool():
                now = time.monotonic()
                if now >= next_screens_check:
                    frames = [screen.frame() for screen in ak.NSScreen.screens()]
                    if frames != screen_frames:
                        for window in windows:
                            window.close()
                        windows.clear()
                        screen_frames = frames
                        for frame in frames:
                            window = ak.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
                                frame, ak.NSWindowStyleMaskBorderless, ak.NSBackingStoreBuffered, False
                            )
                            window.setReleasedWhenClosed_(False)
                            window.setOpaque_(False)
                            window.setBackgroundColor_(ak.NSColor.clearColor())
                            window.setHasShadow_(False)
                            window.setIgnoresMouseEvents_(True)
                            window.setLevel_(ak.NSStatusWindowLevel)
                            window.setCollectionBehavior_(
                                ak.NSWindowCollectionBehaviorCanJoinAllSpaces
                                | ak.NSWindowCollectionBehaviorFullScreenAuxiliary
                                | ak.NSWindowCollectionBehaviorIgnoresCycle
                            )
                            view = RainbowTrailView.alloc().initWithFrame_(((0, 0), frame.size))
                            window.setContentView_(view)
                            window.orderFrontRegardless()
                            windows.append(window)
                    next_screens_check = now + 1
                # Cocoa даёт общие координаты всех экранов, включая Retina.
                point = ak.NSEvent.mouseLocation()
                trail.update((point.x, point.y), now)
                for window in windows:
                    window.contentView().setNeedsDisplay_(True)
                    window.displayIfNeeded()
                deadline = foundation.NSDate.dateWithTimeIntervalSinceNow_(FRAME_SECONDS)
                event = app.nextEventMatchingMask_untilDate_inMode_dequeue_(
                    ak.NSEventMaskAny, deadline, foundation.NSDefaultRunLoopMode, True
                )
                if event is not None:
                    app.sendEvent_(event)
    finally:
        for window in windows:
            window.close()


if __name__ == "__main__" and sys.argv[1:] == ["--child"]:
    try:
        run_overlay()
    except KeyboardInterrupt:
        pass
