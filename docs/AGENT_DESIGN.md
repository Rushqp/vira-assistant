# Vira Agent — Design

> Status: **Accepted** (v0.4.0) · Replaces the keyword-first understanding layer of v0.1–v0.3.
> The services, database and scheduler are kept; only *understanding* changes.

---

## 1. Why

The keyword pipeline (normalizer → regex rules → LLM only as a fallback) failed on ordinary sentences:

| User wrote | What happened | Why |
|---|---|---|
| «یک یاد اوری تنظیم کن برای ۵ دقیقه دیگه …» | Treated as chat | «اوری» without madda was not a known keyword |
| «امروز ۳ خرید کردم: سیگار ۱۵۰ هزار، ماست ۲۰۰ هزار، آب ۵۰ هزار» | Asked "3 thousand or 3 million?" | «۳» (a count) looked like an amount |
| «برای فردا تایم دکتر دارم» … «تایم دکتر رو کنسل کن» | Could not cancel | No notion of follow-ups or references |

Rules can only recognise phrasings someone anticipated. A personal assistant must understand *any*
phrasing, typos, several requests in one message, and references to earlier messages.

## 2. Requirements

**Functional**
- Understand Persian (formal, colloquial, typos, no ZWNJ/madda) and English, including mixed messages.
- Several actions in one message ("add these three expenses and remind me to pay the rent").
- Follow-ups and references: "cancel the doctor one", "no, it was 200", "delete the last one".
- Act directly and show what was done with **↩️ Undo** and **✏️ Edit** (user decision).
- Ask only when truly ambiguous. Hard rule kept from v0.4: an amount below 1000 without
  thousand/million («۳ تومن») is always asked with buttons.
- Plain Q&A chat in the user's language.

**Non-functional**
- $0: free API tiers and/or local models.
- Three CPU-only hardware profiles: `lite` (2 GB), `standard` (4 GB), `full` (8 GB+), plus `remote`.
- Reminders keep firing with no LLM at all; the bot keeps working (degraded) when every model is down.
- Single user: tens to low hundreds of messages a day (well inside free quotas).
- Latency: API ≈ 1–4 s per message; local CPU models are slower (see §8).

**Constraints**: Python 3.12 / aiogram 3 / SQLite; existing services and tests stay valid.

## 3. Research summary (September–October 2026)

**Free LLM APIs** (all OpenAI-compatible, all support tool calling):

| Provider | Default model (others in the menu) | Free quota (approx.) | Notes |
|---|---|---|---|
| Google Gemini | `gemini-flash-latest` (`gemini-flash-lite-latest`) | low thousands req/day (Flash tier), 1M context | Best Persian quality among free options; reasoning can't be fully disabled on 3.x → `reasoning_effort=low` |
| Groq | `openai/gpt-oss-120b` (`gpt-oss-20b`, `llama-3.3-70b-versatile`, `qwen/qwen3.8-27b`) | 30 RPM, 1 000 RPD, 8 000 TPM | Very fast; tokens-per-minute is the real limit → compact prompts |
| Mistral | `mistral-small-latest` (`medium`, `large`) | free *Experiment* plan, low RPS | Good multilingual quality; native tool calling |
| GitHub Models | `openai/gpt-4.1-mini` (`gpt-4.1`, `gpt-4o-mini`, `gpt-5-mini`) | 15 RPM, 150 RPD (lower for larger models) | Needs only a GitHub token with *Models* access |
| OpenRouter | `openrouter/free` | ~50 req/day without credits | A router that picks a free model supporting the request's features (tools) |
| Cerebras, Cohere | — | — | Not used: no permanent free tier / non-commercial trial keys |

