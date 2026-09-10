import contextlib
import io
import unittest
from unittest.mock import Mock, call, patch

import wallpaper_controller as wallpaper


class WallpaperTests(unittest.TestCase):
    def setUp(self):
        self.desktop = Mock()
        self.desktop.screens.return_value = {10: 'left', 20: 'right'}
        self.desktop.image_url = 'new-image'
        self.desktop.picture_options.return_value = {'scaling': 'fit'}
        self.desktop.get.side_effect = lambda screen: ('old-' + screen, {'original': screen})
        for item in (
            patch.object(wallpaper.sys, 'platform', 'darwin'),
            patch.object(wallpaper, 'MacDesktop', return_value=self.desktop),
        ):
            item.start()
            self.addCleanup(item.stop)
        self.effect = wallpaper.TemporaryWallpaper()

    def test_restore_each_screen_by_identity_with_original_options(self):
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.effect.start()
            self.desktop.set.assert_has_calls([
                call('left', 'new-image', {'scaling': 'fit'}),
                call('right', 'new-image', {'scaling': 'fit'}),
            ])
            self.desktop.screens.return_value = {20: 'right-new-object', 10: 'left-new-object'}
            self.effect.close()
            self.assertEqual(self.desktop.set.call_args_list[2:], [
                call('left-new-object', 'old-left', {'original': 'left'}),
                call('right-new-object', 'old-right', {'original': 'right'}),
            ])
            self.effect.close()
            self.assertEqual(self.desktop.set.call_count, 4)
            self.assertEqual(stdout.getvalue(), '')

    def test_screen_is_not_changed_when_original_cannot_be_saved(self):
        self.desktop.get.side_effect = [RuntimeError, ('old-right', {})]
        with contextlib.redirect_stderr(io.StringIO()):
            self.effect.start()
        self.desktop.set.assert_called_once_with('right', 'new-image', {'scaling': 'fit'})
        self.effect.close()
        self.desktop.set.assert_called_with('right', 'old-right', {})

    def test_interrupt_during_write_still_restores_saved_wallpaper(self):
        self.desktop.set.side_effect = [KeyboardInterrupt, None]
        with self.assertRaises(KeyboardInterrupt):
            self.effect.start()
        self.effect.close()
        self.desktop.set.assert_called_with('left', 'old-left', {'original': 'left'})

    def test_one_restore_failure_does_not_prevent_other_restore(self):
        self.effect.start()
        self.desktop.set.side_effect = [RuntimeError, None]
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.effect.close()
        self.desktop.set.assert_called_with('right', 'old-right', {'original': 'right'})
        self.assertIn('восстановить', stderr.getvalue())
        self.assertFalse(self.effect.originals)

    def test_disconnected_screen_does_not_stop_restoration_of_remaining_screen(self):
        self.effect.start()
        self.desktop.screens.return_value = {20: 'right'}
        with contextlib.redirect_stderr(io.StringIO()):
            self.effect.close()
        self.assertEqual(self.desktop.set.call_count, 3)
        self.desktop.set.assert_called_with('right', 'old-right', {'original': 'right'})

    def test_no_change_before_start_on_other_systems_or_with_missing_asset(self):
        self.effect.close()
        with patch.object(wallpaper.sys, 'platform', 'win32'):
            self.effect.start()
            self.effect.close()
        with patch.object(wallpaper, 'WALLPAPER_FILE') as asset, \
                contextlib.redirect_stderr(io.StringIO()):
            asset.is_file.return_value = False
            self.effect.start()
            self.effect.close()
        self.desktop.set.assert_not_called()


if __name__ == '__main__':
    unittest.main()
