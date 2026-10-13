# Release v0.3.0-beta.1 — Voices of History Multiplayer

Experimental multiplayer for the Voices of History HoI4 AI mod. The host runs the
AI (Player2) and the console injector; clients forward their in-game decisions to
the host over HTTP and receive the AI's replies in a small agent window. Clients
never execute anything — every effect is injected by the host, so the game's
multiplayer sync is never modified by a client machine.

Read before testing: [BETA_TESTING.md](BETA_TESTING.md) — setup, firewall notes,
the phased test checklist, and the verdict criteria.
Background and feasibility: [MULTIPLAYER.md](MULTIPLAYER.md).

## What is in this release

- Host arbiter (`middleware/mp_server.py` + `mp_main.py`): HTTP API, per-player
  sessions, per-in-game-day request budget, one serialized AI pipeline, client
  state swap (the AI sees each client's own nation), shared leader channels and
  private decree/life channels, optional auto-pause.
- Client agent (`middleware/mp_agent.py`): tails the local game.log, forwards
  AIDIPLO_STATE / AIDIPLO_OPEN / AIDIPLO_DECREE_OPEN / AIDIPLO_LIFE_OPEN raw,
  chat window with ping/version check. No LLM, no injection, display only.
- One-click launchers: `middleware/START_MP_HOST.bat`, `middleware/START_MP_CLIENT.bat`.
- Offline self-test: `python mp_selftest.py` verifies the entire wire protocol
  without HoI4 or an LLM. Testers: run this first.
- Version + protocol handshake: agents warn on host/agent mismatch.

## Setup in one paragraph

Host: set a password in `middleware/mp_config.json`, run
`middleware/START_MP_HOST.bat`, host the HoI4 session (-debug, mod enabled, not
Ironman), open TCP 8710. Clients: same mod version, join the session, edit and run
`middleware/START_MP_CLIENT.bat`, use the in-game decisions as usual and type in
the agent window.

## Requirements

- HoI4 1.19, non-Ironman, identical mod version on every machine, -debug mode.
- Python 3.10+ (tcl/tk) on host and clients; Player2 only on the host.
- LAN or VPN connectivity to the host on TCP 8710.

## Known limitations

- Dynamic event popup TEXT on clients is stale/placeholder (the game does not
  sync localisation). The authoritative AI text is the client agent window.
- "Act as another figure" is host-only in this beta.
- Host's own chat and client requests share one pipeline.
- The Phase 0 kill test (host console effect in a live MP session) has not been
  verified on real hardware by the maintainers. Testers must run it first
  (BETA_TESTING.md). If it fails, the whole approach is dead and that is a
  valid, wanted result to report.

## Reporting

GitHub issues, with phase number, host console output, agent output, and whether
a desync popup appeared.
