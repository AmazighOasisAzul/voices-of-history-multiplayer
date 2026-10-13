# Multiplayer — feasibility analysis and the turn-based design

This fork attempts what upstream considers impossible as a mod: running Voices of
History in a multiplayer session. This document is the honest breakdown of why it
breaks, why the naive fixes do not work, and the only architecture that can.

## Why it breaks in multiplayer (the three walls)

The current system is a loop: mod writes state to `game.log` → middleware reads it,
calls the LLM, and types console commands back into the game. In multiplayer every
link of that loop breaks:

1. **Wall-clock turns are the wrong unit.** HoI4 multiplayer has pause control and
   game speed owned mostly by the host. A real-time "15 minutes of AI access per
   player" timer desynchronizes from what is actually happening in the game and
   punishes players for host pauses they do not control.
2. **No execution channel for clients.** The debug console is host territory. A
   client-side middleware typing `effect` commands executes against a local game
   state that is not authoritative — the result is a desync, not an AI action.
   Every AI action, for every player, must be executed by the host's single
   middleware. There is no way around this inside a mod.
3. **No cross-machine channel inside the mod.** A HoI4 mod cannot open sockets.
   `game.log` is a local file per machine. The host's middleware currently sees
   only the host's log, so a client right-clicking "Talk to the Leader" produces an
   `AIDIPLO_OPEN` line the host will never read.

Comparisons to agents conquering GTA or Elden Ring do not apply: those are
single-machine, single-player environments with no deterministic lockstep sync to
preserve. HoI4 multiplayer is a synchronized simulation; anything executed
out-of-band on a client corrupts it.

## The realistic architecture

The key insight: the middleware is not the mod. It is a companion app. Moving
coordination into the companion layer does not touch the game's sync at all.

- **Host = arbiter.** The host runs the existing, unchanged middleware: it owns the
  LLM, the memory/treaty SQLite DB, and the console injector. One brain, one
  memory, one executor. All AI actions are injected by the host, so they sync.
- **Clients run a light agent (new, small, no LLM).** A stripped-down Python script
  that tails the client's local `game.log`, forwards `AIDIPLO_*` lines to the host
  over HTTP (LAN or VPN), and shows replies in a display-only overlay. Clients
  never execute anything.
- **Host middleware gains**: an HTTP endpoint, per-player sessions, a request
  queue, and a fairness scheduler.

## The turn system — corrected

The original idea (each player gets N minutes with the AI, others wait) is
playable but miserable with 3+ players: 20 min turns × 4 players = an hour between
your turns. Instead:

- **Tie the budget to in-game time, not wall-clock.** Each player gets a request
  budget per in-game month (e.g. 5 LLM calls/month, host-configurable). The state
  export already runs daily, so the host middleware knows exactly which day it is.
- **Queue, do not block.** Any player can compose messages/diplomacy at any time;
  the agent queues them. The host processes the queue when the game is paused or
  at a configurable interval (e.g. every in-game week), executing action batches
  in one host-side injection pass. Waiting players lose nothing — they just see
  results at the next tick.
- **Host pause discipline.** Injecting a batch of console commands mid-tick is
  what causes desyncs. The host middleware should auto-pause, inject, resume.
  This is the single most important reliability rule.
- **Shared treaty memory.** Because only the host holds the SQLite DB, all players'
  deals live in one consistent world state. This is a genuine advantage over the
  single-player version.

## Experiment order (do not skip)

Each step must pass before the next one, or the whole project is dead:

1. **Host console in MP (kill test).** Host a multiplayer session with -debug, open
   the console as host, run `effect GER = { stability = 0.05 }`-class commands.
   Confirm every client sees the change and no desync occurs. If host console
   commands do not sync, stop — there is no mod-side workaround.
2. **Host log visibility.** Confirm the daily `AIDIPLO_STATE` export line still
   appears in the host's `game.log` during an MP session.
3. **Agent loop over the wire.** Two machines, one runs the arbiter, the other the
   agent; forward one `AIDIPLO_OPEN` line over HTTP and get a reply back.
4. **Queue + batch injection.** Two queued requests, one injection pass, verify no
   desync over 30 in-game days.

## Non-goals

- No per-player API keys. The host's key is the only key; that was the right idea.
- No client-side effects, ever. Display-only clients.
- No rewriting the game's multiplayer sync. That is the "impossible as a mod" wall
  and this design goes around it, not through it.

## Status

Phase 0 — this document. Phase 1 (host console kill test) is the next deliverable
and must be run on real hardware with 2+ players before any code is written.
