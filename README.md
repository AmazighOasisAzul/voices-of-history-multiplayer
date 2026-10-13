# HOI4 AI Mod — Voices of History

Write your **own** history in Hearts of Iron IV. Every nation's leader is played by a **local AI**
you can actually talk to: negotiate, scheme, reform, industrialise, plot coups and wage wars in
plain language — and it **really happens in the game**, not in a menu. No rigid focus tree: you say
what you want, the AI turns it into real in-game actions and events, balanced to feel like part of
base HoI4.

This package has two parts that work together:
- **The mod** (`mod/HOI4_AI_Diplomacy`) — the in-game side: the diplomacy button, the decisions,
  the dynamic events and effects.
- **The middleware** (`middleware/`) — a small companion app (the on-screen chat) that connects the
  mod to your **own local AI** running in Player2. Nothing is sent to the cloud.

Everything is driven from one window: **`VoicesOfHistory.exe`**.

---

## Requirements
- **Hearts of Iron IV 1.19** (no Ironman — the mod uses console effects).
- A **local AI** via the **Player2** app (runs on your PC). Open it before playing.
- **Windows**. (To run the middleware you need **Python 3.10+** with tcl/tk — see below.)

## Quick start
1. Run **`VoicesOfHistory.exe`**.
2. Click **Install / Update Mod** — it copies the mod into your HoI4 folder and registers it.
3. Open the **Paradox launcher**, enable *HOI4 AI Mod Voices of History*, and launch the game in
   **`-debug`** mode. Start or load a game.
4. Back in the launcher, click **Start Middleware** — the chat panel appears on the right.
   - The first time it asks the **realism mode** and the **language** the AI should speak in.
5. Play. **Right-click any nation** on the map to talk to its leader, or use the in-game
   **decisions** (Supreme Command, Life of the Head of State, the press…).

> In the chat box, press **Enter** to send (**Shift+Enter** for a new line).

## How to play
- **Talk to a leader** — right-click a nation → *Talk to the Leader (AI)*. Negotiate pacts,
  alliances, lend-lease, cessions, coordinated wars… what you agree on is executed in-game.
- **Supreme Command / Head of State Office** — give orders in natural language (reforms,
  conscription laws, industrial plans, political moves); the AI translates them into real actions.
- **Life of the Head of State** — step into your leader: speeches, tours, cabinet meetings.
- **Act as Another Figure** — play a faction, a general, a conspirator; plot against the government.
- **The Press** — read the state, independent or opposition newspaper about the real world state.

## Troubleshooting
- Launcher says *"path invalid / does not exist"* → close the Paradox launcher, then click
  **Repair Launcher** in `VoicesOfHistory.exe`, reopen the launcher and re-enable the mod.
- *"Python not found"* → install Python 3.10+ from python.org (tick **Add to PATH** and keep
  **tcl/tk and IDLE**), then click **Start Middleware** again.
- The AI doesn't reply → make sure the **Player2** app is open and reachable.

---

## Open source & safety
This companion app is **fully open source** — read every line before you run it. It runs **entirely
on your PC**: no telemetry, no accounts, no cloud. Its only network use is your **local** AI
(Player2, on `localhost`) and a one-time `pip install` of dependencies from PyPI. See
**[SECURITY.md](SECURITY.md)** for exactly what it reads/writes and how to verify it yourself.

Prefer not to trust a binary? You can run it straight from source:
```
cd middleware
pip install -r requirements.txt
python main.py
```

### For developers
- `launcher.py` — source of the launcher. `build_launcher.py` rebuilds `VoicesOfHistory.exe`
  (run `python build_launcher.py` once on Windows; PyInstaller required). End users only need the
  built **.exe** plus the `middleware/` and `mod/` folders.
- `ARCHITECTURE.md` — how the mod and the middleware talk to each other.
- License: **MIT** (see `LICENSE`).


---

## Multiplayer (experimental beta)

This fork adds an experimental multiplayer mode. The host runs the AI and the
console injector; clients forward their in-game decisions to the host over HTTP
and get the AI's replies in a small agent window. See
**[MULTIPLAYER.md](MULTIPLAYER.md)** for the feasibility analysis and
**[BETA_TESTING.md](BETA_TESTING.md)** for setup and the tester checklist.
