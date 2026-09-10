"""Независимое воспроизведение звука каждые 10 секунд на macOS."""

from pathlib import Path
import subprocess
import sys
import threading
import time


AUDIO_INTERVAL_SECONDS = 10
AUDIO_FILE = Path(__file__).resolve().parent / "assets" / "farts-8.mp3"


class RepeatingAudio:
    def __init__(self):
        self.stop_event = threading.Event()
        self.thread = None
        self.player = None

    def start(self):
        if sys.platform != "darwin":
            print("Воспроизведение звука поддерживается только на macOS.")
            return
        if not AUDIO_FILE.is_file():
            print(f"Аудиофайл не найден: {AUDIO_FILE}", file=sys.stderr)
            return
        self.thread = threading.Thread(target=self._run, name="repeating-audio", daemon=True)
        self.thread.start()
        print(f"Каждые {AUDIO_INTERVAL_SECONDS} секунд: звук на системной громкости 100%.", flush=True)

    def _stop_player(self):
        if self.player is not None:
            if self.player.poll() is None:
                self.player.terminate()
                try:
                    self.player.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.player.kill()
                    self.player.wait()
            self.player = None

    def play_once(self):
        self._stop_player()
        # Громкость меняется для текущего системного устройства вывода.
        subprocess.run(
            ["/usr/bin/osascript", "-e", "set volume output volume 100 without output muted"],
            check=True, timeout=3, stdout=subprocess.DEVNULL,
        )
        if not self.stop_event.is_set():
            self.player = subprocess.Popen(
                ["/usr/bin/afplay", "-v", "1", str(AUDIO_FILE)],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            )

    def _run(self):
        next_play = time.monotonic() + AUDIO_INTERVAL_SECONDS
        try:
            while not self.stop_event.wait(max(0, next_play - time.monotonic())):
                try:
                    self.play_once()
                except (OSError, subprocess.SubprocessError) as error:
                    print(f"Не удалось воспроизвести звук ({type(error).__name__}); "
                          "повторю через 10 секунд.", file=sys.stderr, flush=True)
                next_play += AUDIO_INTERVAL_SECONDS
                # После сна не воспроизводим пропущенные запуски подряд.
                if next_play <= time.monotonic():
                    next_play = time.monotonic() + AUDIO_INTERVAL_SECONDS
        finally:
            self._stop_player()

    def close(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join()
