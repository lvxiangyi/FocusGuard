import os
os.environ["AIMONITOR_NO_BLOCKER_SINGLETON"] = "1"

import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import mvp_service as service
import session_manager as sessions
import settings_manager
import quiz_generator
from mvp_i18n import STRINGS, LANGUAGES


class ChallengeTests(unittest.TestCase):
    def setUp(self):
        self.manager = SimpleNamespace(active=True, should_block=True, session_id="session-a", block_id="block-a", acknowledge_block=Mock())
        self.store = service.ChallengeStore(self.manager)

    def test_six_target_languages_never_copy_source_language(self):
        for code, target in LANGUAGES.items():
            with patch.object(service, "load_settings", return_value={"practice_target_language": target}):
                challenge = self.store.get(replace=True)
                self.assertNotEqual(challenge["source_language"], code)
                self.assertEqual(challenge["target_language"], target)

    def test_return_requires_actual_pass(self):
        challenge = self.store.get()
        with self.assertRaises(ValueError):
            self.store.finish(challenge["challenge_id"])
        with patch.object(service, "grade_translation_answer", return_value={"accepted": True, "model": "test"}):
            self.store.grade(challenge["challenge_id"], "a valid translation")
        self.store.finish(challenge["challenge_id"])
        self.manager.acknowledge_block.assert_called_once()

    def test_revealing_answer_never_unlocks(self):
        challenge = self.store.get()
        with patch.object(service, "explain_translation", return_value={"accepted": True, "model": "test"}):
            self.store.grade(challenge["challenge_id"], "", skip=True)
        with self.assertRaises(ValueError):
            self.store.finish(challenge["challenge_id"])
        with self.assertRaises(ValueError):
            self.store.grade(challenge["challenge_id"], "copied answer")
        new = self.store.get(replace=True)
        self.assertNotEqual(new["source_text"], challenge["source_text"])
        self.assertFalse(new["accepted"])

    def test_connection_error_never_passes_or_skips(self):
        challenge = self.store.get()
        with patch.object(service, "grade_translation_answer", return_value={"accepted": True, "model": "api-error"}):
            with self.assertRaises(RuntimeError):
                self.store.grade(challenge["challenge_id"], "anything")
        self.assertFalse(self.store.current["accepted"])
        self.assertFalse(self.store.current["skipped"])

    def test_previous_block_and_session_answers_expire(self):
        challenge = self.store.get()
        self.manager.block_id = "block-b"
        with self.assertRaises(ValueError):
            self.store.grade(challenge["challenge_id"], "answer")
        self.manager.session_id = "session-b"
        with self.assertRaises(ValueError):
            self.store.finish(challenge["challenge_id"])
        self.manager.acknowledge_block.assert_not_called()

    def test_stop_during_ai_call_does_not_grant_pass(self):
        challenge = self.store.get()
        def slow_grade(*args, **kwargs):
            self.manager.active = False
            return {"accepted": True, "model": "test"}
        with patch.object(service, "grade_translation_answer", side_effect=slow_grade):
            with self.assertRaises(ValueError):
                self.store.grade(challenge["challenge_id"], "answer")
        self.manager.acknowledge_block.assert_not_called()

    def test_malformed_ai_boolean_is_not_truthy_pass(self):
        challenge = self.store.get()
        with patch.object(service, "grade_translation_answer", return_value={"accepted": "false", "model": "test"}):
            self.store.grade(challenge["challenge_id"], "answer")
        self.assertFalse(self.store.current["accepted"])