Quotas change often, so providers and models are configuration, not code (`app/llm/models.py` is
only the menu's catalog), and the chain falls through to the next model when one is exhausted.

**Local models with native tool calling** (Ollama): Qwen3 (0.6B–235B, native tool template,
optional thinking) is the common recommendation for local agents; `qwen3:4b` for ~4 GB and
`qwen3:8b` for 8 GB+. Gemma 3 has no native tool support (fine for chat only).

**Similar open-source projects and the patterns adopted**
- *matteo-bigliardi/personal-ai-assistant*: typed tools validated by the app; the database is the
  source of truth and the LLM is not the scheduler; a thin transcript only resolves "that one";
  no calendar arithmetic by the model (it gets absolute dates); domain errors are returned to the
  model verbatim so it can correct itself; static prompt prefix for caching, time in the user turn.
- *josephniel/majordomo*: ordered multi-vendor failover with cooldowns, empty replies count as
  failures; never trust the model's claims about actions, only real tool results.
- General findings: argument validation and strict schemas matter more for tool reliability than
  model size; always validate tool arguments before executing.

## 4. High-level design

```
Telegram update
   │
   ├─ buttons / commands / form states ──► existing handlers (unchanged)
   │
   └─ free text ─► assistant handler
                     │  instant: calculator, "what's the date"            (no LLM)
                     │
                     ▼
                  Agent.run(text, context)
                     │   messages = [static system prompt]          ← cacheable prefix
                     │            + recent transcript (with [✓ …] action notes)
                     │            + [context: now, date table fa/en, settings] + user text
                     ▼
                  ProviderChain.respond(messages, tools)  ── [chosen model] → gemini → groq
                     │        → mistral → github → openrouter → local
                     │        (cooldown on 429/5xx/timeout/empty; skips models without tools;
                     │         a change of the answering model becomes a notice to the user)
                     ▼
              ┌── tool calls? ──no──► final text (streamed when the provider streams)
              │yes
              ▼
           ToolRegistry.execute(call)
              │  1. validate args (Pydantic)
              │  2. deterministic checks: amount parser, Jalali/Gregorian date parser
              │  3. call services (expenses, reminders, reports, settings)
              │  4. record undo info (agent_actions)
              │  5. return {result for the model} + {card for the user}
              ▼
           results go back to the model (max 4 rounds) ──► short final sentence
                     │
                     ▼
     user sees: [streamed text] + result cards with ↩️ Undo / ✏️ Edit
                or a deterministic question (thousand / million buttons)

   No tool-capable provider reachable ──► fallback: the v0.3/v0.4 rule pipeline + plain chat
```

Key decisions:
1. **The model decides, the app verifies and acts.** Tools are typed; arguments are validated;
   cards shown to the user are rendered from real results, never from the model's text, so a
   hallucinated "done!" can't hide a missing action.
2. **No date or currency arithmetic by the model.** The context lists today ± a week in both
   calendars; tools take the user's own words (`when_text`, `amount_text`) *and* the model's
   interpretation; deterministic parsers win where they are certain (Jalali dates, «هزار/میلیون»).
3. **Database = memory.** The transcript is short (last messages) and carries compact action notes
   (`[✓ reminder #12 created: …]`) so references resolve to ids. Tools also accept a text `query`
   ("doctor") and refuse when it matches more than one item, returning the candidates.
4. **ProviderChain is a drop-in for the old `LLMClient`** (`stream_chat`, `complete_json`, plus the
   new `respond`), so chat history, reminder/expense helpers and tests keep working.

## 5. Tools

| Tool | Purpose | Arguments (main) | Deterministic checks |
|---|---|---|---|
| `add_expenses` | Record one or more expenses | `items[{description, amount_text, quantity?, unit?, category?}]`, `date?` | amount parser on `amount_text`; ambiguous (<1000, no scale) → buttons; future date → error |
| `list_expenses` | Find expenses (to edit/delete/answer) | `period?`, `query?` | — |
| `update_expense` | Change amount/description/category/date | `id`, fields | same as add |
| `delete_expenses` | Delete by ids or query | `ids?`, `query?` | ambiguous query → candidates |
| `get_report` | Show a report card | `period` (today … last_month) | report service |
| `create_reminder` | New reminder | `subject`, `when_text`, `start`, `alerts[]`, `repeat`, `important` | date/time parser on `when_text`; past → error; empty alerts → "at the time" + alert buttons |
| `list_reminders` | Find reminders | `query?` | — |
| `update_reminder` | Reschedule / rename / change alerts | `id?`/`query?`, fields | as create |
| `cancel_reminders` | Cancel by ids or query | `ids?`, `query?` | ambiguous query → candidates |
| `convert_date` | Jalali ↔ Gregorian, weekday | `date_text` | date parser / jdatetime |
| `calculate` | Arithmetic | `expression` | safe AST evaluator |
| `update_settings` | Calendar, morning briefing, nightly report | `calendar?`, `morning_briefing?`, `morning_briefing_time?`, `nightly_report?`, `nightly_report_time?` | enum validation; time parser (a bare «۹» is 21:00 for the nightly report, which must be 12:00–23:59) |
| `export_expenses` | Send an Excel file of expenses | `period?` / `month?` / `year?` / `from_date?` + `to_date?`, `categories?`, `query?`, `columns?`, `summaries?`, `chart?` | months by name or number in both calendars («مهر», "October", `1405-07`), dates via the date parser; unknown category → the list |
| `export_reminders` | Send an Excel file of reminders | `period?` (upcoming …), `from_date?`, `to_date?`, `query?`, `important_only?`, `include_done?` | date parser |
| `make_spreadsheet` | Any table as an Excel file | `title`, `sheets[{name, columns, rows, totals?}]` | size limits; numbers detected safely (phone numbers stay text); rows given as objects are accepted |

Errors are returned to the model as `{"error": "...", "hint": "..."}`; the model gets up to four
rounds per message to correct itself or ask the user.

## 6. Prompting

- **System prompt (static)**: role, rules, tool guidance, categories, day-part clock times, examples
  in Persian and English. Nothing volatile → providers can cache it; Ollama reuses its KV cache.
- **Context block (per message, prepended to the user text)**: now (both calendars, weekday names
  in both languages), a table of yesterday … +7 days, the user's calendar and currency.
- **Transcript**: last `CHAT_MEMORY` messages of the active chat; assistant messages include the
  action notes. 🗂 Chats recaps hide the notes.
- Rules the prompt insists on: use tools for every action; several items → one call; counts
  («۳ تا خرید») are not amounts; copy amounts and time words verbatim; ask only for missing
  essentials; after tools reply with at most one short sentence (cards show the details); answer in
  the user's language.
- Qwen3 local models get `/no_think` (speed); Gemini and gpt-oss use `reasoning_effort=low`.

## 7. Undo, edit and clarifications

- Every write records an **agent action** (`agent_actions` table: kind, JSON payload, undone_at):
  created ids, deleted rows, previous values. ↩️ Undo reverses it (delete / restore / revert) and
  survives restarts.
- ✏️ Edit asks "what should I change?" and sends the next message to the agent with a note pointing
  at that action, so "make it 200 thousand" updates the right record.
- **Amount clarification** stays deterministic: the batch waits; buttons choose thousand/million;
  typing «هزار» / «میلیون» also answers. Then everything is saved at once with Undo.
- **Reminders without a notification time** are saved "at the time" (act directly) and the card
  offers buttons to add 15 min / 1 hour before, the night before or the morning of the day.

## 8. Hardware profiles

| Profile | RAM | Brain (in order) | Local model | Without an API key |
|---|---|---|---|---|
| `lite` | 2 GB | free APIs → rules | `gemma3:1b` (chat only, no tools) | rule pipeline + local chat |
| `standard` | 4 GB | free APIs → local agent | `qwen3:4b` (tools, `/no_think`) | local agent (slow on CPU) |
| `full` | 8 GB+ | free APIs → local agent | `qwen3:8b` (tools, `/no_think`) | local agent |
| `remote` | — | configured API(s) only | — | — |

Recommendation for every profile: add at least one free API key (Gemini). Local CPU inference of
a 4–8B model takes several seconds to tens of seconds per message; the static prompt prefix keeps
follow-up messages faster through prompt caching. `scripts/eval_agent.py` measures accuracy and
latency of any configured provider/model on a fixed set of Persian/English cases, so profile
defaults can be benchmarked on the real server.

## 9. Reliability

- Model errors (connection, timeout, 429, 5xx, invalid key, unknown model, empty response) → the
  model is paused and the next one answers. Free quota used up (429): `Retry-After`, otherwise
  1 min doubling up to 30 min; invalid key / unknown model: 1 hour; anything else: 30 s doubling
  up to 10 min. Cooldowns are per model, so another model of the same provider can still answer.
- The user can put any model first (🤖 AI model, `/model`; saved in the `settings` table and
  applied at startup). The configured order stays behind it as backup; ✨ Auto removes the choice.
- Every change of the answering model is a `Notice` (`switched` with the reason and the time the
  model is tried again, `restored`, `down`), sent after the turn by a middleware; `down` is sent
  before the rule-based fallback so the user knows why the answer is basic. Each change is
  reported once: an outage is not repeated on every message, and plain-chat calls made during an
  outage don't add notices (they do in a chat-only setup, which has no agent turns).
- Mid-turn failure: actions already executed are still shown (with Undo); only the final sentence
  is missing.
- No tool-capable provider → rule pipeline (v0.4 behaviour) + plain chat if any model can chat.
- Reminders, alerts and the morning briefing never call an LLM.
- Privacy: with an API provider, message text (not the database) is sent to that provider. Use
  `PROFILE=standard/full` without API keys for fully local operation.

## 10. Trade-offs

| Choice | Gain | Cost / risk | Mitigation |
|---|---|---|---|
| LLM-first instead of rules-first | Understands any phrasing, follow-ups, multi-intent | 1–3 LLM calls per action; depends on model quality | Free API chain; deterministic validators; rule fallback |
| Free APIs as primary | Best intelligence at $0 | Quotas change; text leaves the server | Config-driven chain, cooldowns, local fallback |
| Act directly + Undo | Feels like a real assistant | Wrong action possible | Undo everywhere; validation; cards show exactly what happened |
| Deterministic amount/date checks | No Jalali/currency mistakes | Two sources of truth to reconcile | Clear precedence rules (§4.2), tested |
| Thin transcript + action notes | Small prompts (Groq TPM), references work | Very old references need a search | `list_*` tools and `query` arguments |

## 11. What to revisit

- Benchmark local defaults per profile with `scripts/eval_agent.py` on the real server.
- Voice (v0.6) feeds transcripts into the same agent, with a note that the text comes from
  speech (recognition errors are possible); watch how models handle mis-heard words.
- Notes / to-dos (v0.7) become new tools (and `export_*` gains them).
- If quotas tighten: a small classifier to answer trivial chat locally and save API calls.
- Proactive suggestions (e.g. budget warnings) once there is enough data.
