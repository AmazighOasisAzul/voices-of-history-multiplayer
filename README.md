# HOI4 AI Mod — Voices of History (Multiplayer fork)

Write your **own** history in **Hearts of Iron IV**. Every nation's leader is played by a **local AI**
you can actually talk to: negotiate, scheme, reform, industrialise, plot coups and wage wars in
plain language — and it **really happens in the game**, not in a menu. No rigid focus tree: you say
what you want, the AI turns it into real in-game actions and events, balanced to feel like part of
base HoI4.

This fork adds an **experimental multiplayer mode**: the host runs the AI, clients send their
in-game decisions to the host and get AI replies in a small window. Clients never execute
anything, so the game's multiplayer sync is never modified by a client machine.

This package has three parts:
- **The mod** (`mod/HOI4_AI_Diplomacy`) — the in-game side: the diplomacy button, the decisions,
  the dynamic events and effects. Install it on EVERY machine in a multiplayer session.
- **The middleware** (`middleware/`) — the companion app: the host's chat panel that connects
  the mod to your **local AI** (Player2) and executes actions in-game via the console.
- **The multiplayer layer** (`middleware/mp_*.py`) — the host-side arbiter + the client-side
  agent that make the above work across machines.

---

## Detailed guide — single player (unchanged from upstream)

### Requirements
- **Hearts of Iron IV 1.19** (no Ironman — the mod uses console effects).
- A **local AI** via the **Player2** app (runs on your PC). Open it before playing.
- **Windows**. To run the middleware you need **Python 3.10+** with tcl/tk.

### Single-player setup, step by step
1. Get this repo: **Code → Download ZIP** and extract it, or `git clone`.
2. Install the mod: run the upstream launcher **`VoicesOfHistory.exe`** if you have it, or copy
   the folder `mod/HOI4_AI_Diplomacy` into
   `Documents\Paradox Interactive\Hearts of Iron IV\mod\` and add a `.mod` descriptor
   (the folder contains `HOI4_AI_Diplomacy.mod` as a template).
3. Open the **Paradox launcher**, enable *HOI4 AI Mod Voices of History*.
4. Launch HoI4 in **`-debug`** mode (Steam: right-click HoI4 → Properties →
   Launch Options: `-debug`). Start or load a game (not Ironman).
5. Start the middleware: `cd middleware && pip install -r requirements.txt`
   then `python main.py` (or the upstream `VoicesOfHistory.exe`). The chat panel appears.
6. Play. **Right-click any nation** to talk to its leader, or use the in-game
   decisions (Supreme Command, Life of the Head of State, the press…).
   In the chat box: **Enter** to send, **Shift+Enter** for a new line.

## Detailed guide — MULTIPLAYER (this fork)

Who is who:
- **HOST**: the player who hosts the HoI4 session. Only the host runs the AI (Player2),
  the middleware, and the multiplayer arbiter. Ideally the best PC.
- **CLIENT**: every other player. Runs only the tiny agent. No AI, no Player2 needed.

### All players
- HoI4 1.19, NOT Ironman, launched with **`-debug`**.
- The **same mod version** installed and enabled (step 2 above).
- **Python 3.10+** from python.org (tick "Add to PATH"; keep tcl/tk/IDLE).

### Host setup
1. Edit `middleware/mp_config.json`: set a real `password`. Optionally tune
   `max_requests_per_day` (per-player AI request budget, resets each in-game day).
2. In `middleware/`: `python mp_selftest.py` — it must print
   `ALL SELF-TESTS PASSED` before you host.
3. Run `middleware/START_MP_HOST.bat` (or `python mp_main.py`). You should see:
   `[MP] arbiter listening on 0.0.0.0:8710`.
4. Windows Firewall: allow inbound **TCP 8710** (or temporarily allow Python on
   private networks while testing).
5. Host the game in HoI4 (Host Game → LAN / Direct Connect).

### Client setup
1. Join the host's session.
2. Right-click `middleware/START_MP_CLIENT.bat` → Edit. Set:
   - `HOSTIP` = the host's IP on your LAN/VPN (host: run `ipconfig`, IPv4 address)
   - `PASSWORD` = the password from the host's mp_config.json
   - `PLAYERNAME` = your name
3. Double-click it. The window must say **"Host reachable"**. If `PING FAILED`:
   wrong IP, firewall, or the host's arbiter is not running.
4. Keep this window open while playing. **Type your AI messages here**, not in-game.

### Playing multiplayer
- Use the in-game decisions exactly as in single player ("Talk to the Leader (AI)",
  "Head of State Office", "Life of the Head of State", "Act as Another Figure").
  The mod writes the trigger to your local log; the agent forwards it to the host;
  the host's AI answers in your agent window; effects are executed by the HOST and
  reach your game through normal multiplayer sync.
- Everyone talking to the SAME leader shares one conversation and one treaty memory.
- You have a limited number of AI requests per in-game day (host-configurable).

### First test — before anything else (Phase 0)
Host, in the live session: open the console, run
`effect GER = { stability = 0.05 }`. Every player must see Germany's stability drop
with NO desync popup. If this fails, stop and report it — nothing else can work.

Full test plan: **[BETA_TESTING.md](BETA_TESTING.md)**. Tester instructions in one
page: **[TESTER_GUIDE.md](TESTER_GUIDE.md)**.

## Troubleshooting
- Launcher says *"path invalid / does not exist"* → close the Paradox launcher, click
  **Repair Launcher**, reopen and re-enable the mod.
- *"Python not found"* → install Python 3.10+ from python.org (tick **Add to PATH**, keep
  **tcl/tk and IDLE**), then retry.
- The AI doesn't reply → make sure the **Player2** app is open (host only) and reachable.
- Client gets PING FAILED → check IP, password, firewall TCP 8710; host must run
  START_MP_HOST.bat.
- Dynamic event popup text on clients looks stale/placeholder → known limitation: the
  game does not sync localisation; the authoritative AI text is the agent window.

---

## Open source & safety
This companion app is **fully open source** — read every line before you run it. It runs
**entirely on your PC**: no telemetry, no accounts, no cloud. Its only network use is your
**local** AI (Player2, on `localhost`) — plus, in multiplayer, the LAN/VPN connection between
the host's arbiter and the clients' agents. See **[SECURITY.md](SECURITY.md)**.

Prefer not to trust a binary? Run it straight from source:
```
cd middleware
pip install -r requirements.txt
python main.py        # single player
python mp_main.py     # multiplayer HOST
```

### For developers
- `launcher.py` — source of the upstream launcher; `build_launcher.py` rebuilds it.
- `ARCHITECTURE.md` — how the mod and the middleware talk to each other.
- `MULTIPLAYER.md` — why multiplayer breaks, the design that goes around it, and what is implemented.
- `mp_server.py` / `mp_agent.py` / `mp_main.py` / `mp_selftest.py` — the multiplayer layer.
- License: **MIT** (see `LICENSE`).
