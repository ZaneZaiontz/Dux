"""Dux backend server"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
import socketio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from agents.dux_agent import DuxAgent, build_gemini
from data.database import connection_string
from workspace.tools import build_workspace_tools

sio = socketio.AsyncServer(cors_allowed_origins="*", async_mode="asgi")


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
    async with AsyncPostgresSaver.from_conn_string(
        connection_string()
    ) as checkpointer:
        await checkpointer.setup()
        agent = DuxAgent(
            llm=build_gemini(),
            checkpointer=checkpointer,
            tools=build_workspace_tools(),
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


if __name__ == "__main__":
    port = int(os.environ.get("BACKEND_PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
