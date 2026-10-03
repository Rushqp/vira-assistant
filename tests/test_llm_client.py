"""LLMClient against a tiny fake OpenAI-compatible server (no real model needed)."""

import json
import socket

import pytest
from aiohttp import web

from app.llm.client import LLMClient, LLMError

LAST_REQUEST = web.AppKey("last_request", dict)


def _sse(data: dict) -> bytes:
    return f"data: {json.dumps(data)}\n\n".encode()


def _chunk(content: str | None) -> dict:
    delta = {"content": content} if content is not None else {}
    return {
        "id": "x",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "test",
        "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
    }


async def _completions(request: web.Request) -> web.StreamResponse:
    body = await request.json()
    if body["model"] == "missing":
        return web.json_response({"error": {"message": "model not found"}}, status=404)
    request.app[LAST_REQUEST].update(body)
    response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
    await response.prepare(request)
    for piece in ["سلام", "! ", None, "Hi"]:
        await response.write(_sse(_chunk(piece)))
    await response.write(b"data: [DONE]\n\n")
    return response


async def _models(request: web.Request) -> web.Response:
    return web.json_response(
        {"object": "list", "data": [{"id": "qwen2.5:3b", "object": "model", "owned_by": "x"}]}
    )


@pytest.fixture
async def server():
    app = web.Application()
    app[LAST_REQUEST] = {}
    app.router.add_post("/v1/chat/completions", _completions)
    app.router.add_get("/v1/models", _models)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    yield app, f"http://127.0.0.1:{port}/v1"
    await runner.cleanup()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def test_stream_chat_yields_pieces(server):
    app, url = server
    client = LLMClient(url, "key", "qwen2.5:3b")
    pieces = [p async for p in client.stream_chat([{"role": "user", "content": "hi"}])]
    assert pieces == ["سلام", "! ", "Hi"]
    assert app[LAST_REQUEST]["stream"] is True
    assert app[LAST_REQUEST]["messages"] == [{"role": "user", "content": "hi"}]
    await client.close()


async def test_chat_joins_pieces(server):
    _, url = server
    client = LLMClient(url, "key", "qwen2.5:3b")
    assert await client.chat([{"role": "user", "content": "hi"}]) == "سلام! Hi"
    await client.close()


async def test_missing_model(server):
    _, url = server
    client = LLMClient(url, "key", "missing")
    with pytest.raises(LLMError) as exc:
        await client.chat([{"role": "user", "content": "hi"}])
    assert exc.value.kind == "model_missing"
    await client.close()


async def test_unreachable_server():
    client = LLMClient(f"http://127.0.0.1:{_free_port()}/v1", "key", "m", timeout=2)
    with pytest.raises(LLMError) as exc:
        await client.chat([{"role": "user", "content": "hi"}])
    assert exc.value.kind == "unreachable"
    assert await client.check() is False
    await client.close()


async def test_check(server):
    _, url = server
    assert await LLMClient(url, "key", "qwen2.5:3b").check() is True
    assert await LLMClient(url, "key", "gemma3:1b").check() is False
