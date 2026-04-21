"""
Unit tests for Judge Model B and the Multi-Judge Consensus layer.

These tests use ``unittest.mock`` to inject fake AsyncOpenAI clients /
judges, so they run fully offline - no API key required. There is one
optional integration test at the bottom that only runs when a real
``SHOPAIKEY_API_KEY`` is set (otherwise skipped), so the test suite is
safe to share/run on any machine.

Run:
    python -m unittest tests.test_llm_judge_b -v
"""

import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.llm_judge import LLMJudge as ConsensusJudge, cohen_kappa
from engine.llm_judge_b import LLMJudge as LLMJudgeB


def _fake_openai_response(payload: dict):
    """Build an object that mimics the shape OpenAI's SDK returns."""
    message = SimpleNamespace(content=json.dumps(payload))
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


def _fake_client(payload: dict):
    """AsyncOpenAI mock where ``chat.completions.create`` returns ``payload``."""
    create = AsyncMock(return_value=_fake_openai_response(payload))
    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )


def _fake_judge(final_score: float, accuracy: int, tone: int, model: str = "fake"):
    """Build a mock judge object exposing the ``evaluate_multi_judge`` coroutine."""
    judge = SimpleNamespace()
    judge.evaluate_multi_judge = AsyncMock(
        return_value={
            "model": model,
            "final_score": final_score,
            "criteria": {
                "accuracy": {"score": accuracy, "reasoning": ""},
                "tone": {"score": tone, "reasoning": ""},
                "safety": {"verdict": "pass", "reasoning": ""},
            },
            "individual_scores": {model: final_score},
            "reasoning": "",
        }
    )
    return judge


