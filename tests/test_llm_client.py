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


TOOL_CALL = {
    "id": "call_1",
    "type": "function",
    "function": {"name": "add_expenses", "arguments": '{"items": []}'},
}


def _completion(message: dict) -> dict:
    return {
        "id": "x",
        "object": "chat.completion",
        "created": 0,
        "model": "test",
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
    }


def _tool_delta(index: int, call_id: str | None, name: str | None, args: str) -> dict:
    function = {"arguments": args}
    if name:
        function["name"] = name
    part = {"index": index, "type": "function", "function": function}
    if call_id:
        part["id"] = call_id
    return {
        "id": "x",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "test",
        "choices": [{"index": 0, "delta": {"tool_calls": [part]}, "finish_reason": None}],
    }


async def _completions(request: web.Request) -> web.StreamResponse:
    body = await request.json()
    model = body["model"]
    if model == "missing":
        return web.json_response({"error": {"message": "model not found"}}, status=404)
    if model == "busy":
        return web.json_response(
            {"error": {"message": "rate limited"}}, status=429, headers={"retry-after": "7"}
        )
    request.app[LAST_REQUEST].clear()
    request.app[LAST_REQUEST].update(body)
    if model == "tools" and not body.get("stream"):
        return web.json_response(
            _completion({"role": "assistant", "content": None, "tool_calls": [TOOL_CALL]})
        )
    if model == "empty" and not body.get("stream"):
        return web.json_response(_completion({"role": "assistant", "content": ""}))
    if model == "tools":  # streamed tool call, split into pieces
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        for delta in [
            _tool_delta(0, "call_9", "create_", '{"subj'),
            _tool_delta(0, None, "reminder", 'ect": "دکتر"}'),
        ]:
            await response.write(_sse(delta))
        await response.write(b"data: [DONE]\n\n")
        return response
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


async def test_list_models(server):
    """Regression: the 🤖 AI model menu did nothing because listing local models crashed."""
    _, url = server
    client = LLMClient(url, "key", "m", name="local")
    assert await client.list_models() == ["qwen2.5:3b"]
    await client.close()
    unreachable = LLMClient(f"http://127.0.0.1:{_free_port()}/v1", "key", "m", timeout=2)
    assert await unreachable.list_models() == []
    await unreachable.close()


async def test_check(server):
    _, url = server
    assert await LLMClient(url, "key", "qwen2.5:3b").check() is True
    assert await LLMClient(url, "key", "gemma3:1b").check() is False


# --- Agent turns: respond() with tools ---

TOOLS = [{"type": "function", "function": {"name": "add_expenses", "parameters": {}}}]


async def test_respond_returns_tool_calls(server):
    app, url = server
    client = LLMClient(url, "key", "tools", name="api", reasoning_effort="low")
    response = await client.respond([{"role": "system", "content": "s"}], tools=TOOLS)
    assert [(c.id, c.name, c.arguments) for c in response.tool_calls] == [
        ("call_1", "add_expenses", '{"items": []}')
    ]
    assert response.provider == "api"
    assert app[LAST_REQUEST]["tool_choice"] == "auto"
    assert app[LAST_REQUEST]["reasoning_effort"] == "low"
    await client.close()


async def test_respond_streams_tool_call_pieces(server):
    _, url = server
    client = LLMClient(url, "key", "tools", stream_tools=True)
    response = await client.respond([{"role": "user", "content": "x"}], tools=TOOLS)
    assert [(c.id, c.name, c.arguments) for c in response.tool_calls] == [
        ("call_9", "create_reminder", '{"subject": "دکتر"}')
    ]
    await client.close()


async def test_respond_streams_text(server):
    app, url = server
    shown = []

    async def on_text(piece):
        shown.append(piece)

    client = LLMClient(url, "key", "qwen3:4b", system_suffix="/no_think")
    response = await client.respond(
        [{"role": "system", "content": "rules"}, {"role": "user", "content": "hi"}], on_text=on_text
    )
    assert response.content == "سلام! Hi" and shown == ["سلام", "! ", "Hi"]
    assert app[LAST_REQUEST]["messages"][0]["content"] == "rules\n/no_think"
    await client.close()


async def test_empty_answer_is_a_failure(server):
    _, url = server
    client = LLMClient(url, "key", "empty")
    with pytest.raises(LLMError) as exc:
        await client.respond([{"role": "user", "content": "x"}], tools=TOOLS)
    assert exc.value.kind == "failed"
    await client.close()


async def test_rate_limit_with_retry_after(server):
    _, url = server
    client = LLMClient(url, "key", "busy")
    with pytest.raises(LLMError) as exc:
        await client.respond([{"role": "user", "content": "x"}], tools=TOOLS)
    assert exc.value.kind == "rate_limited" and exc.value.retry_after == 7
    await client.close()
