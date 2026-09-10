"""Глобальная Ctrl + Option + Q через системную регистрацию Carbon."""

import ctypes as ct
import sys
import time


class HotkeyError(RuntimeError):
    pass


class HotkeyID(ct.Structure):
    _fields_ = [("signature", ct.c_uint32), ("id", ct.c_uint32)]


class EventType(ct.Structure):
    _fields_ = [("event_class", ct.c_uint32), ("kind", ct.c_uint32)]


KEYBOARD_EVENT = int.from_bytes(b"keyb", "big")
HOTKEY_SIGNATURE = int.from_bytes(b"brkc", "big")
EVENT_TIMEOUT = -9875


def load_carbon():
    carbon = ct.CDLL("/System/Library/Frameworks/Carbon.framework/Carbon")
    signatures = {
        "GetApplicationEventTarget": (ct.c_void_p, []),
        "RegisterEventHotKey": (ct.c_int32, [ct.c_uint32, ct.c_uint32, HotkeyID,
                                             ct.c_void_p, ct.c_uint32, ct.POINTER(ct.c_void_p)]),
        "UnregisterEventHotKey": (ct.c_int32, [ct.c_void_p]),
        "ReceiveNextEvent": (ct.c_int32, [ct.c_ulong, ct.POINTER(EventType), ct.c_double,
                                          ct.c_ubyte, ct.POINTER(ct.c_void_p)]),
        "GetEventParameter": (ct.c_int32, [ct.c_void_p, ct.c_uint32, ct.c_uint32,
                                           ct.c_void_p, ct.c_ulong, ct.c_void_p, ct.c_void_p]),
        "ReleaseEvent": (None, [ct.c_void_p]),
    }
    for name, (result, arguments) in signatures.items():
        function = getattr(carbon, name)
        function.restype = result
        function.argtypes = arguments
    return carbon


class StopHotkey:
    def __init__(self):
        self.carbon = None
        self.reference = ct.c_void_p()
        self.event_type = EventType(KEYBOARD_EVENT, 5)  # kEventHotKeyPressed
        self.identifier = HotkeyID(HOTKEY_SIGNATURE, 1)
        self.triggered = False

    def start(self):
        if sys.platform != "darwin":
            return
        try:
            self.carbon = load_carbon()
            # keyCode 12 = Q / Й; Carbon controlKey | optionKey. Exclusive
            # сообщает о конфликте вместо регистрации неработающего сочетания.
            result = self.carbon.RegisterEventHotKey(
                12, (1 << 12) | (1 << 11), self.identifier,
                self.carbon.GetApplicationEventTarget(), 1, ct.byref(self.reference)
            )
        except (OSError, AttributeError) as error:
            raise HotkeyError("macOS не предоставила системные горячие клавиши.") from error
        if result != 0 or not self.reference.value:
            raise HotkeyError(f"Не удалось зарегистрировать Ctrl + Option + Q (код {result}). "
                              "Возможно, сочетание занято другой программой.")

    def receive(self, timeout):
        if not self.reference.value:
            raise HotkeyError("Сочетание остановки не зарегистрировано.")
        event = ct.c_void_p()
        result = self.carbon.ReceiveNextEvent(
            1, ct.byref(self.event_type), timeout, True, ct.byref(event)
        )
        if result == -9876:  # Cocoa может однократно прервать начальный event loop.
            result = self.carbon.ReceiveNextEvent(
                1, ct.byref(self.event_type), timeout, True, ct.byref(event)
            )
        if result == EVENT_TIMEOUT:
            return False
        if result != 0 or not event.value:
            raise HotkeyError(f"Ошибка получения горячей клавиши (код {result}).")
        try:
            identifier = HotkeyID()
            result = self.carbon.GetEventParameter(
                event, int.from_bytes(b"----", "big"), int.from_bytes(b"hkid", "big"),
                None, ct.sizeof(identifier), None, ct.byref(identifier)
            )
            if result != 0:
                raise HotkeyError(f"Ошибка чтения горячей клавиши (код {result}).")
            return identifier.signature == HOTKEY_SIGNATURE and identifier.id == 1
        finally:
            self.carbon.ReleaseEvent(event)

    def wait(self, seconds):
        if sys.platform != "darwin":
            time.sleep(seconds)
            return
        deadline = time.monotonic() + seconds
        while True:
            remaining = max(0, deadline - time.monotonic())
            # Обрабатываем очередь macOS, сохраняя реакцию на Ctrl+C и SIGTERM.
            if self.receive(min(remaining, 0.05)):
                self.triggered = True
                raise KeyboardInterrupt
            if time.monotonic() >= deadline:
                return

    def close(self):
        if self.reference.value:
            result = self.carbon.UnregisterEventHotKey(self.reference)
            self.reference = ct.c_void_p()
            if result != 0:
                print(f"Не удалось освободить горячую клавишу (код {result}).", file=sys.stderr)


def check_hotkey():
    """Проверка только клавиатуры: никаких эффектов или изменения автозапуска."""
    if sys.platform != "darwin":
        print("Проверка доступна только на macOS.", file=sys.stderr)
        return 1
    from main import hide_dock_icon

    hide_dock_icon()
    hotkey = StopHotkey()
    try:
        hotkey.start()
        print("За 15 секунд нажмите Ctrl + Option + Q (Й). Эффекты выключены.", file=sys.stderr)
        hotkey.wait(15)
        print("Сочетание не получено.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        if hotkey.triggered:
            print("Ctrl + Option + Q получено: остановка работает.", file=sys.stderr)
            return 0
        print("Проверка прервана через Ctrl+C.", file=sys.stderr)
        return 1
    except HotkeyError as error:
        print(str(error), file=sys.stderr)
        return 1
    finally:
        hotkey.close()


if __name__ == "__main__":
    raise SystemExit(check_hotkey())
