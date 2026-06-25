"""
memory.py
Memoria persistente PER-PARTITA (SQLite).

Ogni partita ha un ID univoco ('gameid') che HoI4 salva come variabile: quindi
caricando un salvataggio della stessa campagna si ritrova la stessa memoria.
Ogni voce e' marcata col GIORNO di gioco ('day', anch'esso salvato): cosi' se
il giocatore carica un salvataggio PIU' VECCHIO, l'IA ricorda solo cio' che e'
accaduto FINO a quella data (le voci con day > giorno corrente vengono ignorate).

Conserva: conversazioni, fatti/trattati, e i PIANI a tempo in sospeso (con il loro
payload) cosi' sopravvivono alla chiusura del middleware e si riallineano al save.
"""
import sqlite3
import json
import threading
import time


class Memory:
    def __init__(self, db_path):
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.gameid = 0
        self.day = 0
        c = self.conn
        c.execute("""CREATE TABLE IF NOT EXISTS messages(
            id INTEGER PRIMARY KEY AUTOINCREMENT, gameid INTEGER DEFAULT 0,
            day INTEGER DEFAULT 0, channel TEXT, role TEXT, content TEXT, ts REAL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS facts(
            id INTEGER PRIMARY KEY AUTOINCREMENT, gameid INTEGER DEFAULT 0,
            day INTEGER DEFAULT 0, kind TEXT, text TEXT, ts REAL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS plans(
            id INTEGER PRIMARY KEY AUTOINCREMENT, gameid INTEGER DEFAULT 0,
            slot INTEGER, title TEXT, payload TEXT, facts TEXT DEFAULT '',
            meta TEXT DEFAULT '{}', created_day INTEGER, eta_day INTEGER,
            done INTEGER DEFAULT 0, ts REAL)""")
        # contatori cumulativi per-partita (es. quanti research slot la mod ha gia' concesso
        # a una nazione: cap di 4 per partita). PRIMARY KEY per l'upsert.
        c.execute("""CREATE TABLE IF NOT EXISTS counters(
            gameid INTEGER DEFAULT 0, name TEXT, value INTEGER DEFAULT 0,
            PRIMARY KEY(gameid, name))""")
        # migrazione soft di vecchi DB (ignora se le colonne esistono gia')
        for tbl, col in (("messages", "gameid"), ("messages", "day"),
                         ("facts", "gameid"), ("facts", "day"),
                         ("plans", "gameid")):
            try:
                c.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} INTEGER DEFAULT 0")
            except Exception:
                pass
        # colonne TESTO eventualmente mancanti sulla tabella plans dei DB vecchi
        for stmt in ("ALTER TABLE plans ADD COLUMN facts TEXT DEFAULT ''",
                     "ALTER TABLE plans ADD COLUMN meta TEXT DEFAULT '{}'"):
            try:
                c.execute(stmt)
            except Exception:
                pass
        c.commit()

    def set_context(self, gameid, day):
        try:
            self.gameid = int(gameid)
            self.day = int(day)
        except Exception:
            pass

    # ---------------- messaggi ----------------
    def add_message(self, channel, role, content):
        with self.lock:
            self.conn.execute(
                "INSERT INTO messages(gameid,day,channel,role,content,ts) VALUES(?,?,?,?,?,?)",
                (self.gameid, self.day, channel, role, content, time.time()))
            self.conn.commit()

    def first_player_message(self):
        """Il PRIMO messaggio scritto dal player in QUESTA partita (per fissare la LINGUA da usare
        in tutte le narrazioni, anche quelle autonome come i giornali che non hanno input)."""
        with self.lock:
            row = self.conn.execute(
                "SELECT content FROM messages WHERE gameid=? AND role='user' AND content!='' "
                "ORDER BY id ASC LIMIT 1", (self.gameid,)).fetchone()
        return (row[0] if row else "") or ""

    def get_history(self, channel, limit=40):
        with self.lock:
            rows = self.conn.execute(
                "SELECT role,content FROM messages WHERE gameid=? AND day<=? AND channel=? "
                "ORDER BY id DESC LIMIT ?",
                (self.gameid, self.day, channel, limit)).fetchall()
        return [{"role": r, "content": c} for (r, c) in reversed(rows)]

    # ---------------- fatti ----------------
    def remember_fact(self, kind, text):
        with self.lock:
            self.conn.execute(
                "INSERT INTO facts(gameid,day,kind,text,ts) VALUES(?,?,?,?,?)",
                (self.gameid, self.day, kind, text, time.time()))
            self.conn.commit()

    def facts_block(self, limit=25):
        with self.lock:
            rows = self.conn.execute(
                "SELECT kind,text FROM facts WHERE gameid=? AND day<=? "
                "ORDER BY id DESC LIMIT ?",
                (self.gameid, self.day, limit)).fetchall()
        if not rows:
            return "No agreements/events recorded so far in this game."
        items = [f"[{k}] {t}" for (k, t) in reversed(rows)]
        return ("GAME HISTORY MEMORY (agreements, events, plans, and real in-game world "
                "developments tagged [world] — wars, capitulations, government changes: "
                "stay consistent with these):\n" + "\n".join(items))

    # ---------------- piani a tempo ----------------
    def add_plan(self, slot, title, payload, created_day, eta_day, facts="", meta=None):
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO plans(gameid,slot,title,payload,facts,meta,created_day,eta_day,done,ts) "
                "VALUES(?,?,?,?,?,?,?,?,0,?)",
                (self.gameid, slot, title, json.dumps(payload), facts,
                 json.dumps(meta or {}), created_day, eta_day, time.time()))
            self.conn.commit()
            return cur.lastrowid

    def update_plan_meta(self, plan_id, meta):
        # Aggiorna PER ID univoco (rowid): immune a un gameid instabile, cosi' lo stato del
        # piano (stage_idx, ecc.) si salva SEMPRE e reconcile non lo ri-esegue da capo.
        if not plan_id:
            return
        with self.lock:
            self.conn.execute("UPDATE plans SET meta=? WHERE id=?",
                              (json.dumps(meta or {}), int(plan_id)))
            self.conn.commit()

    def active_plans(self):
        with self.lock:
            rows = self.conn.execute(
                "SELECT id,slot,title,payload,facts,meta,created_day,eta_day FROM plans "
                "WHERE gameid=? AND done=0", (self.gameid,)).fetchall()
        out = []
        for pid, slot, title, payload, facts, meta, cday, eta in rows:
            try:
                pl = json.loads(payload)
            except Exception:
                pl = []
            try:
                mt = json.loads(meta) if meta else {}
            except Exception:
                mt = {}
            d = {"slot": slot, "title": title, "payload": pl, "facts": facts or "",
                 "created_day": cday, "eta_day": eta}
            d.update(mt)  # stages_total, stage_idx, segment, ecc.
            d["id"] = pid            # chiave STABILE per salvare/segnare-finito senza errori
            d["gid"] = self.gameid   # a quale PARTITA appartiene il piano (anti contaminazione)
            out.append(d)
        return out

    def mark_plan_done(self, plan_id):
        # Segna finito PER ID univoco (rowid): cosi' un piano completato NON viene mai
        # ricaricato/ri-eseguito (era la causa dei completamenti doppi e del tempo collassato).
        if not plan_id:
            return
        with self.lock:
            self.conn.execute("UPDATE plans SET done=1 WHERE id=?", (int(plan_id),))
            self.conn.commit()

    # ---------------- contatori cumulativi (per cap come i research slot) ----------------
    def counter_get(self, name):
        with self.lock:
            row = self.conn.execute("SELECT value FROM counters WHERE gameid=? AND name=?",
                                    (self.gameid, name)).fetchone()
        return int(row[0]) if row else 0

    def counter_add(self, name, delta):
        with self.lock:
            self.conn.execute(
                "INSERT INTO counters(gameid,name,value) VALUES(?,?,?) "
                "ON CONFLICT(gameid,name) DO UPDATE SET value=value+excluded.value",
                (self.gameid, name, int(delta)))
            self.conn.commit()

    def discard_future_plans(self, current_day):
        """Su caricamento di un save vecchio: elimina piani creati DOPO la data corrente."""
        with self.lock:
            self.conn.execute("DELETE FROM plans WHERE gameid=? AND created_day>?",
                              (self.gameid, current_day))
            self.conn.commit()

    def revive_loaded_plans(self, current_day):
        """Su caricamento di un save PRECEDENTE: un piano che risulta GIA' completato (done=1) ma
        la cui finestra temporale include ANCORA la data caricata (created_day <= oggi < eta_day)
        non e' davvero finito in QUESTA timeline -> lo RIATTiviamo (done=0), cosi' i suoi bivi e il
        completamento riavvengono al momento giusto invece di essere trattati come gia' fatti."""
        with self.lock:
            self.conn.execute(
                "UPDATE plans SET done=0 WHERE gameid=? AND done=1 AND created_day<=? AND eta_day>?",
                (self.gameid, current_day, current_day))
            self.conn.commit()
