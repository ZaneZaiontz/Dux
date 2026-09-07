"""Tests for the Dux agent"""

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk
from langgraph.checkpoint.memory import InMemorySaver

from agents.dux_agent import (MAX_TOOL_CALLS, DuxAgent, build_model,
                              route_entry, route_research, route_verdict,
                              stream_event, supports_tool_calling)
from agents.endpoint import file_budget, select_loaded_model
from data.database import connection_string
from observability import setup_tracing
from workspace.sandbox import Workspace
from workspace.tools import build_tools


class StubStructured:
    """Structured-output stand-in that returns queued assessments"""

    def __init__(self, schema, verdicts):
        self.schema = schema
        self.verdicts = verdicts

    async def ainvoke(self, _messages):
        """Return the next queued assessment"""
        return self.schema(verdict=self.verdicts.pop(0), reason="stub")


class StubLLM:
    """LLM stand-in that returns queued replies without calling a provider"""

    def __init__(self, texts, verdicts=None):
        self.texts = list(texts)
        self.verdicts = list(verdicts or [])

    async def ainvoke(self, _messages):
        """Return the next queued reply"""
        queued = self.texts.pop(0)
        return queued if isinstance(queued, AIMessage) else AIMessage(
            content=queued
        )

    def with_structured_output(self, schema, method=None):
        """Return a stub that produces assessments of the given schema"""
        return StubStructured(schema, self.verdicts)

    def bind_tools(self, _tools):
        """Return the same stub, since queued replies already decide calls"""
        return self


def tool_call(name, args):
    """Build a model reply that asks for one tool call"""
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": f"call-{name}"}],
    )


async def state_after(agent, *turns):
    """Run turns through one conversation and return the resulting state"""
    for turn in turns:
        await agent.generate(turn, "t1")
    return await agent.graph.aget_state({"configurable": {"thread_id": "t1"}})


@pytest.fixture(name="project_tools")
def project_tools_fixture(tmp_path):
    (tmp_path / "main.py").write_text("def run():\n    return fetch()\n")
    return build_tools(Workspace(tmp_path))


@pytest.mark.parametrize("hypothesis,expected", [
    ("", "hypothesize"),
    ("Missing await", "assess"),
])
def test_route_entry_hypothesizes_only_when_needed(hypothesis, expected):
    assert route_entry({"hypothesis": hypothesis}) == expected


@pytest.mark.parametrize("verdict,revised,expected", [
    ("arrived", False, "affirm"),
    ("warm", False, "probe"),
    ("off_track", False, "probe"),
    ("direct_question", True, "answer"),
    ("direct_question", False, "hypothesize"),
    ("problem_changed", False, "hypothesize"),
    ("problem_changed", True, "probe"),
])
def test_route_verdict_picks_the_reply_and_guards_the_rebuild(
    verdict, revised, expected
):
    state = {"verdict": verdict, "revised_this_turn": revised}

    assert route_verdict(state) == expected


@pytest.mark.parametrize("pending,expected", [
    (True, "answer"),
    (False, "assess"),
])
def test_finished_research_goes_to_whoever_asked_for_it(pending, expected):
    state = {"research": [AIMessage(content="done")], "pending_answer": pending}

    assert route_research(state) == expected


@pytest.mark.asyncio
async def test_the_hypothesis_is_stored_but_never_shown():
    stub = StubLLM(["It is a missing await", "What does the call return?"],
                   ["off_track"])
    agent = DuxAgent(llm=stub, checkpointer=InMemorySaver())

    state = await state_after(agent, "my function returns a coroutine")

    assert state.values["hypothesis"] == "It is a missing await"
    assert "missing await" not in state.values["messages"][-1].content


@pytest.mark.asyncio
async def test_arriving_at_the_answer_returns_the_affirming_reply():
    stub = StubLLM(["It is a missing await", "Yes, that is exactly it"],
                   ["arrived"])
    agent = DuxAgent(llm=stub, checkpointer=InMemorySaver())

    reply = await agent.generate("I never awaited it", "t1")

    assert reply == "Yes, that is exactly it"


@pytest.mark.asyncio
async def test_the_second_turn_reuses_the_stored_hypothesis():
    stub = StubLLM(
        ["It is a missing await", "What does the call return?",
         "So what would await change?"],
        ["off_track", "warm"],
    )
    agent = DuxAgent(llm=stub, checkpointer=InMemorySaver())

    state = await state_after(agent, "returns a coroutine", "something weird")

    assert state.values["messages"][-1].content == "So what would await change?"
    assert not stub.texts


