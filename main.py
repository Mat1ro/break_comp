"""Перемещает курсор в случайную точку основного экрана каждые 180 секунд."""

import random
import sys
import time


INTERVAL_SECONDS = 180


def hide_dock_icon():
    """Запускаем текущий процесс как фоновое приложение macOS без значка Dock."""
    if sys.platform != "darwin":
        return True
    from AppKit import NSApplication, NSApplicationActivationPolicyProhibited

    return bool(NSApplication.sharedApplication().setActivationPolicy_(
        NSApplicationActivationPolicyProhibited
    ))


def move_cursor(pyautogui, x, y):
    """На macOS меняем позицию напрямую, без синтетических событий мыши."""
    if sys.platform == "darwin":
        import Quartz

        result = Quartz.CGWarpMouseCursorPosition((x, y))
        if result != Quartz.kCGErrorSuccess:
            return False
    else:
        pyautogui.moveTo(x, y, duration=0)
    return tuple(pyautogui.position()) == (x, y)


def main() -> int:
    try:
        import pyautogui
        # Импорт GUI-зависимостей может зарегистрировать Python в Dock.
        if not hide_dock_icon():
            print("macOS не удалось скрыть значок Python в Dock.", file=sys.stderr)
    except ImportError:
        print(
            "Установите зависимости: python3 -m pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 1

    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0
    print(f"Курсор будет перемещаться каждые {INTERVAL_SECONDS} секунд. Остановка: Ctrl+C.")

    try:
        next_move = time.monotonic() + INTERVAL_SECONDS
        last_status = None
        while True:
            time.sleep(max(0, next_move - time.monotonic()))
            width, height = pyautogui.size()
            if width < 3 or height < 3:
                # Дисплей может быть временно недоступен во время сна/пробуждения.
                if last_status != "screen_unavailable":
                    print("Экран недоступен; ожидаю восстановления рабочего стола.", flush=True)
                last_status = "screen_unavailable"
                next_move = time.monotonic() + INTERVAL_SECONDS
                continue
            # Выбираем точку внутри экрана с отступом в один пиксель.
            x = random.randrange(1, width - 1)
            y = random.randrange(1, height - 1)
            status = "confirmed" if move_cursor(pyautogui, x, y) else "unconfirmed"
            if status != last_status:
                if status == "confirmed":
                    print("Перемещение курсора подтверждено по фактической позиции.", flush=True)
                else:
                    print(f"Позиция курсора не совпала с заданной. Повторю через {INTERVAL_SECONDS} секунд; "
                          "если проблема сохраняется, проверьте разрешения macOS.", flush=True)
            last_status = status
            next_move += INTERVAL_SECONDS
            # После сна компьютера не выполняем пропущенные перемещения подряд.
            if next_move <= time.monotonic():
                next_move = time.monotonic() + INTERVAL_SECONDS
    except KeyboardInterrupt:
        print("\nОстановлено.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
