"""Перемещает курсор в случайную точку основного экрана каждые 5 секунд."""

import random
import sys
import time


INTERVAL_SECONDS = 5


def main() -> int:
    try:
        import pyautogui
    except ImportError:
        print(
            "Установите зависимости: python3 -m pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 1

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0
    print("Курсор будет перемещаться каждые 5 секунд. Остановка: Ctrl+C.")
    print("Аварийная остановка: переместите курсор в левый верхний угол и оставьте там.")

    try:
        next_move = time.monotonic() + INTERVAL_SECONDS
        while True:
            time.sleep(max(0, next_move - time.monotonic()))
            width, height = pyautogui.size()
            if width < 3 or height < 3:
                print("Не удалось определить размеры экрана.", file=sys.stderr)
                return 1
            # Не попадаем в углы, чтобы самим не включить аварийную остановку.
            x = random.randrange(1, width - 1)
            y = random.randrange(1, height - 1)
            pyautogui.moveTo(x, y, duration=0)
            next_move += INTERVAL_SECONDS
            # После сна компьютера не выполняем пропущенные перемещения подряд.
            if next_move <= time.monotonic():
                next_move = time.monotonic() + INTERVAL_SECONDS
    except KeyboardInterrupt:
        print("\nОстановлено.")
    except pyautogui.FailSafeException:
        print("\nОстановлено: курсор находится в углу экрана.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
