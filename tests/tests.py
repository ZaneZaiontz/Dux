"""Tests for the Dux agent"""

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from agents.dux_agent import DuxAgent, route_entry, route_verdict
from data.database import connection_string


def test_route_entry_hypothesizes_when_no_hypothesis_yet():
    state = {"hypothesis": "", "verdict": "", "revised_this_turn": False}
    assert route_entry(state) == "hypothesize"


def test_route_entry_assesses_when_hypothesis_exists():
    state = {"hypothesis": "Missing await", "verdict": "",
             "revised_this_turn": False}
    assert route_entry(state) == "assess"


def test_route_verdict_affirms_when_user_arrived():
    state = {"hypothesis": "Missing await", "verdict": "arrived",
             "revised_this_turn": False}
    assert route_verdict(state) == "affirm"


def test_route_verdict_probes_when_user_is_warm():
    state = {"hypothesis": "Missing await", "verdict": "warm",
             "revised_this_turn": False}
    assert route_verdict(state) == "probe"


def test_route_verdict_probes_when_user_is_off_track():
    state = {"hypothesis": "Missing await", "verdict": "off_track",
             "revised_this_turn": False}
    assert route_verdict(state) == "probe"


def test_route_verdict_rebuilds_hypothesis_when_problem_changed():
    state = {"hypothesis": "Missing await", "verdict": "problem_changed",
             "revised_this_turn": False}
    assert route_verdict(state) == "hypothesize"


def test_route_verdict_stops_rebuilding_after_one_revision():
    state = {"hypothesis": "Missing await", "verdict": "problem_changed",
             "revised_this_turn": True}
    assert route_verdict(state) == "probe"


class StubStructured:
    """Structured-output stand-in that returns queued assessments"""

    def __init__(self, schema, verdicts):
        self.schema = schema
        self.verdicts = verdicts

    async def ainvoke(self, _messages):
        """Return the next queued assessment"""
        return self.schema(verdict=self.verdicts.pop(0), reason="stub")


class StubLLM:
    """LLM stand-in that returns queued text without calling a provider"""

    def __init__(self, texts, verdicts=None):
        self.texts = list(texts)
        self.verdicts = list(verdicts or [])

    async def ainvoke(self, _messages):
        """Return the next queued reply"""
        return AIMessage(content=self.texts.pop(0))

    def with_structured_output(self, schema):
        """Return a stub that produces assessments of the given schema"""
        return StubStructured(schema, self.verdicts)


def build_agent(stub):
    return DuxAgent(llm=stub, checkpointer=InMemorySaver())


@pytest.mark.asyncio
async def test_first_turn_keeps_the_hypothesis_out_of_the_reply():
    stub = StubLLM(["It is a missing await", "What does the call return?"],
                   ["off_track"])
    agent = build_agent(stub)

    reply = await agent.generate("my function returns a coroutine", "t1")

    assert reply == "What does the call return?"
    assert "missing await" not in reply


@pytest.mark.asyncio
async def test_first_turn_stores_the_hypothesis_in_state():
    stub = StubLLM(["It is a missing await", "What does the call return?"],
                   ["off_track"])
    agent = build_agent(stub)

    await agent.generate("my function returns a coroutine", "t1")
    state = await agent.graph.aget_state(
        {"configurable": {"thread_id": "t1"}}
    )

    assert state.values["hypothesis"] == "It is a missing await"


@pytest.mark.asyncio
async def test_arriving_at_the_answer_returns_the_affirming_reply():
    stub = StubLLM(["It is a missing await", "Yes, that is exactly it"],
                   ["arrived"])
    agent = build_agent(stub)

    reply = await agent.generate("I never awaited it", "t1")

    assert reply == "Yes, that is exactly it"


@pytest.mark.asyncio
async def test_second_turn_reuses_the_stored_hypothesis():
    stub = StubLLM(
        ["It is a missing await", "What does the call return?",
         "So what would await change?"],
        ["off_track", "warm"],
    )
    agent = build_agent(stub)

    first = await agent.generate("my function returns a coroutine", "t1")
    second = await agent.generate("it returns something weird", "t1")

    assert [first, second] == ["What does the call return?",
                               "So what would await change?"]
    assert not stub.texts


def test_connection_string_uses_the_configured_environment(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "zane")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("POSTGRES_HOST", "db")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("POSTGRES_DB", "dux_test")

    assert connection_string() == (
        "postgresql://zane:secret@db:5433/dux_test?sslmode=disable"
    )
