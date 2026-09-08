"""Discovery of what a model endpoint is currently serving"""

from dataclasses import dataclass

import httpx

DEFAULT_CONTEXT_TOKENS = 8192
CHARACTERS_PER_TOKEN = 4
FILE_SHARE_OF_CONTEXT = 4
DISCOVERY_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class ModelInfo:
    """What an endpoint reports about the model it has loaded"""

    name: str
    context_tokens: int
    supports_tools: bool | None = None


def select_loaded_model(payload: dict) -> ModelInfo | None:
    """Pick the loaded model out of an LM Studio style listing

    Args:
        payload: The decoded response from the endpoint

    Returns:
        The loaded model, or None when the endpoint has none
    """
    for entry in payload.get("data", []):
        if entry.get("state") != "loaded":
            continue
        context = (
            entry.get("loaded_context_length")
            or entry.get("max_context_length")
            or DEFAULT_CONTEXT_TOKENS
        )
        capabilities = entry.get("capabilities")
        return ModelInfo(
            name=entry["id"],
            context_tokens=context,
            supports_tools=(
                "tool_use" in capabilities if capabilities is not None else None
            ),
        )
    return None


def file_budget(context_tokens: int) -> int:
    """Decide how many bytes of one file may be spent on the context window

    Args:
        context_tokens: The context length the model was loaded with

    Returns:
        The most bytes a single file read should return
    """
    return context_tokens * CHARACTERS_PER_TOKEN // FILE_SHARE_OF_CONTEXT


async def discover_model(base_url: str) -> ModelInfo | None:
    """Ask an endpoint which model it has loaded, if it will say

    Only LM Studio style servers answer this. Anything else, including every
    hosted provider, simply returns nothing and leaves the configured values
    in charge.

    Args:
        base_url: The OpenAI compatible base URL, ending in /v1

    Returns:
        The loaded model, or None when the endpoint does not report one
    """
    url = base_url.rstrip("/").removesuffix("/v1") + "/api/v0/models"
    try:
        async with httpx.AsyncClient(
            timeout=DISCOVERY_TIMEOUT_SECONDS
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return select_loaded_model(response.json())
    except Exception:
        return None
