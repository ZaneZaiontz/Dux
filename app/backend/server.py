"""Dux backend server"""

import json
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
import socketio
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from agents.dux_agent import (DEFAULT_BASE_URL, DuxAgent, build_model,
                              supports_tool_calling)
from agents.endpoint import discover_model, file_budget
from data.database import connection_string
from observability import setup_tracing
from workspace.tools import build_workspace_tools

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger("dux")

sio = socketio.AsyncServer(cors_allowed_origins="*", async_mode="asgi")


async def usable_tools(llm, info):
    """Pick the code tools only when the model can actually call them

    Args:
        llm: The chat model Dux is configured to use
        info: What the endpoint reports it has loaded

    Returns:
        The code reading tools, or None when they would go unused
    """
    budget = file_budget(info.context_tokens) if info else None
    tools = build_workspace_tools(max_file_bytes=budget)
    if not tools:
        return None
    if info and info.supports_tools is not None:
        capable = info.supports_tools
    else:
        capable = await supports_tool_calling(llm, tools)
    if not capable:
        LOGGER.warning(
            "Model %s will not accept tools, so Dux cannot read your code. "
            "It can still talk a problem through with you.",
            os.environ.get("DUX_MODEL", "local-model"),
        )
        return None
    return tools


class GenerateRequest(BaseModel):
    """Request model for the generate endpoint"""

    user_input: str
    conversation_id: str


class GenerateResponse(BaseModel):
    """Response model for the generate endpoint"""

    output: str


agent: DuxAgent | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown lifecycle

    Args:
        app: The FastAPI application instance

    Yields:
        None during the application's active period
    """
    global agent
    if setup_tracing():
        LOGGER.info("Tracing agent runs to the collector")
    async with AsyncPostgresSaver.from_conn_string(
        connection_string()
    ) as checkpointer:
        await checkpointer.setup()
        info = await discover_model(
            os.environ.get("DUX_MODEL_BASE_URL", DEFAULT_BASE_URL)
        )
        if info:
            LOGGER.info(
                "Serving %s with a context of %s tokens",
                info.name, info.context_tokens,
            )
        llm = build_model(info)
        agent = DuxAgent(
            llm=llm,
            checkpointer=checkpointer,
            tools=await usable_tools(llm, info),
        )
        yield
        agent = None


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/ws", socketio.ASGIApp(socketio_server=sio, socketio_path="socket.io"))


@app.get("/health")
async def health() -> dict[str, str]:
    """Check server health status.

    Returns:
        A dictionary containing the server status
    """
    return {"status": "healthy"}


@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest) -> GenerateResponse:
    """Generate a response from the LLM based on user input

    Args:
        request: The request containing user input

    Returns:
        The generated response from the LLM

    Raises:
        HTTPException: If the agent is not initialized
    """
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    output = await agent.generate(
        request.user_input, request.conversation_id
    )
    return GenerateResponse(output=output)



@app.post("/generate/stream")
async def generate_stream(request: GenerateRequest) -> StreamingResponse:
    """Stream a reply as it is produced

    Args:
        request: The request containing user input

    Returns:
        Server sent events carrying progress and reply text

    Raises:
        HTTPException: If the agent is not initialized
    """
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    async def events():
        async for event in agent.stream(
            request.user_input, request.conversation_id
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")

if __name__ == "__main__":
    port = int(os.environ.get("BACKEND_PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
