"""M08 measurement logic tests with a fake tokenizer, no model files/imports."""
import sys
import unittest
from count_qwen_prompt_tokens import MODEL, measure


class Tokenizer:
    def apply_chat_template(self, messages, **kwargs):
        assert kwargs == dict(tokenize=False, add_generation_prompt=True)
        return "template-plus-generation-prefix"

    def encode(self, text, **kwargs):
        assert text == "template-plus-generation-prefix"
        assert kwargs == dict(add_special_tokens=False)
        return [11, 12, 13]


class PromptTokensTests(unittest.TestCase):
    def fixture(self):
        return dict(model=MODEL, mode="fixture", status="validated_not_applied", calls=[
            dict(stage="action", context={"vehicle_id":3}, messages=[dict(role="system", content="test")])])

    def test_template_and_generation_prefix_counted_once(self):
        row = measure(Tokenizer(), self.fixture(), 2, 5)[0]
        self.assertEqual((row["input_tokens"], row["required_tokens"], row["remaining_tokens"]), (3, 5, 0))
        self.assertTrue(row["fits"])

    def test_over_budget_is_not_success(self):
        self.assertFalse(measure(Tokenizer(), self.fixture(), 3, 5)[0]["fits"])

    def test_wrong_model_or_failed_fixture_rejected(self):
        for key, value in (("model", "other"), ("status", "failed"), ("mode", "live")):
            fixture = self.fixture()
            fixture[key] = value
            with self.assertRaises(ValueError):
                measure(Tokenizer(), fixture, 2, 5)

    def test_invalid_messages_rejected(self):
        fixture = self.fixture()
        fixture["calls"][0]["messages"][0]["content"] = None
        with self.assertRaises(ValueError):
            measure(Tokenizer(), fixture, 2, 5)


if __name__ == "__main__":
    unittest.main(testRunner=unittest.TextTestRunner(stream=sys.stdout, verbosity=2))
