"""
game_state.py
Parsing delle righe di stato scritte da HoI4 nel game.log:
  AIDIPLO_STATE|date=...|tag=GER|name=Germany|...
e costruzione di un contesto leggibile per l'LLM.
"""

IDEOLOGY = {
    "1": "Fascism",
    "2": "Communism",
    "3": "Democracy",
    "4": "Non-Aligned",
    "0": "Unknown",
}


def parse_state_line(line):
    """Ritorna un dict dallo stato, o None se la riga non e' uno stato valido."""
    marker = "AIDIPLO_STATE|"
    idx = line.find(marker)
    if idx == -1:
        return None
    payload = line[idx + len(marker):].strip()
    state = {}
    for part in payload.split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            state[k.strip()] = v.strip()
    if "tag" not in state:
        return None
    state["ideology_name"] = IDEOLOGY.get(state.get("ideo", "0"), "Unknown")
    return state


def _i(state, key, default=0):
    try:
        return int(float(state.get(key, default)))
    except Exception:
        return default


def war_situation(state):
    """Builds a clear MILITARY SITUATION block from the exported war fields, plus a
    coarse standing label (the AI still judges; this just makes the facts explicit)."""
    if state.get("war", "0") != "1":
        return ("MILITARY SITUATION: at peace. No active war: focus on internal politics, "
                "economy, diplomacy and preparation.")
    cores_lost = _i(state, "cores_lost")
    enemy_land = _i(state, "enemy_land")
    enemies = _i(state, "enemies")
    allies = _i(state, "allies")
    cap = _i(state, "cap", 1)
    # coarse standing
    if cap == 0:
        standing = "CRITICAL — the capital has fallen: collapse or last stand."
    elif cores_lost > 0 and enemy_land == 0:
        standing = "LOSING — home cores are occupied and we hold no enemy land: on the defensive."
    elif cores_lost > enemy_land and cores_lost > 0:
        standing = "STRUGGLING — losing more home ground than we are taking."
    elif enemy_land > 0 and cores_lost == 0:
        standing = "WINNING — our cores are intact and we are advancing into enemy land."
    elif enemy_land > cores_lost:
        standing = "ADVANTAGE — we hold more enemy territory than we have lost."
    else:
        standing = "CONTESTED — the front is roughly balanced."
    return (
        "MILITARY SITUATION (interpret it before deciding ANYTHING):\n"
        f"- Enemies at war with us: {enemies}   Allies in our faction: {allies}\n"
        f"- Home core states occupied by the enemy: {cores_lost}\n"
        f"- Enemy states we currently control: {enemy_land}\n"
        f"- Capital under our control: {'yes' if cap else 'NO (fallen)'}\n"
        f"- Overall standing: {standing}"
    )


def parse_open_line(line):
    """AIDIPLO_OPEN|target=GER|tname=Germany|tleader=...|player=ITA"""
    marker = "AIDIPLO_OPEN|"
    idx = line.find(marker)
    if idx == -1:
        return None
    out = {}
    for part in line[idx + len(marker):].strip().split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out if out.get("target") else None


def parse_tag_line(line):
    """AIDIPLO_TAG|tag=GER|name=Germany  -> (tag, name) per la tabella dinamica."""
    marker = "AIDIPLO_TAG|"
    idx = line.find(marker)
    if idx == -1:
        return None
    out = {}
    for part in line[idx + len(marker):].strip().split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    if out.get("tag") and out.get("name"):
        return (out["tag"], out["name"])
    return None


def parse_plan_done(line):
    """AIDIPLO_PLAN_DONE|slot=N -> indice slot del piano completato."""
    marker = "AIDIPLO_PLAN_DONE|"
    idx = line.find(marker)
    if idx == -1:
        return None
    for part in line[idx + len(marker):].strip().split("|"):
        if part.startswith("slot="):
            try:
                return int(part.split("=", 1)[1])
            except Exception:
                return None
    return None


def parse_choice(line):
    """AIDIPLO_CHOICE|c=N -> scelta dell'opzione (1=A, 2=B) in un bivio di piano."""
    marker = "AIDIPLO_CHOICE|"
    idx = line.find(marker)
    if idx == -1:
        return None
    for part in line[idx + len(marker):].strip().split("|"):
        if part.startswith("c="):
            try:
                return int(part.split("=", 1)[1])
            except Exception:
                return None
    return None


def parse_ack(line):
    """AIDIPLO_ACK|n=N -> N. Conferma che il file di comandi e' stato eseguito in gioco
    (usato per ritentare automaticamente l'iniezione finche' non e' confermata)."""
    marker = "AIDIPLO_ACK|"
    idx = line.find(marker)
    if idx == -1:
        return None
    for part in line[idx + len(marker):].strip().split("|"):
        if part.startswith("n="):
            try:
                return int(part.split("=", 1)[1])
            except Exception:
                return None
    return None


