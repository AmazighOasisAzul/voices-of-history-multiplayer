# Architecture — HOI4 AI Mod Voices of History

## The three-way loop

```
            (1) EXPORT state                    (2) REASONING
   HoI4  ──────────────────────►  game.log  ──►  MIDDLEWARE  ──►  Player2 (LLM)
   (mod)                                          (Python)         (localhost:4315)
     ▲                                               │   ▲              │
     │                                               │   └──── JSON ◄────┘
     │            (3) EXECUTION via console          │   {reason,message,actions}
     └───────────────────────────────────────────────┘
            effect / event / reload  (typed into the console)
```

1. **Export (HoI4 → log).** Once a day (`on_actions/on_daily`) and on every explicit
   request, the scripted effect `ai_diplo_export_state` writes **one line** to the
   `game.log` with the player nation's full state:
   `AIDIPLO_STATE|date=…|tag=…|stab=…|ws=…|pp=…|civ=…|mil=…|mp=…|wt=…|war=…|…`.
   The decisions also write `AIDIPLO_OPEN|target=…` (open a dialogue with a leader)
   and `AIDIPLO_DECREE_OPEN` (open the Head of State Office).

2. **Middleware (Python).** `main.py` *tails* the log in real time:
   - `game_state.py` parses the state and builds the **context** for the AI;
   - `memory.py` (SQLite) stores conversations and **treaties/promises** per game;
   - `prompts.py` builds the **system prompt** (leader persona or Supreme Command
     staff) with the ideological-consistency rules and the function catalog;
   - `llm_client.py` calls **Player2** (OpenAI format) and parses the JSON;
   - `overlay.py` is the chat window (player input + history).

3. **Execution (Middleware → HoI4).** `functions.py` translates each AI `action` into
   real **console commands**; `injector.py` brings HoI4 to the foreground, opens the
   console, **types** the command (typing = robust with the IT layout), presses Enter
   and closes. For **dynamic events** it rewrites the mod localisation, runs
   `reload loc` and fires the event (`event aidiplo.1`); for **rejections** it fires
   `event aidiplo.10`.

## Function calling (dialogue → gameplay)

The AI always replies with JSON:
```json
{ "reason":"…", "message":"…", "actions":[ {"name":"send_equipment",
  "args":{"receiver":"SOV","equipment_type":"rifles","quantity":5000}} ] }
```
The full catalog is in `functions.py → catalog_text()` and is injected into the
system prompt. It covers: sending equipment, manpower, factories, laws and
mobilization, fortifications, regime changes (changes **party and portrait**), civil
wars, factions/alliances, non-aggression pacts (Molotov-Ribbentrop), guarantees,
military access, opinions, declarations of war and war goals, white peace, state
cessions, annexations, puppets, **dynamic events**, anachronistic **rejections**,
named new leaders, country renaming, plus two *escape hatches* (`raw_effect`,
`raw_console`) for **any** valid HoI4 effect/command — so the AI can influence
everything.

## Mod files (folder `mod/HOI4_AI_Diplomacy/`)

| File | Role |
|---|---|
| `common/on_actions/zzz_ai_diplo_on_actions.txt` | daily state export + per-game ID |
| `common/scripted_effects/ai_diplo_export.txt` | builds the `AIDIPLO_STATE` line |
| `common/scripted_effects/ai_diplo_apply.txt` | complex "actions" (regime, mobilization, forts…) |
| `common/decisions/…` | in-game UI (talk to leader / supreme command / sync) |
| `common/scripted_guis/ai_diplo_gui.txt` + `interface/ai_diplo.gui` | top-bar button + chat box design |
| `common/ideas/ai_diplo_ideas.txt` | temporary modifiers (War Drive, Reform Strain…) |
| `common/opinion_modifiers/ai_diplo_opinion.txt` | goodwill/distrust opinions |
| `events/ai_diplo_events.txt` | dynamic event, rejection, plans, crossroads, civil war, new leader (aidiplo.60) |
| `localisation/english/ai_diplo_l_english.yml` | texts (rewritten at runtime for events) |

## How to extend the mod

- **New game action**: add a case in `functions.build_action()` that returns the
  console commands, and describe it in `catalog_text()` so the AI knows about it. For
  complex logic add a scripted effect in `ai_diplo_apply.txt` and call it with
  `effect TAG = {{ effect_name = yes }}`.
- **More data in the state**: add `set_temp_variable` + a field in the `log` line of
  `ai_diplo_export.txt`, then read it in `game_state.context_for_llm()`.
- **Other LLM backends**: change `base_url`/`chat_path` in `config.json` (any
  OpenAI-compatible endpoint).

## Safety/reliability notes
- `dry_run: true` in `config.json` prints the commands without sending them (safe test).
- All AI inputs are **sanitized** (3-letter tags, numbers, whitelisted laws,
  single-line effects, validated idea references) before touching the console.
- The AI **replies in the player's input language**; the base mod texts are English.
