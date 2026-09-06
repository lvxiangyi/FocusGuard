import unittest

from whitelist import apply_whitelist_override, match_whitelist


class WhitelistOverrideTests(unittest.TestCase):
    def test_spotify_matches_listen_to_music(self):
        self.assertEqual(
            match_whitelist(
                "The user is on Spotify and viewing playlists",
                ["听音乐"],
            ),
            "听音乐",
        )

    def test_unrelated_activity_does_not_match(self):
        self.assertIsNone(match_whitelist("Writing Python in VS Code", ["听音乐"]))

    def test_override_forces_on_task(self):
        result = apply_whitelist_override(
            {
                "on_task": False,
                "should_interrupt": True,
                "current_activity": "Listening to music on a web-based music player (Spotify)",
                "reason": "This is entertainment.",
                "trigger_category": "none",
                "judgement_status": "ok",
            },
            ["听音乐"],
        )
        self.assertTrue(result["on_task"])
        self.assertFalse(result["should_interrupt"])
        self.assertEqual(result["whitelist_hit"], "听音乐")
        self.assertIn("Whitelist override", result["reason"])

    def test_hard_block_wins(self):
        result = apply_whitelist_override(
            {
                "on_task": False,
                "should_interrupt": True,
                "current_activity": "Spotify next to an adult website",
                "trigger_category": "adult",
                "judgement_status": "ok",
            },
            ["听音乐"],
        )
        self.assertFalse(result["on_task"])
        self.assertTrue(result["should_interrupt"])
        self.assertNotIn("whitelist_hit", result)


if __name__ == "__main__":
    unittest.main()
