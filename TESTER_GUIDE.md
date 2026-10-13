# Playtester quick guide — Voices of History Multiplayer (v0.3.x-beta)

Read this once. It answers "what do I install, what do I click, what do I report".

## What you are testing

Whether AI-driven diplomacy works in a HoI4 multiplayer session. The HOST runs
the AI and executes everything; you (the client) send your in-game decisions to
the host and get AI replies in a small window on your PC. You never run the AI.

## Who is the host

The person with the best PC and the Player2 AI app. Everyone else is a client.
Agree on this before starting.

## Setup — ALL players

1. Hearts of Iron IV 1.19, NOT Ironman, launched in `-debug` mode
   (Steam launch options: `-debug`). Same mod version on every machine.
2. Python 3.10+ from python.org (tick "Add to PATH", keep tcl/tk/IDLE enabled).
   From the release page: Code → Download ZIP → extract, or git clone.

## Setup — HOST only (extra)

1. Open `middleware/mp_config.json`, change `"password"` to something real.
2. Double-click `middleware/START_MP_HOST.bat`. You should see
   `[MP] arbiter listening on 0.0.0.0:8710` in the window.
3. Run `python mp_selftest.py` in the same folder first: it must print
   ALL SELF-TESTS PASSED.
4. Windows Firewall: allow inbound TCP 8710 (or temporarily disable private
   network firewall while testing).
5. Host the game: Host Game → LAN, or Direct Connect.

## Setup — CLIENTS only

1. Right-click `middleware/START_MP_CLIENT.bat` → Edit: set HOSTIP (host's
   LAN/VPN IP), PASSWORD, PLAYERNAME. Save. Double-click it.
2. The window must say "Host reachable". If PING FAILED: wrong IP, firewall,
   or the host's arbiter isn't running.

## Playing

- Host launches the session in -debug, loads the save/start.
- Everyone joins. Play normally.
- To talk to an AI leader: use the in-game decision "Talk to the Leader (AI)"
  (right-click nation → Talk to the Leader). Type your message in the AGENT
  WINDOW on your PC (clients) — NOT in the game, NOT on the host.
- The AI's reply appears in your agent window. The effects it agrees to happen
  in the game automatically via the host.

## What to report (GitHub issue or the group chat, in this order)

Phase 0 — THE BIG ONE (host only, 2 minutes, do this FIRST):
- Host: open the debug console (~ key) in the live MP session and type:
  `effect GER = { stability = 0.05 }`
- Then press Escape → hover Germany or check its stability.
- REPORT: did every player see Germany's stability drop, and did anyone get a
  DESYNC popup? This single test decides if the project can work at all.

Phase 1 — wiring (10 min):
- Client agent says "Host reachable"?
- Client uses "Talk to the Leader" on some nation → agent window says
  "Channel open". Host's chat overlay shows the same.
- Client sends one message → AI replies in the agent window.

Phase 2 — effects (30 min):
- Ask the AI leader for something visible (equipment, opinion change, deal).
  Both players see the result? Desync during the next 30 in-game days?

Phase 3 — stress (if you got this far):
- Two clients talk to the SAME leader at once.
- Two clients send messages simultaneously.
- One client spams until "budget exhausted" appears; works again next day?

## For slow PCs

- The client agent is tiny (no AI, no game hooking); it runs on anything that
  runs HoI4. If HoI4 itself is unplayable, be the HOST's note-taker instead and
  watch the host's screen via Discord stream.

## Honesty clause

This may be impossible in practice (the game may reject host console effects
in MP). If Phase 0 fails, say so clearly — that is the single most valuable
data point this beta can produce, not a failure of you as a tester.
