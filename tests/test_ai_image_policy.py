import json
import unittest

from app.ai_provider import _build_payload, _policy_prompt


class AIImagePolicyTests(unittest.TestCase):
    def test_external_payload_is_text_only(self):
        raw = _build_payload("hello")
        data = json.loads(raw.decode("utf-8"))
        text = json.dumps(data)
        self.assertNotIn("inline_data", text)
        self.assertNotIn("inlineData", text)
        self.assertEqual(len(data["contents"][0]["parts"]), 1)
        self.assertIn("text", data["contents"][0]["parts"][0])

    def test_policy_forbids_claiming_direct_visual_inspection(self):
        text = _policy_prompt("test", [])
        self.assertIn("hiçbir radyografi/fotoğraf pikseli", text)
        self.assertIn("TEK izinli kaynak", text)


if __name__ == "__main__":
    unittest.main()
