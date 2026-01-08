"""Basic LangGraph agent for handling LLM generation"""

import os
from typing import TypedDict

from langgraph.graph import StateGraph, START, END
# from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI


class AgentState(TypedDict):
    """State definition for the agent graph"""

    user_input: str
    output: str


class DuxAgent:
    """Agent that processes user input through an LLM using LangGraph"""

    def __init__(self, model_name: str = "gemini-2.5-flash") -> None:
        """Initialize the agent with an LLM and compiled graph

        Args:
            model_name: The name of the model to use
        """
        # self.llm = ChatOpenAI(model=model_name)
        self.llm = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=os.environ.get("GEMINI_KEY"),
        )
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build and compile the LangGraph workflow

        Returns:
            The compiled state graph
        """
        graph = StateGraph(AgentState)
        graph.add_node("generate", self._generate_node)
        graph.add_edge(START, "generate")
        graph.add_edge("generate", END)
        return graph.compile()

    async def _generate_node(self, state: AgentState) -> dict[str, str]:
        """Process user input through the LLM

        Args:
            state: The current agent state containing user input

        Returns:
            Dictionary with the generated output
        """
        response = await self.llm.ainvoke(state["user_input"])
        return {"output": response.content}

    async def generate(self, user_input: str) -> str:
        """Run the agent graph with the given user input

        Args:
            user_input: The user's input text

        Returns:
            The generated output from the LLM
        """
        result = await self.graph.ainvoke({"user_input": user_input, "output": ""})
        return result["output"]
