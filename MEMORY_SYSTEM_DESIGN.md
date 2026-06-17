# Long-term Memory System — Design

A lightweight long-term memory layer for an Open-LLM-VTuber character, so it
remembers who you are and gets to know you over time — without running a heavy
external memory service. It uses only the LLM you already configured plus the
existing `chat_history/` folder.

## Design in one line

Don't stuff everything into the LLM's context. Keep the full history on disk,
**inject a small curated "core memory"** into the persona, and let the LLM
**consolidate** new facts into that core memory after each turn.

## Layers

| Layer | What it holds | How it works |
|-------|---------------|--------------|
| **Core memory** (injected) | A few curated facts about the user (who they are, what they're working on, preferences, key moments) | Stored at `chat_history/<conf_uid>/core_memory.md`; appended to the persona prompt |
| **Full history** (fallback) | Every conversation, verbatim | The VTuber's existing `chat_history` JSON. (Phase 2: add FTS5 full-text retrieval) |
| **Consolidation** | Decides what is worth remembering | After each turn the LLM checks the exchange against write-triggers and updates core memory only when there's something new |

## Flow

1. **Conversation start** → core memory is injected into the persona, so the character already knows you.
2. **After each turn** → a background, non-blocking LLM call decides whether anything in the exchange is worth saving (see write-triggers) and updates `core_memory.md` if so.
3. **Per turn (phase 1.5)** → before each turn the system prompt is refreshed from `core_memory.md`, so newly-saved memories take effect immediately without a restart, while the conversation history in the agent is preserved.

## Write-triggers (what gets saved)

- User facts (identity, occupation, what they're building)
- Preferences and habits (likes, how they want to be addressed)
- Key events / important conclusions
- NOT: one-off small talk, greetings, exchanges with no new information

## Hard cap

Core memory is capped (~1.5 KB) so it always fits in the prompt. When it grows
past the cap, the LLM merges/distills older entries (promote the key, drop the
stale) — nothing is truly lost because the full history is always on disk.

## Vectors: not used (yet)

Phase 1 needs no search at all (core memory is injected directly). Phase 2's
full-history retrieval can use SQLite **FTS5** (local, light, no GPU). Vectors
are only worth it once FTS5 proves insufficient.

## Implementation

- `src/open_llm_vtuber/memory_core.py` — load/inject core memory + background consolidation
- `service_context.construct_system_prompt` — injects `core_memory.md` into the persona
- `single_conversation.py` — after each turn, schedules consolidation; before each turn, refreshes the injected memory (phase 1.5)
