# Multiplayer — feasibility, design, and the v0 implementation

This fork attempts what upstream considers impossible as a mod: running Voices of
History in a multiplayer session. This document is the honest breakdown of why it
breaks, why the naive fixes do not work, the only architecture that can work — and
what is actually implemented in this repo today (see "v0 implementation" below).

## Why it breaks in multiplayer (the three walls)

The current system is a loop: mod writes state to `game.log` → middleware reads it,
calls the LLM, and types console commands back into the game. In multiplayer every
link of that loop breaks:

1. **No execution channel for clients.** The debug console is host territory. A
   client-side middleware typing `effect` commands executes against a local game
   state that is not authoritative — the result is a desync, not an AI action.
   Every AI action, for every player, must be executed by the host's single
   middleware. There is no way around this inside a mod.
2. **No cross-machine channel inside the mod.** A HoI4 mod cannot open sockets.
   `game.log` is a local file per machine. The host's middleware currently sees
   only the host's log, so a client right-clicking "Talk to the Leader" produces an
   `AIDIPLO_OPEN` line the host will never read.
3. **Wall-clock turns are the wrong unit.** A real-time "15 minutes of AI access per
   player" timer desynchronizes from what is actually happening in the game and
   punishes players for host pauses they do not control.

Comparisons to agents conquering GTA or Elden Ring do not apply: those are
single-machine, single-player environments with no deterministic lockstep sync to
preserve. HoI4 multiplayer is a synchronized simulation; anything executed
out-of-band on a client corrupts it.

## Dynamic events — the event-ID question, checked against the code

Concern raised: "the game syncs events using the event ID from the existing events
on the client's files, and they might not exist if the event is made up by the
brain." Checked against `injector.py` / `main.py`. The good news and the bad news:

- **The event IDs are fine.** The middleware never invents event IDs. Dynamic
  events reuse fixed, shipped IDs (`event aidiplo.1`, `aidiplo.3<slot>`, `aidiplo.10`,
  `aidiplo.60`, …) that exist in the mod files on every machine. If all players run
  the same mod version, the ID resolves on every client. No unknown-ID desync from
  the ID itself.
- **What does NOT propagate is the text.** The dynamic content is carried by
  rewriting `ai_diplo_l_english.yml` on the host and injecting `reload loc` + `event
  aidiplo.X`. The rewrite happens in the HOST's Documents folder; `reload loc`
  re-loads the HOST's files only. Localisation is not part of the synchronized game
  state — each client renders event popups from its own local files. So when a
  dynamic event fired by the host pops up on a client, the client shows stale or
  placeholder text from ITS OWN loc file, while the host sees the real text.
- **Consequences:** (a) an event targeted at a client's country pops up on the
  client with wrong/empty text; (b) two different dynamic events in a row can even
  show the previous event's text on clients, since each rewrite overwrites the same
  keys. (c) The event still *fires* and its *effects* still apply — the gameplay
  result syncs, only the displayed text does not.

**v0 mitigation:** clients get the real content out-of-band — the AI's reply is
returned by the arbiter to the client agent window, which is the authoritative
display. The in-game popup on the client is a generic "something happened" box.
A proper fix (a static generic loc key for MP + all dynamic text delivered via the
agent) is listed under non-goals for v0 and is the first mod-side change to make.

## The realistic architecture

The key insight: the middleware is not the mod. It is a companion app. Moving
coordination into the companion layer does not touch the game's sync at all.

- **Host = arbiter.** The host runs the existing, unchanged middleware: it owns the
  LLM, the memory/treaty SQLite DB, and the console injector. One brain, one
  memory, one executor. All AI actions are injected by the host, so they sync.
- **Clients run a light agent (no LLM).** A small script that tails the client's
  local `game.log`, forwards `AIDIPLO_OPEN` lines to the host over HTTP (LAN or
  VPN), and shows replies in its own window. Clients never execute anything.
- **Host middleware gains**: an HTTP endpoint, per-player sessions, a request
  queue, and a fairness scheduler.

## The turn system — corrected

