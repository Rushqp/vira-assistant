"""The evaluation harness itself: a model doing the right thing passes, a wrong one fails."""

import importlib.util
import json
from pathlib import Path

from app.llm.client import LLMResponse, ToolCall

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("eval_agent", ROOT / "scripts" / "eval_agent.py")
eval_agent = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(eval_agent)  # type: ignore[union-attr]


class ScriptedModel:
    name = "scripted"
    model = "scripted"
    supports_tools = True

    def __init__(self, steps):
        self.steps = list(steps)

    async def respond(self, messages, tools=None, on_text=None, temperature=0.3):
        return self.steps.pop(0) if self.steps else LLMResponse(content="done", provider="x")

    async def close(self):
        pass


def tool(name, **args):
    return LLMResponse(tool_calls=[ToolCall("c1", name, json.dumps(args, ensure_ascii=False))])


def case(case_id):
    return next(c for c in eval_agent.CASES if c.id == case_id)


async def test_correct_model_passes(config):
    model = ScriptedModel(
        [
            tool(
                "add_expenses",
                items=[
                    {"description": "سیگار", "amount_text": "۱۵۰ هزار تومن"},
                    {"description": "ماست", "amount_text": "۲۰۰ هزار تومن"},
                    {"description": "آب", "amount_text": "۵۰ هزار تومن"},
                ],
            )
        ]
    )
    ok, detail, _ = await eval_agent.run_case(case("purchases"), model, config)
    assert ok, detail


async def test_wrong_model_fails(config):
    model = ScriptedModel(
        [tool("add_expenses", items=[{"description": "خرید", "amount_text": "۳ تومن"}])]
    )
    ok, detail, _ = await eval_agent.run_case(case("purchases"), model, config)
    assert not ok and "expenses" in detail


async def test_follow_up_case_has_its_setup(config):
    model = ScriptedModel([tool("cancel_reminders", query="دکتر")])
    ok, detail, _ = await eval_agent.run_case(case("cancel-follow-up"), model, config)
    assert ok, detail
