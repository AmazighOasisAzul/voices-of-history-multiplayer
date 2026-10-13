# Beta testing — Voices of History Multiplayer (v0.2.0-beta.1)

Turn-based-free AI multiplayer for HoI4 via the Voices of History system. Read
[MULTIPLAYER.md](MULTIPLAYER.md) for why this design is the only one that can work.
This page is the tester checklist.

## What this beta is

The host runs the normal middleware PLUS a small arbiter. Clients run a light
agent that forwards their in-game "Talk to the Leader" / "Head of State Office" /
"Life of the Head of State" triggers to the host over HTTP (LAN or VPN). The
host's single AI answers everyone, and the host's console is the ONLY thing that
executes effects — so the game's multiplayer sync is never touched by a client.

## Requirements (all players)

- Hearts of Iron IV 1.19, NOT Ironman, same mod version installed and enabled
  (the host installs/registers it with the normal launcher).
- Game launched in `-debug` mode.
- Python 3.10+ with tcl/tk (host and clients). Player2 (the local AI app) ONLY on
  the host.
- Network: clients must reach the host on TCP 8710 (LAN, Hamachi, ZeroTier, Tailscale...).

## Host setup

1. Edit `middleware/mp_config.json`: set a real `password`. Optionally tune
   `max_requests_per_day` (per-player LLM request budget, resets each in-game day)
   and `auto_pause` (see caveats).
2. `cd middleware && python mp_main.py` — the normal chat overlay starts, plus
   `[MP] arbiter listening on 0.0.0.0:8710`.
3. Host the HoI4 multiplayer session (Direct Connect or LAN). Open your firewall
   for port 8710.
4. Do not run the middleware twice; mp_main.py IS the middleware.

## Client setup

1. Join the host's session. Make sure the mod is enabled and identical.
2. `cd middleware && python mp_agent.py --host <host-ip> --password <pw> --player <YourName>`
3. The agent window says "Host reachable". In game, use the decisions as usual.
   Type your messages in the AGENT window (not in any chat on the host).

## Test checklist — run in order and REPORT every result

Phase 0 — pre-flight (2 machines, no AI needed):

- [ ] Host opens the debug console in an MP session and runs
      `effect GER = { stability = 0.05 }`. Client sees Germany's stability change,
      no desync popup. **If this fails, stop and report — nothing else can work.**
- [ ] Host's `game.log` still shows the daily `AIDIPLO_STATE|` line during the MP
      session.

Phase 1 — wiring:

- [ ] Client agent prints "Host reachable" (`/ping`).
- [ ] Client uses "Talk to the Leader (AI)" on some nation; agent prints the
      channel open; the HOST overlay shows the same channel event.
- [ ] Client sends one message; the AI replies IN THE AGENT WINDOW within ~a
      minute; the host overlay shows the same reply.

Phase 2 — effects:

- [ ] The client asks the AI leader for something with a visible effect (e.g. a
      small equipment transfer or an opinion change). The effect appears on BOTH
      machines; no desync over the following 30 in-game days.
- [ ] The client uses "Head of State Office" and orders something (e.g. a law
      change): the AI sees the CLIENT's nation in its state block (ask it "what
      country am I?"), and the effect lands.

Phase 3 — multi-player stress:

- [ ] Two clients talk to the SAME leader: both see a consistent conversation
      (shared channel `leader:TAG`).
- [ ] Two clients send at the same time: replies come back serialized, no crash.
- [ ] A client hits the daily budget: the agent shows the budget-exhausted error
      and works again the next in-game day.

## Known limitations (do not report these, they are listed)

- Dynamic event POPUP text on clients is stale/placeholder (localisation is not
  synced by the game). The authoritative AI text is the agent window.
- "Act as another figure" channel is host-only in this beta.
- Host's own chat and client requests share one pipeline; avoid colliding.
- `auto_pause` is experimental (console `pause` is a toggle); default off.
- Client state reaches the host only when the client's mod exports it (daily or
  on channel open). Before the first export the AI may not know the client's tag.
- The AI's plan/crossroad safety-net reminders do not trigger on client
  decree/life channels (namespaced channels); clients should phrase plan requests
  explicitly.

## Reporting

Open a GitHub issue with: phase number, what happened, host middleware console
output, client agent output, and whether a desync popup appeared.

## Verdict criteria

The beta is validated if Phase 2 passes on at least two independent host/client
pairs with zero desyncs attributable to the middleware. It is dead if Phase 0
fails — report it and we close the project as "impossible", which is fine too.