def parse_stateinfo(line):
    """AIDIPLO_STATEINFO|id=2|name=Rome|owner=ITA|mine=1 -> info di UNO stato (regione).
    Serve perche' gli effetti sugli stati richiedono l'ID NUMERICO dello stato."""
    marker = "AIDIPLO_STATEINFO|"
    idx = line.find(marker)
    if idx == -1:
        return None
    out = {}
    for part in line[idx + len(marker):].strip().split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    if not out.get("id"):
        return None
    return out


def states_block(states):
    """Blocco KNOWN STATES per l'LLM: elenca gli stati (regioni) noti con ID e nome, cosi'
    l'IA puo' riferirsi a uno stato per NOME o per ID quando trasferisce regioni, sposta la
    capitale, aggiunge core/rivendicazioni, ecc. (gli effetti sugli stati vogliono l'ID)."""
    note = ("STATES (regions): for any state action (transfer_state, set_capital, add_core, "
            "add_claim, occupy_state) refer to a region by its REAL NAME (e.g. 'Bavaria', "
            "'Marseille', 'Sicily') or by its #ID — EVERY state in the game is known and the "
            "system resolves the name to its ID automatically (so it keeps working even after "
            "you expand). Use real, existing region names; do not invent them.")
    mine = sorted([s for s in states.values() if s.get("mine") == "1"],
                  key=lambda s: s.get("name", ""))
    if mine:
        note += ("\nYOUR current states: "
                 + ", ".join(f"{s.get('name','?')}=#{s.get('id','?')}" for s in mine[:90]))
    return note


def parse_nation(line):
    """AIDIPLO_NATION|tag=..|name=..|ideo=..|stab=..|ws=..|civ=..|mil=..|div=..|states=..|
    war=..|waryou=..|cap=..|fac=..|facyou=..|maj=..|nb=..|subj=..|subjyou=..
    -> stato compatto di UNA nazione rilevante del mondo (snapshot reale del gioco)."""
    marker = "AIDIPLO_NATION|"
    idx = line.find(marker)
    if idx == -1:
        return None
    out = {}
    for part in line[idx + len(marker):].strip().split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    if not out.get("tag"):
        return None
    out["ideology_name"] = IDEOLOGY.get(out.get("ideo", "0"), "Unknown")
    return out


def _nation_line(n):
    """Una riga leggibile e compatta per l'IA, SOLO con fatti reali esportati dal gioco."""
    flags = []
    if n.get("cap") == "1":
        flags.append("CAPITULATED")
    if n.get("waryou") == "1":
        flags.append("AT WAR WITH YOU")
    elif n.get("war") == "1":
        flags.append("at war")
    if n.get("facyou") == "1":
        flags.append("your faction")
    if n.get("subjyou") == "1":
        flags.append("YOUR SUBJECT")
    elif n.get("subj") == "1":
        flags.append("a subject")
    if n.get("maj") == "1":
        flags.append("great power")
    if n.get("nb") == "1":
        flags.append("borders you")
    tail = ("  [" + ", ".join(flags) + "]") if flags else ""
    return (f"- {n.get('name','?')} ({n.get('tag','?')}): {n.get('ideology_name','?')}, "
            f"stab {n.get('stab','?')}%, war supp {n.get('ws','?')}%, "
            f"factories {n.get('civ','?')}c/{n.get('mil','?')}m, "
            f"{n.get('div','?')} divisions, {n.get('states','?')} states{tail}")


def _nation_compact(n):
    """Riga compatta (roster di TUTTE le nazioni): nome(tag) + bandierine essenziali."""
    fl = []
    if n.get("waryou") == "1":
        fl.append("war-vs-you")
    elif n.get("war") == "1":
        fl.append("at war")
    if n.get("cap") == "1":
        fl.append("capitulated")
    if n.get("subjyou") == "1":
        fl.append("your subject")
    elif n.get("subj") == "1":
        fl.append("subject")
    return f"{n.get('name','?')} ({n.get('tag','?')})" + ("[" + ", ".join(fl) + "]" if fl else "")