@pytest.mark.asyncio
async def test_code_is_read_for_the_hypothesis_but_kept_out_of_the_chat(
    project_tools
):
    stub = StubLLM(
        [tool_call("read_file", {"path": "main.py"}),
         "run forgets to await fetch",
         "What does fetch return?"],
        ["off_track"],
    )
    agent = DuxAgent(llm=stub, checkpointer=InMemorySaver(),
                     tools=project_tools)

    state = await state_after(agent, "my function returns the wrong thing")

    assert state.values["hypothesis"] == "run forgets to await fetch"
    assert "return fetch()" in str(state.values["research"])
    assert "return fetch()" not in str(state.values["messages"])


@pytest.mark.asyncio
async def test_investigation_stops_at_the_tool_call_cap(project_tools):
    stub = StubLLM(
        [tool_call("list_files", {}) for _ in range(MAX_TOOL_CALLS)]
        + ["giving up, likely a missing await", "What does fetch return?"],
        ["off_track"],
    )
    agent = DuxAgent(llm=stub, checkpointer=InMemorySaver(),
                     tools=project_tools)

    state = await state_after(agent, "my function returns the wrong thing")

    assert state.values["tool_calls_used"] == MAX_TOOL_CALLS
    assert state.values["hypothesis"] == "giving up, likely a missing await"


def test_connection_string_uses_the_configured_environment(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "zane")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("POSTGRES_HOST", "db")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("POSTGRES_DB", "dux_test")

    assert connection_string() == (
        "postgresql://zane:secret@db:5433/dux_test?sslmode=disable"
    )


class RefusingLLM(StubLLM):
    """Model stand-in for a server that rejects tool definitions"""

    def bind_tools(self, _tools):
        raise ValueError("this model does not support tools")


@pytest.mark.asyncio
async def test_a_tool_capable_model_is_detected(project_tools):
    assert await supports_tool_calling(StubLLM(["ok"]), project_tools) is True


@pytest.mark.asyncio
async def test_a_model_without_tool_support_is_detected(project_tools):
    assert await supports_tool_calling(RefusingLLM([]), project_tools) is False


def test_the_model_is_configured_from_the_environment(monkeypatch):
    monkeypatch.setenv("DUX_MODEL", "qwen3-coder")
    monkeypatch.setenv("DUX_MODEL_BASE_URL", "http://host.docker.internal:1234/v1")

    model = build_model()

    assert model.model_name == "qwen3-coder"
    assert model.openai_api_base == "http://host.docker.internal:1234/v1"


LOADED_LISTING = {
    "data": [
        {"id": "some/other-model", "state": "not-loaded",
         "max_context_length": 4096},
        {"id": "prism-ml/bonsai-27b", "state": "loaded",
         "max_context_length": 262144, "loaded_context_length": 100096,
         "capabilities": ["tool_use"]},
    ]
}


def test_the_loaded_model_is_picked_out_of_a_listing():
    found = select_loaded_model(LOADED_LISTING)

    assert found.name == "prism-ml/bonsai-27b"
    assert found.context_tokens == 100096
    assert found.supports_tools is True


def test_nothing_is_reported_when_no_model_is_loaded():
    assert select_loaded_model({"data": [{"id": "x", "state": "not-loaded"}]}) is None


@pytest.mark.parametrize("context_tokens,expected", [
    (100096, 100096),
    (32768, 32768),
])
def test_one_file_may_use_a_quarter_of_the_context_window(context_tokens,
                                                          expected):
    assert file_budget(context_tokens) == expected


def test_tracing_stays_off_when_no_collector_is_configured(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    assert setup_tracing() is False


@pytest.mark.parametrize("mode,chunk,expected", [
    ("updates", {"hypothesize": {}}, {"type": "step", "node": "hypothesize"}),
    ("messages", (AIMessageChunk(content="ask this"),
                  {"langgraph_node": "probe"}),
     {"type": "token", "text": "ask this"}),
    ("messages", (AIMessageChunk(content="the secret answer"),
                  {"langgraph_node": "hypothesize"}), None),
])
def test_only_spoken_nodes_reach_the_client(mode, chunk, expected):
    assert stream_event(mode, chunk) == expected