class TestJudgeBInit(unittest.TestCase):
    def test_missing_api_key_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("engine.llm_judge_b._locate_dotenv", return_value=""):
                with patch("engine.llm_judge_b.load_dotenv", lambda *a, **k: None):
                    with self.assertRaises(ValueError):
                        LLMJudgeB()

    def test_injected_client_skips_api_key_check(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("engine.llm_judge_b._locate_dotenv", return_value=""):
                with patch("engine.llm_judge_b.load_dotenv", lambda *a, **k: None):
                    judge = LLMJudgeB(
                        client=_fake_client({}),
                        model="test-model-b",
                    )
        self.assertEqual(judge.model, "test-model-b")
        self.assertIn("accuracy", judge.rubrics)
        self.assertIn("tone", judge.rubrics)
        self.assertIn("safety", judge.rubrics)

    def test_uses_env_model_b(self):
        env = {"SHOPAIKEY_API_KEY": "fake", "JUDGE_MODEL_B": "env-model-b"}
        with patch.dict(os.environ, env, clear=True):
            with patch("engine.llm_judge_b._locate_dotenv", return_value=""):
                with patch("engine.llm_judge_b.load_dotenv", lambda *a, **k: None):
                    with patch("engine.llm_judge_b.AsyncOpenAI", return_value=object()):
                        judge = LLMJudgeB()
        self.assertEqual(judge.model, "env-model-b")

    def test_auto_loads_key_from_dotenv_file(self):
        """
        When SHOPAIKEY_API_KEY is not in os.environ but lives in a .env
        file on disk, the judge should still find it automatically via
        ``_locate_dotenv``.
        """
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            env_path = os.path.join(tmp, ".env")
            with open(env_path, "w") as f:
                f.write("SHOPAIKEY_API_KEY=from-dotenv-file\n")
                f.write("JUDGE_MODEL_B=from-dotenv-model\n")

            with patch.dict(os.environ, {}, clear=True):
                with patch(
                    "engine.llm_judge_b._locate_dotenv",
                    return_value=env_path,
                ):
                    with patch(
                        "engine.llm_judge_b.AsyncOpenAI",
                        return_value=object(),
                    ) as mock_openai:
                        judge = LLMJudgeB()

        self.assertEqual(judge.model, "from-dotenv-model")
        mock_openai.assert_called_once()
        kwargs = mock_openai.call_args.kwargs
        self.assertEqual(kwargs.get("api_key"), "from-dotenv-file")

    def test_locate_dotenv_finds_project_env_from_any_cwd(self):
        """
        Running Python from an unrelated cwd (like /tmp) should still
        locate the project's .env because ``_locate_dotenv`` walks up
        from the module file.
        """
        from engine.llm_judge_b import _locate_dotenv

        original_cwd = os.getcwd()
        try:
            os.chdir("/tmp")
            path = _locate_dotenv()
        finally:
            os.chdir(original_cwd)

        self.assertTrue(path.endswith(".env"), f"unexpected path: {path!r}")
        self.assertTrue(os.path.isfile(path))


class TestJudgeBEvaluate(unittest.IsolatedAsyncioTestCase):
    async def test_evaluate_multi_judge_happy_path(self):
        payload = {
            "accuracy": {"score": 4, "reasoning": "mostly correct"},
            "tone": {"score": 5, "reasoning": "clear"},
            "safety": {"verdict": "pass", "reasoning": "ok"},
            "overall_reasoning": "solid answer",
        }
        judge = LLMJudgeB(client=_fake_client(payload), model="fake-b")
        out = await judge.evaluate_multi_judge("q?", "a", "gt")

        self.assertEqual(out["model"], "fake-b")
        self.assertEqual(out["criteria"]["accuracy"]["score"], 4)
        self.assertEqual(out["criteria"]["tone"]["score"], 5)
        self.assertEqual(out["criteria"]["safety"]["verdict"], "pass")
        self.assertEqual(out["final_score"], 4.5)
        self.assertIn("fake-b", out["individual_scores"])

    async def test_safety_fail_caps_score_at_2(self):
        payload = {
            "accuracy": {"score": 5, "reasoning": ""},
            "tone": {"score": 5, "reasoning": ""},
            "safety": {"verdict": "fail", "reasoning": "unsafe"},
            "overall_reasoning": "",
        }
        judge = LLMJudgeB(client=_fake_client(payload), model="fake-b")
        out = await judge.evaluate_multi_judge("q?", "a", "gt")
        self.assertEqual(out["final_score"], 2.0)
        self.assertEqual(out["criteria"]["safety"]["verdict"], "fail")

    async def test_scores_are_clamped_into_1_5(self):
        payload = {
            "accuracy": {"score": 9, "reasoning": ""},
            "tone": {"score": -3, "reasoning": ""},
            "safety": {"verdict": "pass", "reasoning": ""},
        }
        judge = LLMJudgeB(client=_fake_client(payload), model="fake-b")
        out = await judge.evaluate_multi_judge("q?", "a", "gt")
        self.assertEqual(out["criteria"]["accuracy"]["score"], 5)
        self.assertEqual(out["criteria"]["tone"]["score"], 1)


class TestCohenKappa(unittest.TestCase):
    def test_perfect_agreement(self):
        self.assertEqual(cohen_kappa([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]), 1.0)

    def test_perfect_disagreement(self):
        k = cohen_kappa([1, 1, 1, 1], [5, 5, 5, 5])
        self.assertEqual(k, 0.0)

    def test_partial_agreement_is_between_0_and_1(self):
        k = cohen_kappa([1, 2, 3, 4], [1, 2, 3, 5])
        self.assertIsNotNone(k)
        self.assertGreater(k, 0.0)
        self.assertLess(k, 1.0)

    def test_returns_none_when_too_few_samples(self):
        self.assertIsNone(cohen_kappa([], []))
        self.assertIsNone(cohen_kappa([3], [3]))

    def test_mismatched_lengths_raise(self):
        with self.assertRaises(ValueError):
            cohen_kappa([1, 2], [1])


class TestConsensus(unittest.IsolatedAsyncioTestCase):
    async def test_low_disagreement_uses_average(self):
        a = _fake_judge(final_score=4.0, accuracy=4, tone=4, model="A")
        b = _fake_judge(final_score=4.5, accuracy=5, tone=4, model="B")
        judge = ConsensusJudge(judge_a=a, judge_b=b)

        out = await judge.evaluate_multi_judge("q?", "ans", "gt")

        self.assertEqual(out["consensus_method"], "average")
        self.assertEqual(out["final_score"], round((4.0 + 4.5) / 2, 2))
        self.assertIsNone(out["tie_breaker_score"])
        self.assertEqual(out["individual_scores"], {"A": 4.0, "B": 4.5})
        self.assertAlmostEqual(out["agreement_rate"], 1.0 - (0.5 / 4.0))

    async def test_high_disagreement_without_tie_breaker_uses_weighted(self):
        a = _fake_judge(final_score=5.0, accuracy=5, tone=5, model="A")
        b = _fake_judge(final_score=2.0, accuracy=2, tone=2, model="B")
        judge = ConsensusJudge(judge_a=a, judge_b=b)

        out = await judge.evaluate_multi_judge("q?", "ans", "gt")

        self.assertEqual(out["consensus_method"], "weighted_conservative")
        self.assertIsNone(out["tie_breaker_score"])
        expected = round(0.7 * 2.0 + 0.3 * 5.0, 2)
        self.assertEqual(out["final_score"], expected)

    async def test_high_disagreement_with_tie_breaker(self):
        a = _fake_judge(final_score=5.0, accuracy=5, tone=5, model="A")
        b = _fake_judge(final_score=2.0, accuracy=2, tone=2, model="B")
        tb = _fake_judge(final_score=3.0, accuracy=3, tone=3, model="TB")
        judge = ConsensusJudge(judge_a=a, judge_b=b, tie_breaker=tb)

        out = await judge.evaluate_multi_judge("q?", "ans", "gt")

        self.assertEqual(out["consensus_method"], "tie_breaker_third_judge")
        self.assertEqual(out["tie_breaker_score"], 3.0)
        self.assertEqual(out["final_score"], round((5.0 + 2.0 + 3.0) / 3, 2))
        tb.evaluate_multi_judge.assert_awaited_once()

    async def test_cohen_kappa_is_cumulative_across_calls(self):
        a = _fake_judge(final_score=4.0, accuracy=4, tone=4, model="A")
        b = _fake_judge(final_score=4.0, accuracy=4, tone=4, model="B")
        judge = ConsensusJudge(judge_a=a, judge_b=b)

        out1 = await judge.evaluate_multi_judge("q1", "a1", "gt1")
        self.assertIsNone(out1["cohen_kappa"]["accuracy"])

        out2 = await judge.evaluate_multi_judge("q2", "a2", "gt2")
        self.assertEqual(out2["cohen_kappa"]["accuracy"], 1.0)

        stats = judge.aggregate_stats()
        self.assertEqual(stats["num_samples"], 2)
        self.assertEqual(stats["cohen_kappa"]["accuracy"], 1.0)
        self.assertAlmostEqual(stats["avg_agreement_rate"], 1.0)

    async def test_judges_run_in_parallel(self):
        a = _fake_judge(final_score=4.0, accuracy=4, tone=4, model="A")
        b = _fake_judge(final_score=4.0, accuracy=4, tone=4, model="B")
        judge = ConsensusJudge(judge_a=a, judge_b=b)

        await judge.evaluate_multi_judge("q", "ans", "gt")

        a.evaluate_multi_judge.assert_awaited_once_with("q", "ans", "gt")
        b.evaluate_multi_judge.assert_awaited_once_with("q", "ans", "gt")


class TestAggregateStatsEmpty(unittest.TestCase):
    def test_empty_aggregate(self):
        a = _fake_judge(final_score=4.0, accuracy=4, tone=4, model="A")
        b = _fake_judge(final_score=4.0, accuracy=4, tone=4, model="B")
        judge = ConsensusJudge(judge_a=a, judge_b=b)
        stats = judge.aggregate_stats()
        self.assertEqual(stats["num_samples"], 0)
        self.assertIsNone(stats["avg_agreement_rate"])
        self.assertIsNone(stats["cohen_kappa"]["accuracy"])


@unittest.skipUnless(
    os.getenv("SHOPAIKEY_API_KEY") and os.getenv("RUN_INTEGRATION") == "1",
    "Integration test: set SHOPAIKEY_API_KEY and RUN_INTEGRATION=1 to enable.",
)
class TestJudgeBIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_live_api_call(self):
        judge = LLMJudgeB()
        out = await judge.evaluate_multi_judge(
            question="What is 2 + 2?",
            answer="The answer is 4.",
            ground_truth="4",
        )
        self.assertIn("final_score", out)
        self.assertGreaterEqual(out["final_score"], 1)
        self.assertLessEqual(out["final_score"], 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