def world_snapshot_block(world):
    """Blocco WORLD SNAPSHOT dal dict {tag: nation}: la VERITA' di base sul mondo.
    Nessun limite di rilevanza: l'IA deve sapere di TUTTI. Per non perdere contesto ne'
    esplodere, le nazioni CHIAVE (in guerra, grandi potenze, vicini, fazione, sudditi) sono
    in DETTAGLIO, e TUTTE le altre in un roster COMPATTO raggruppato per ideologia."""
    if not world:
        return ("WORLD SNAPSHOT: not available yet (it is exported when you open a channel "
                "or each in-game day).")
    nats = list(world.values())

    def is_key(n):
        return (n.get("waryou") == "1" or n.get("maj") == "1" or n.get("nb") == "1"
                or n.get("facyou") == "1" or n.get("subjyou") == "1" or n.get("war") == "1")

    def keyf(n):
        score = 0
        if n.get("waryou") == "1":
            score -= 100
        if n.get("maj") == "1":
            score -= 10
        if n.get("nb") == "1":
            score -= 5
        if n.get("subjyou") == "1":
            score -= 3
        return (score, n.get("name", ""))

    key_nats = sorted([n for n in nats if is_key(n)], key=keyf)
    detailed, overflow = key_nats[:45], key_nats[45:]
    others = overflow + [n for n in nats if not is_key(n)]

    out = ["WORLD SNAPSHOT — real, current state of the world (GROUND TRUTH: these are the ONLY "
           "facts about other nations; never assume or invent anything beyond them).",
           "KEY nations (in detail):"]
    out += [_nation_line(n) for n in detailed]

    if others:
        groups = {}
        for n in others:
            groups.setdefault(n.get("ideology_name", "Unknown"), []).append(n)
        out.append("ALL OTHER nations (compact roster — name(TAG), flags only if notable):")
        for ideo in ("Fascism", "Communism", "Democracy", "Non-Aligned", "Unknown"):
            grp = groups.get(ideo)
            if not grp:
                continue
            ents = ", ".join(_nation_compact(n) for n in sorted(grp, key=lambda x: x.get("name", "")))
            out.append(f"  {ideo}: {ents}")
    return "\n".join(out)


def parse_world(line):
    """AIDIPLO_WORLD|t=<testo> -> grande sviluppo in gioco (guerra, capitolazione, cambio
    di governo) da ricordare come contesto per l'IA."""
    marker = "AIDIPLO_WORLD|t="
    idx = line.find(marker)
    if idx == -1:
        return None
    txt = line[idx + len(marker):].strip()
    return txt or None


def is_decree_open(line):
    return "AIDIPLO_DECREE_OPEN|" in line


def parse_actor_open(line):
    """AIDIPLO_ACTOR_OPEN|tag=ITA -> agisci come un ALTRO attore interno (fazione,
    generale, cospiratore...), non come il capo di Stato."""
    marker = "AIDIPLO_ACTOR_OPEN|"
    idx = line.find(marker)
    if idx == -1:
        return None
    out = {}
    for part in line[idx + len(marker):].strip().split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out or {}


def parse_life_open(line):
    """AIDIPLO_LIFE_OPEN|tag=ITA|leader=Mussolini"""
    marker = "AIDIPLO_LIFE_OPEN|"
    idx = line.find(marker)
    if idx == -1:
        return None
    out = {}
    for part in line[idx + len(marker):].strip().split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out or {}


def context_for_llm(state, world=None, states=None):
    """Trasforma lo stato in un blocco di testo che diamo all'LLM ad ogni turno.
    Se passato 'world' (dict tag->nazione), accoda lo SNAPSHOT del mondo; se passato
    'states' (dict id->stato), accoda l'elenco delle REGIONI note con i loro ID."""
    extra = ""
    if world:
        extra += "\n\n" + world_snapshot_block(world)
    if states:
        extra += "\n\n" + states_block(states)
    if not state:
        base = "Game state not available yet (press 'Sync state with the AI' in HoI4)."
        return base + extra

    def g(k, d="?"):
        return state.get(k, d)

    subj = g('is_subject') == '1'
    block = (
        "=== CURRENT WORLD STATE (HoI4) ===\n"
        f"Date: {g('date')}\n"
        f"Player nation: {g('name')} ({g('tag')})\n"
        f"Head of State: {g('leader')}\n"
        f"Ruling ideology: {g('ideology_name')}\n"
        f"Stability: {g('stab')}%   War support: {g('ws')}%\n"
        f"Political Power: {g('pp')}\n"
        f"Factories  -> Civilian: {g('civ')}  Military: {g('mil')}  Naval: {g('nav')}\n"
        f"Army: {g('div')} divisions    Available manpower: {g('mp')}\n"
        f"World Tension: {g('wt')}%\n"
        f"At war: {'Yes' if g('war') == '1' else 'No'}\n"
        f"In a faction: {'Yes' if g('faction') == '1' else 'No'}"
        f"{' (faction LEADER)' if g('facleader') == '1' else ''}\n"
        f"Subject states (puppets) we hold: {g('subjects')}\n"
        f"We are a subject (puppet) of another power: {'YES' if subj else 'No'}\n"
        f"Controlled states: {g('states')}\n"
        f"{war_situation(state)}\n"
        "======================================"
    )
    return block + extra
