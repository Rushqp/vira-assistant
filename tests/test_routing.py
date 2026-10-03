"""End-to-end routing: real updates through the dispatcher with a fake Telegram session.

The `env` fixture (conftest.py) feeds updates to the real dispatcher; see `tests/fakes.py`.
"""

from app import texts
from app.llm.client import LLMError


async def test_free_text_goes_to_llm(env):
    send, session, llm = env
    await send("Hello Vira")
    assert len(llm.calls) == 1
    assert llm.calls[0][-1] == {"role": "user", "content": "Hello Vira"}
    shown = session.edits[-1] if session.edits else session.sent[-1]
    assert shown == "Hi! How can I help?"


async def test_calculator_skips_llm(env):
    send, session, llm = env
    await send("۱۲ × ۳۵۰۰۰۰")
    assert llm.calls == []
    assert "4,200,000" in session.sent[-1]


async def test_date_question_skips_llm(env):
    send, session, llm = env
    await send("امروز چندمه؟")
    assert llm.calls == []
    assert "امروز" in session.sent[-1]


async def test_new_chat_button_and_command(env):
    send, session, llm = env
    await send("first")
    await send(texts.BTN_NEW_CHAT)
    assert session.sent[-1] == texts.NEW_CHAT
    await send("second")
    assert [m["content"] for m in llm.calls[-1][1:]] == ["second"]
    await send("/new")
    assert session.sent[-1] == texts.NEW_CHAT


async def test_planned_buttons_and_commands_do_not_reach_llm(env):
    send, session, llm = env
    await send(texts.BTN_EXPORT)
    await send("/backup")
    await send("/whatever")
    assert llm.calls == []
    assert "v0.5" in session.sent[0]
    assert "v0.7" in session.sent[1]
    assert session.sent[2] == texts.UNKNOWN_COMMAND


async def test_llm_failure_shows_notice(env):
    send, session, llm = env
    llm.answer, llm.error = "", LLMError("unreachable")
    await send("hello?")
    assert session.sent[-1] == texts.LLM_ERRORS["unreachable"]


async def test_strangers_are_ignored(env):
    send, session, llm = env
    await send("hi", user_id=999)
    assert session.sent == [] and llm.calls == []


async def test_previous_chats_flow(env):
    await env.send("My name is Sara")
    await env.send(texts.BTN_NEW_CHAT)
    await env.send("Second topic")

    await env.send(texts.BTN_CHATS)
    assert env.session.sent[-1].startswith("🗂 <b>Your chats</b> (2)")

    await env.press(env.button("My name is Sara"))
    recap = env.session.edits[-1]
    assert "Continuing: <b>My name is Sara</b>" in recap
    assert "🧑 My name is Sara" in recap

    await env.send("What's my name?")
    assert [m["content"] for m in env.llm.calls[-1][1:]] == [
        "My name is Sara",
        "Hi! How can I help?",
        "What's my name?",
    ]


async def test_delete_chat_flow(env):
    await env.send("Delete me")
    await env.send(texts.BTN_CHATS)
    await env.press(env.button("Delete me"))
    await env.press(env.button(texts.BTN_DELETE))
    assert "This can't be undone" in env.session.edits[-1]
    await env.press(env.button(texts.BTN_YES_DELETE))
    assert env.session.alerts[-1] == texts.CHAT_DELETED
    assert env.session.edits[-1] == texts.CHATS_EMPTY


async def test_chats_empty(env):
    await env.send("/chats")
    assert env.session.sent[-1] == texts.CHATS_EMPTY
