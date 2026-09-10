"""Управление автозапуском курсора через пользовательский macOS LaunchAgent."""

import argparse
import os
from pathlib import Path
import plistlib
import subprocess
import sys


LABEL = "io.github.mat1ro.break-comp"
PROJECT = Path(__file__).resolve().parent
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOGS = Path.home() / "Library" / "Logs" / "break_comp"


def configuration():
    return {
        "Label": LABEL,
        # Не resolve(): Python должен сохранить привязку к виртуальному окружению.
        "ProgramArguments": [str(PROJECT / ".venv/bin/python"), "-u", str(PROJECT / "main.py")],
        "WorkingDirectory": str(PROJECT),
        "RunAtLoad": True,
        "LimitLoadToSessionType": "Aqua",
        # Завершившееся приложение остаётся остановленным до следующего входа.
        "KeepAlive": False,
        "StandardOutPath": str(LOGS / "stdout.log"),
        "StandardErrorPath": str(LOGS / "stderr.log"),
    }


def launchctl(*arguments, check=True):
    result = subprocess.run(
        ["/bin/launchctl", *arguments], capture_output=True, text=True
    )
    if check and result.returncode:
        raise RuntimeError(f"launchctl {arguments[0]}: {result.stderr.strip()}")
    return result


def stop(service):
    if launchctl("print", service, check=False).returncode == 0:
        launchctl("bootout", service)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["install", "uninstall", "stop", "status", "preview"])
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("Автозапуск поддерживается только на macOS.")

    domain = f"gui/{os.getuid()}"
    service = f"{domain}/{LABEL}"
    try:
        if args.action == "preview":
            sys.stdout.buffer.write(plistlib.dumps(configuration()))
        elif args.action == "install":
            python = PROJECT / ".venv/bin/python"
            if not python.is_file() or not (PROJECT / "main.py").is_file():
                raise RuntimeError("Сначала создайте .venv и установите зависимости по README.md.")
            subprocess.run([str(python), "-c", "import pyautogui"], check=True)
            payload = plistlib.dumps(configuration())
            PLIST.parent.mkdir(parents=True, exist_ok=True)
            LOGS.mkdir(parents=True, exist_ok=True)
            stop(service)
            PLIST.write_bytes(payload)
            PLIST.chmod(0o644)
            launchctl("enable", service)
            launchctl("bootstrap", domain, str(PLIST))
            print("Автозапуск установлен, программа запущена в текущем сеансе.")
            print(f"Настройка: {PLIST}")
            print(f"Логи: {LOGS}")
        elif args.action == "uninstall":
            stop(service)
            PLIST.unlink(missing_ok=True)
            print("Программа остановлена, автозапуск удалён.")
        elif args.action == "stop":
            stop(service)
            print("Остановлено до следующего входа в macOS.")
        else:
            print(f"Автозапуск: {'установлен' if PLIST.is_file() else 'не установлен'}")
            result = launchctl("print", service, check=False)
            if result.returncode:
                print("Агент не загружен в текущем сеансе.")
            else:
                # Полный вывод launchctl может содержать переменные окружения.
                seen = set()
                for line in result.stdout.splitlines():
                    key, separator, value = line.strip().partition(" = ")
                    if separator and key in {"state", "pid", "last exit code"} and key not in seen:
                        print(f"{key} = {value}")
                        seen.add(key)
        return 0
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