The original idea (each player gets N minutes with the AI, others wait) is
playable but miserable with 3+ players: 20 min turns x 4 players = an hour between
your turns. Instead:

- **Tie the budget to in-game time, not wall-clock.** Each player gets a request
  budget per in-game day (v0 implements exactly this: `max_requests_per_day` in
  `mp_config.json`, reset automatically on each new in-game day).
- **Queue, do not block.** Any player can compose messages anytime; requests are
  serialized by the arbiter (one LLM pipeline at a time) rather than scheduled into
  exclusive windows.
- **Host pause discipline.** Injecting commands mid-tick is what causes desyncs.
  The host should pause before/during batches. (Not yet automated in v0.)
- **Shared treaty memory.** Because only the host holds the SQLite DB, all players'
  deals live in one consistent world state. This is a genuine advantage over the
  single-player version.

## v0 implementation (in this repo)

Zero changes to the existing mod or middleware source: everything is additive.

| File | Machine | Role |
|---|---|---|
| `middleware/mp_config.json` | host | port, shared password, request budget |
| `middleware/mp_server.py` | host | HTTP arbiter: /ping /open /send /close, per-player sessions, budget, serialized LLM pipeline |
| `middleware/mp_main.py` | host | entry point: runs the normal middleware with the arbiter attached |
| `middleware/mp_agent.py` | each client | tails local game.log, forwards AIDIPLO_OPEN, chat window, display only |

### Setup

Host:
1. Configure `middleware/mp_config.json` (set a real password).
2. Run `python mp_main.py` instead of `python main.py`. The chat overlay works as
   usual; the arbiter listens on port 8710.
3. Host the HoI4 session with the mod enabled, -debug mode. Firewall: open the port.

Client:
1. Same mod version installed. Do NOT run the middleware.
2. `python mp_agent.py --host <host-ip> --password <pw> --player <name>`.
3. Join the host's session. Use the in-game 'Talk to the Leader' decision; type in
   the agent window. Effects are executed by the host and appear in your game via
   the normal sync.

### Known v0 limitations (read before testing)

- **Untested against a live MP session.** The single kill test below must pass on
  real hardware first.
- The AI's world context is host-centric: `AIDIPLO_STATE` is exported by the host's
  mod to the host's log, so every player's conversation carries the host's state
  block. The client's own nation still appears in the world snapshot. Fix later:
  clients submit their own parsed state line to the arbiter.
- Only leader channels are wired in v0 (decree/life/actor channels are host-only).
- The host's own chat and client requests share one pipeline; the host should not
  chat at the exact moment a client request is running.
- Dynamic event TEXT on clients is wrong/stale (see the section above); the
  authoritative reply text is the agent window.

## Experiment order (do not skip)

Each step must pass before the next one, or the whole project is dead:

1. **Host console in MP (kill test).** Host a multiplayer session with -debug, open
   the console as host, run `effect GER = { stability = 0.05 }`-class commands.
   Confirm every client sees the change and no desync occurs. If host console
   commands do not sync, stop — there is no mod-side workaround. **This is still
   step 1: nobody has run it yet. Do it before testing the v0 code.**
2. **Host log visibility.** Confirm the daily `AIDIPLO_STATE` export line still
   appears in the host's `game.log` during an MP session.
3. **Agent loop over the wire.** Two machines, one runs `mp_main.py`, the other
   `mp_agent.py`; forward one `AIDIPLO_OPEN` line over HTTP and get a reply back.
4. **Queue + batch injection.** Two queued requests, verify no desync over 30
   in-game days.

## Non-goals (v0)

- No per-player API keys. The host's key is the only key.
- No client-side effects, ever. Display-only clients.
- No rewriting the game's multiplayer sync. That is the "impossible as a mod" wall
  and this design goes around it, not through it.
- Full dynamic-text-in-game display for clients (needs a mod-side loc change).

## Status

Phase 0 done (this analysis). Phase 1 v0 code implemented (this commit): arbiter,
client agent, budget, serialization. The live-MP kill test (step 1) is still
unexecuted and gates everything.
