"""Временная смена обоев текущего рабочего стола на macOS."""

from pathlib import Path
import sys

WALLPAPER_FILE = Path(__file__).resolve().parent / "assets" / "poop.png"


class MacDesktop:
    def __init__(self):
        import AppKit
        from Foundation import NSURL

        self.appkit = AppKit
        self.workspace = AppKit.NSWorkspace.sharedWorkspace()
        self.image_url = NSURL.fileURLWithPath_(str(WALLPAPER_FILE))

    def screens(self):
        return {
            int(screen.deviceDescription()["NSScreenNumber"]): screen
            for screen in self.appkit.NSScreen.screens()
        }

    def get(self, screen):
        url = self.workspace.desktopImageURLForScreen_(screen)
        options = self.workspace.desktopImageOptionsForScreen_(screen)
        if url is None or options is None:
            raise RuntimeError("Не удалось сохранить прежние обои.")
        return url, dict(options)

    def set(self, screen, url, options):
        success, error = self.workspace.setDesktopImageURL_forScreen_options_error_(
            url, screen, options, None
        )
        if not success:
            raise RuntimeError("macOS не смогла изменить обои.")

    def picture_options(self):
        return {
            self.appkit.NSWorkspaceDesktopImageScalingKey: self.appkit.NSImageScaleProportionallyUpOrDown,
            self.appkit.NSWorkspaceDesktopImageAllowClippingKey: False,
        }


class TemporaryWallpaper:
    def __init__(self):
        self.desktop = None
        self.originals = {}

    def start(self):
        if sys.platform != "darwin" or self.desktop is not None:
            return
        if not WALLPAPER_FILE.is_file():
            print("Не найден файл assets/poop.png для обоев.", file=sys.stderr)
            return
        try:
            self.desktop = MacDesktop()
            screens = self.desktop.screens()
            options = self.desktop.picture_options()
        except Exception as error:
            print(f"Смена обоев недоступна ({type(error).__name__}).", file=sys.stderr)
            return
        for identifier, screen in screens.items():
            try:
                # Сохраняем до записи: даже прерывание во время системного вызова
                # должно оставить данные для восстановления в finally.
                self.originals[identifier] = self.desktop.get(screen)
                self.desktop.set(screen, self.desktop.image_url, options)
            except Exception as error:
                print(f"Не удалось изменить обои экрана ({type(error).__name__}).", file=sys.stderr)

    def close(self):
        if not self.originals:
            return
        try:
            screens = self.desktop.screens()
            for identifier, (url, options) in self.originals.items():
                try:
                    screen = screens.get(identifier)
                    if screen is None:
                        raise RuntimeError("Экран отключён.")
                    self.desktop.set(screen, url, options)
                except Exception as error:
                    print(f"Не удалось восстановить обои экрана ({type(error).__name__}).", file=sys.stderr)
        except Exception as error:
            print(f"Восстановление обоев недоступно ({type(error).__name__}).", file=sys.stderr)
        finally:
            self.originals.clear()
            self.desktop = None
