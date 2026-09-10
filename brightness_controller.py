"""Переключение яркости встроенного экрана macOS с восстановлением при выходе."""

import ctypes
import math
import sys
import time

BRIGHTNESS_INTERVAL_SECONDS = 3
BRIGHTNESS_ERRORS = (ImportError, OSError, AttributeError, RuntimeError, ValueError)


class BuiltinBrightness:
    def __init__(self):
        import Quartz

        error, displays, count = Quartz.CGGetOnlineDisplayList(32, None, None)
        if error != Quartz.kCGErrorSuccess:
            raise RuntimeError("Не удалось получить список экранов.")
        self.display = next(
            (display for display in displays[:count] if Quartz.CGDisplayIsBuiltin(display)), None
        )
        if self.display is None:
            raise RuntimeError("Встроенный экран недоступен.")
        # Непубличный macOS API; отсутствие поддержки не мешает остальным эффектам.
        self.library = ctypes.CDLL(
            "/System/Library/PrivateFrameworks/DisplayServices.framework/DisplayServices"
        )
        self.get_brightness = self.library.DisplayServicesGetBrightness
        self.get_brightness.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_float)]
        self.get_brightness.restype = ctypes.c_int32
        self.set_brightness = self.library.DisplayServicesSetBrightness
        self.set_brightness.argtypes = [ctypes.c_uint32, ctypes.c_float]
        self.set_brightness.restype = ctypes.c_int32

    def get(self):
        value = ctypes.c_float()
        if self.get_brightness(self.display, ctypes.byref(value)) != 0:
            raise RuntimeError("Не удалось прочитать яркость.")
        if not math.isfinite(value.value) or not 0 <= value.value <= 1:
            raise ValueError("Некорректная яркость.")
        return value.value

    def set(self, value):
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("Яркость должна быть от 0 до 1.")
        if self.set_brightness(self.display, value) != 0:
            raise RuntimeError("Не удалось изменить яркость.")


class BrightnessCycle:
    def __init__(self):
        self.backend = None
        self.original = None
        self.changed = False
        self.next_switch = 0
        self.level = 0.0
        self.error_reported = False

    def start(self):
        if sys.platform != "darwin":
            return
        try:
            self.backend = BuiltinBrightness()
            # Не меняем яркость, если не удалось сохранить исходное значение.
            self.original = self.backend.get()
        except BRIGHTNESS_ERRORS as error:
            self.backend = None
            print(f"Переключение яркости недоступно ({type(error).__name__}).", file=sys.stderr)
            return
        self.next_switch = time.monotonic()
        self.update()

    def update(self):
        if self.backend is None:
            return
        now = time.monotonic()
        if now < self.next_switch:
            return
        try:
            self.changed = True
            self.backend.set(self.level)
            self.level = 1.0 - self.level
            self.error_reported = False
        except BRIGHTNESS_ERRORS as error:
            if not self.error_reported:
                print(f"Не удалось изменить яркость ({type(error).__name__}); повторю через 3 секунды.",
                      file=sys.stderr, flush=True)
            self.error_reported = True
        self.next_switch += BRIGHTNESS_INTERVAL_SECONDS
        # Не выполняем пропущенные переключения подряд после сна компьютера.
        if self.next_switch <= time.monotonic():
            self.next_switch = time.monotonic() + BRIGHTNESS_INTERVAL_SECONDS

    def close(self):
        try:
            if self.backend is not None and self.changed:
                self.backend.set(self.original)
        except BRIGHTNESS_ERRORS as error:
            print(f"Не удалось восстановить яркость ({type(error).__name__}).", file=sys.stderr)
        finally:
            self.backend = None
            self.changed = False
