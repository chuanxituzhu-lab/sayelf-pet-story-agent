import unittest
import uuid

from webui import server


class GenerationLimitTests(unittest.TestCase):
    def setUp(self):
        self.visitor_id = "test-visitor-" + uuid.uuid4().hex

    def tearDown(self):
        server.USAGE_REGISTRY.pop(self.visitor_id, None)
        server.save_json_object(server.USAGE_PATH, server.USAGE_REGISTRY)

    def test_one_video_and_two_images_are_reserved_per_day(self):
        existing, error = server.reserve_quota(self.visitor_id, 2, "request-1")
        self.assertIsNone(existing)
        self.assertIsNone(error)

        quota = server.quota_snapshot(self.visitor_id)
        self.assertEqual(quota["videos_used"], 1)
        self.assertEqual(quota["videos_remaining"], 0)
        self.assertEqual(quota["images_used"], 2)
        self.assertEqual(quota["images_remaining"], 0)

        existing, error = server.reserve_quota(self.visitor_id, 0, "request-2")
        self.assertIsNone(existing)
        self.assertEqual(error["error"], "DAILY_VIDEO_LIMIT")

    def test_idempotency_returns_no_second_reservation(self):
        server.reserve_quota(self.visitor_id, 1, "same-request")
        server.remember_generation(self.visitor_id, "same-request", {"generation_id": "video-test"})
        existing, error = server.reserve_quota(self.visitor_id, 1, "same-request")
        self.assertEqual(existing["generation_id"], "video-test")
        self.assertIsNone(error)
        self.assertEqual(server.quota_snapshot(self.visitor_id)["videos_used"], 1)


if __name__ == "__main__":
    unittest.main()