class FeedbackTests(unittest.TestCase):
    def test_pending_capture_identity_label_and_cache_invalidation(self):
        request = service.PendingFeedback(captured_at="capture-a", task="Task", label="off_task", reason="Unrelated browsing")
        with patch.object(service, "load_pending_capture", return_value={"captured_at": "capture-b"}):
            with self.assertRaises(service.HTTPException) as caught:
                service.pending_feedback(request)
            self.assertEqual(caught.exception.status_code, 409)
        with patch.object(service, "load_pending_capture", return_value={"captured_at": "capture-a"}), patch.object(service, "commit_pending_capture", return_value={"id": "sample"}) as commit, patch.object(service.session_manager, "invalidate_judgement_cache") as invalidate:
            service.pending_feedback(request)
            self.assertEqual(commit.call_args.kwargs["verdict"], "错")
            self.assertEqual(commit.call_args.kwargs["context"]["task"], "Task")
            invalidate.assert_called_once()

    def test_feedback_preserves_historical_task_and_does_not_unlock(self):
        import data_paths
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shot = root / "shot.jpg"
            shot.write_bytes(b"image")
            fake_store = Mock()
            fake_store.add_sample.return_value = {"id": "saved"}
            record = {"task": "original task", "screenshot_path": str(shot), "captured_at": "2026-09-06"}
            with patch.object(data_paths, "DATA_DIR", root), patch.object(service, "BenchStore", return_value=fake_store), patch.object(service.session_manager, "acknowledge_block") as unlock:
                service.save_feedback(record, "on_task", "This was research")
            payload = fake_store.add_sample.call_args.kwargs
            self.assertEqual(payload["task"], "original task")
            self.assertEqual(payload["split"], "train")
            unlock.assert_not_called()

    def test_missing_screenshot_cannot_become_case(self):
        with self.assertRaises(ValueError):
            service.save_feedback({"task": "x", "screenshot_path": ""}, "on_task", "context")

    def test_resources_have_all_six_languages(self):
        for key, values in STRINGS["copy"].items():
            self.assertEqual(len(values), 6, key)
            self.assertTrue(all(values), key)

    def test_settings_reject_unsupported_ui_language(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(settings_manager, "SETTINGS_FILE", Path(temp) / "settings.json"):
            for language in LANGUAGES:
                self.assertEqual(settings_manager.save_settings({"ui_language": language})["ui_language"], language)
            with self.assertRaises(ValueError):
                settings_manager.save_settings({"ui_language": "unknown"})


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_startup_does_not_start_hidden_features(self):
        import main
        with patch.object(main.auto_scheduler, "start") as schedule, patch.object(main.guardian_manager, "start") as guardian:
            await main.startup_event()
        schedule.assert_not_called()
        guardian.assert_not_called()

    async def test_end_dismisses_without_flow_prompt(self):
        manager = sessions.SessionManager()
        manager.session_id = "mvp-test"
        manager.active = True
        manager.start_time = time.time()
        with patch.object(sessions, "record_block"), patch.object(sessions, "blocker") as blocker:
            manager._finish_session("completed", notify=True)
        blocker.dismiss.assert_called_once()
        blocker.show_flow_prompt.assert_not_called()

    async def test_late_inflight_judgement_cannot_affect_replacement(self):
        import threading
        started, release = threading.Event(), threading.Event()
        manager = sessions.SessionManager()
        def judge(*args, **kwargs):
            started.set()
            release.wait(2)
            return {"on_task": False}
        with patch.object(sessions, "record_block"), patch.object(sessions, "capture_screenshot", return_value=("unused", None)), patch.object(sessions, "judge_screenshot", side_effect=judge), patch.object(sessions, "blocker") as blocker:
            blocker.is_showing = False
            manager.start_session("old", 25, 300)
            for _ in range(100):
                if started.is_set():
                    break
                await asyncio.sleep(.01)
            manager.stop_session()
            manager.task = "new"
            release.set()
            await asyncio.sleep(.05)
            self.assertFalse(manager.should_block)
            self.assertIsNone(manager.latest_judgement)


class HttpContractTests(unittest.TestCase):
    def test_overview_and_feedback_round_trip(self):
        from fastapi.testclient import TestClient
        from PIL import Image
        import main
        import data_paths
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            screenshot = root / "screen.jpg"
            Image.new("RGB", (64, 64), "white").save(screenshot)
            record = {"id": "history-1", "mode": "session", "task": "historical research", "screenshot_path": str(screenshot), "ai_label": "off_task"}
            with patch.dict(os.environ, {"PERSONAL_BENCH_ROOT": str(root / "bench")}), patch.object(data_paths, "DATA_DIR", root), patch.object(settings_manager, "SETTINGS_FILE", root / "settings.json"), patch.object(service, "recent_records", return_value=[record]), patch.object(service, "load_pending_capture", return_value=None):
                client = TestClient(main.app)
                response = client.get("/mvp/overview")
                self.assertEqual(response.status_code, 200)
                self.assertIn("model_options", response.json()["settings"])
                self.assertEqual(response.json()["samples"], [])
                saved = client.post("/mvp/feedback", json={"record_id": "history-1", "label": "on_task", "reason": "Research for this task"})
                self.assertEqual(saved.status_code, 200, saved.text)
                sample = saved.json()["sample"]
                self.assertEqual(sample["task"], "historical research")
                self.assertEqual(sample["human_label"], "on_task")
                self.assertEqual(len(client.get("/mvp/overview").json()["samples"]), 1)
                self.assertEqual(client.get(f"/personal-bench/samples/{sample['id']}/image").status_code, 200)
                self.assertEqual(client.delete(f"/personal-bench/samples/{sample['id']}").status_code, 200)
                self.assertEqual(client.get("/mvp/overview").json()["samples"], [])
                stale = client.post("/mvp/feedback", json={"record_id": "missing", "label": "on_task", "reason": "x"})
                self.assertEqual(stale.status_code, 404)


if __name__ == "__main__":
    unittest.main()
