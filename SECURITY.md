# Is it safe? — Security & transparency

This project is **open source** so you don't have to take our word for it: you can read every line,
run it from source, or build the launcher yourself. This page explains exactly what the companion
app does on your PC, what it touches, and — just as importantly — what it does **not** do.

## What the companion app does
The companion app (the `middleware/` chat window, started by the launcher) connects the in-game mod
to a **local AI**. Concretely, while you play it:

- **Reads** Hearts of Iron IV's log file `…/Documents/Paradox Interactive/Hearts of Iron IV/logs/game.log`.
  That's how it sees the game state the mod writes out (your nation, the world, your decisions).
- **Sends commands to the game** the only way a HoI4 mod can without an official API: it writes a
  small text file (`aidiplo.txt`) inside your HoI4 folder and makes the game run it by briefly
  focusing the HoI4 window and typing the console command `run aidiplo.txt`. The file's contents are
  plain text you can open and read — only standard HoI4 console effects/events, nothing else.
- While it types that one command, it **briefly blocks keyboard/mouse input** (a fraction of a
  second) so a stray keypress can't corrupt the command. This is the only reason it asks for
  **administrator rights** (the UAC prompt). You can decline — it still works, just with weaker
  typing protection.
- **Writes** the mod's localisation file (the dynamic leader/nation names shown in events).
- **Talks to your local AI** through the **Player2** app over `localhost` (your own machine).
- **Stores a small local file** (`ai_diplo_memory.sqlite3`) with the chat/plan history for your save.

## What it does NOT do
- **No telemetry, no analytics, no accounts, no cloud.** Your conversations and game data never
  leave your PC.
- **No network access** except: your **local** AI on `localhost`, and a one-time `pip install` from
  the official Python package index (PyPI) to fetch dependencies the first time. That's it.
- **No changes** to your system, registry, or files outside the HoI4 mod/log folders and its own
  local memory file.
- **It does not read or send your personal files.**

## Dependencies
Standard, widely-used PyPI packages (see `middleware/requirements.txt`):
`requests`, `pydirectinput`, `PyGetWindow`, `pyautogui`, `pyperclip`. They are used to read the log,
focus the game window and simulate the keystrokes for the `run` command.

## How to verify it yourself
- **Read the code.** It's all here — `middleware/` (the app) and `launcher.py` (the launcher). Plain
  Python, no obfuscation.
- **Run from source instead of the .exe**, if you prefer not to trust a binary:
  ```
  cd middleware
  pip install -r requirements.txt
  python main.py
  ```
- **Build the launcher yourself** so the `.exe` is one you produced from this source:
  ```
  python build_launcher.py
  ```
- **Inspect what gets typed into the game**: open the generated `aidiplo.txt` in your HoI4 folder —
  it only ever contains standard console commands.

## Reporting an issue
Found something concerning? Please open a GitHub Issue (or a private security advisory) with the
details and we'll address it.
