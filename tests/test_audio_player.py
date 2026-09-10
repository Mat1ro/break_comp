import subprocess
import unittest
from unittest.mock import Mock, patch

import audio_player


class AudioTests(unittest.TestCase):
    def test_immediate_play_after_shared_startup_delay(self):
        clock = [120.0]
        moments = []
        audio = audio_player.RepeatingAudio(initial_delay=0)

        def wait(delay):
            self.assertGreaterEqual(delay, 0)
            clock[0] += delay
            return len(moments) >= 3

        audio.stop_event = Mock()
        audio.stop_event.wait.side_effect = wait
        with patch.object(audio_player.time, "monotonic", lambda: clock[0]), \
                patch.object(audio, "play_once", side_effect=lambda: moments.append(clock[0])):
            audio._run()
        self.assertEqual(moments, [120.0, 130.0, 140.0])

    def test_first_play_at_ten_seconds_and_independent_period(self):
        clock = [0.0]
        moments = []
        audio = audio_player.RepeatingAudio()

        def wait(delay):
            self.assertGreaterEqual(delay, 0)
            clock[0] += delay
            return len(moments) >= 3

        def play():
            moments.append(clock[0])
            clock[0] += 0.2

        audio.stop_event = Mock()
        audio.stop_event.wait.side_effect = wait
        with patch.object(audio_player.time, "monotonic", lambda: clock[0]), \
                patch.object(audio, "play_once", side_effect=play):
            audio._run()
        self.assertEqual(moments, [10.0, 20.0, 30.0])

    def test_volume_and_unmute_before_playback(self):
        audio = audio_player.RepeatingAudio()
        calls = []
        with patch.object(audio_player.subprocess, "run", side_effect=lambda args, **kw: calls.append(args)), \
                patch.object(audio_player.subprocess, "Popen", side_effect=lambda args, **kw: calls.append(args)):
            audio.play_once()
        self.assertEqual(calls, [
            ["/usr/bin/osascript", "-e", "set volume output volume 100 without output muted"],
            ["/usr/bin/afplay", "-v", "1", str(audio_player.AUDIO_FILE)],
        ])

    def test_no_new_playback_after_stop_during_volume_change(self):
        audio = audio_player.RepeatingAudio()
        with patch.object(audio_player.subprocess, "run", side_effect=lambda *a, **k: audio.stop_event.set()), \
                patch.object(audio_player.subprocess, "Popen") as spawn:
            audio.play_once()
        spawn.assert_not_called()

    def test_worker_stops_playback_on_exit(self):
        audio = audio_player.RepeatingAudio()
        player = Mock()
        player.poll.return_value = None
        audio.player = player
        audio.stop_event.set()
        audio._run()
        player.terminate.assert_called_once()
        player.wait.assert_called_once_with(timeout=2)
        self.assertIsNone(audio.player)

    def test_old_playback_stops_before_next_one(self):
        audio = audio_player.RepeatingAudio()
        old = Mock()
        old.poll.return_value = None
        audio.player = old
        with patch.object(audio_player.subprocess, "run"), \
                patch.object(audio_player.subprocess, "Popen") as spawn:
            audio.play_once()
        old.terminate.assert_called_once()
        spawn.assert_called_once()

    def test_failed_volume_change_does_not_start_audio(self):
        audio = audio_player.RepeatingAudio()
        with patch.object(audio_player.subprocess, "run", side_effect=subprocess.TimeoutExpired("osascript", 3)), \
                patch.object(audio_player.subprocess, "Popen") as spawn:
            with self.assertRaises(subprocess.TimeoutExpired):
                audio.play_once()
        spawn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
