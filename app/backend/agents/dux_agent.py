"""LangGraph agent that guides a developer toward their own answer"""

import os
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import (AnyMessage, HumanMessage,
                                     RemoveMessage, SystemMessage)
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import REMOVE_ALL_MESSAGES, add_messages
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

from prompts.dux_prompts_base import DuxPromptsBase

Verdict = Literal["off_track", "warm", "arrived", "problem_changed"]

MAX_TOOL_CALLS = 8


class Assessment(BaseModel):
    """How close the developer's latest turn came to the hypothesis"""

    verdict: Verdict = Field(description="How close the developer is")
    reason: str = Field(description="One line explaining the verdict")


class AgentState(TypedDict):
    """State definition for the agent graph"""

    messages: Annotated[list[AnyMessage], add_messages]
    research: Annotated[list[AnyMessage], add_messages]
    hypothesis: str
    verdict: str
    revised_this_turn: bool
    tool_calls_used: int


def route_entry(state: AgentState) -> str:
    """Pick the first node of a turn based on whether a hypothesis exists

    Args:
        state: The current agent state

    Returns:
        The name of the node to run first
    """
    return "hypothesize" if not state.get("hypothesis") else "assess"


def route_verdict(state: AgentState) -> str:
    """Pick the reply node, allowing one hypothesis rebuild per turn

    Args:
        state: The current agent state

    Returns:
        The name of the node to run next
    """
    if state["verdict"] == "arrived":
        return "affirm"
    if state["verdict"] == "problem_changed" and not state["revised_this_turn"]:
        return "hypothesize"
    return "probe"


def route_research(state: AgentState) -> str:
    """Send the agent back to its tools while it still wants to read code

    Args:
        state: The current agent state

    Returns:
        The name of the node to run next
    """
    latest = state["research"][-1]
    return "research_tools" if getattr(latest, "tool_calls", None) else "assess"


def build_gemini(
    model_name: str = "gemini-2.5-flash",
) -> ChatGoogleGenerativeAI:
    """Build the Gemini chat model used in production

    Args:
        model_name: The name of the model to use

    Returns:
        A configured Gemini chat model
    """
    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=os.environ.get("GEMINI_KEY"),
    )


class DuxAgent:
    """Agent that guides a developer to their own answer through questions"""

    def __init__(self, llm, checkpointer, tools=None) -> None:
        """Initialize the agent with a chat model, storage and code tools

        Args:
            llm: The chat model used by every node
            checkpointer: The LangGraph checkpointer holding thread history
            tools: Code reading tools, or None when no project is mounted
        """
        self.llm = llm
        self.investigator = llm.bind_tools(tools) if tools else llm
        self.graph = self._build_graph(checkpointer, tools)

    def _build_graph(self, checkpointer, tools):
        """Build and compile the LangGraph workflow

        Args:
            checkpointer: The LangGraph checkpointer holding thread history
            tools: Code reading tools, or None when no project is mounted

        Returns:
            The compiled state graph
        """
        graph = StateGraph(AgentState)
        graph.add_node("hypothesize", self._hypothesize_node)
        graph.add_node("assess", self._assess_node)
        graph.add_node("probe", self._probe_node)
        graph.add_node("affirm", self._affirm_node)
        graph.add_conditional_edges(START, route_entry,
                                    ["hypothesize", "assess"])
        if tools:
            graph.add_node("research_tools",
                           ToolNode(tools, messages_key="research"))
            graph.add_conditional_edges("hypothesize", route_research,
                                        ["research_tools", "assess"])
            graph.add_edge("research_tools", "hypothesize")
        else:
            graph.add_edge("hypothesize", "assess")
        graph.add_conditional_edges("assess", route_verdict,
                                    ["probe", "affirm", "hypothesize"])
        graph.add_edge("probe", END)
        graph.add_edge("affirm", END)
        return graph.compile(checkpointer=checkpointer)

    async def _hypothesize_node(self, state: AgentState) -> dict:
        """Form the private answer Dux will guide the developer toward

        Args:
            state: The current agent state

        Returns:
            Either the next tool request or the finished hypothesis
        """
        used = state.get("tool_calls_used", 0)
        model = self.investigator if used < MAX_TOOL_CALLS else self.llm
        prompt = [SystemMessage(DuxPromptsBase.hypothesize_prompt)]
        response = await model.ainvoke(
            prompt + state["messages"] + state.get("research", [])
        )

        if getattr(response, "tool_calls", None):
            return {"research": [response], "tool_calls_used": used + 1}
        return {
            "research": [response],
            "hypothesis": response.content,
            "revised_this_turn": True,
        }

    async def _assess_node(self, state: AgentState) -> dict:
        """Judge how close the developer's latest turn came to the hypothesis

        Args:
            state: The current agent state

        Returns:
            The verdict driving the reply
        """
        grader = self.llm.with_structured_output(Assessment)
        instructions = DuxPromptsBase.assess_prompt.format(
            hypothesis=state["hypothesis"]
        )
        assessment = await grader.ainvoke(
            [SystemMessage(instructions)] + state["messages"]
        )
        if assessment.verdict == "problem_changed":
            return {
                "verdict": assessment.verdict,
                "research": [RemoveMessage(id=REMOVE_ALL_MESSAGES)],
                "tool_calls_used": 0,
            }
        return {"verdict": assessment.verdict}

    async def _probe_node(self, state: AgentState) -> dict:
        """Ask the question that moves the developer one step closer

        Args:
            state: The current agent state

        Returns:
            The reply to append to the conversation
        """
        return await self._reply(state, DuxPromptsBase.probe_prompt)

    async def _affirm_node(self, state: AgentState) -> dict:
        """Confirm the developer reached the answer and say why it holds

        Args:
            state: The current agent state

        Returns:
            The reply to append to the conversation
        """
        return await self._reply(state, DuxPromptsBase.affirm_prompt)

    async def _reply(self, state: AgentState, template: str) -> dict:
        """Generate a reply from a prompt template holding the hypothesis

        Args:
            state: The current agent state
            template: The prompt template for this kind of reply

        Returns:
            The reply to append to the conversation
        """
        instructions = template.format(hypothesis=state["hypothesis"])
        response = await self.llm.ainvoke(
            [SystemMessage(instructions)] + state["messages"]
        )
        return {"messages": [response]}

    async def generate(self, user_input: str, conversation_id: str) -> str:
        """Run one turn of the conversation

        Args:
            user_input: The developer's message
            conversation_id: The thread this message belongs to

        Returns:
            Dux's reply
        """
        result = await self.graph.ainvoke(
            {
                "messages": [HumanMessage(user_input)],
                "revised_this_turn": False,
                "tool_calls_used": 0,
            },
            {"configurable": {"thread_id": conversation_id}},
        )
        return result["messages"][-1].content
