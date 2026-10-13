"""
mp_server.py - HOST-SIDE multiplayer arbiter for Voices of History.

Run ON THE HOST MACHINE ONLY (via mp_main.py or START_MP_HOST.bat). It attaches to
the normal middleware App and exposes a tiny HTTP API so client machines can use
the HOST's AI and - more importantly - the HOST's console injector. The host stays
the ONLY executor: every LLM call and every console injection still goes through
the single host App instance, so the synchronized game state is only ever modified
by the host.

Design notes:
- CHANNELS. "leader:<tag>" is SHARED: every player talking to the same leader
  joins the same conversation and the same treaty memory (a feature, not a bug).
  "decree:<player>" and "life:<player>" are PER-PLAYER (private staff/leader chat).
- CLIENT STATE. Clients forward their own AIDIPLO_STATE line; during that
  client's pipeline the arbiter swaps it in as the App's latest_state, so the AI
  sees the CLIENT's nation (and ROOT-substitution in console commands resolves to
  the client's tag). Swaps are serialized behind llm_lock.
- RAW LINES. Clients forward raw game.log lines and the HOST parses them with its
  own game_state module, so the wire protocol never drifts from the mod format.
- PLAN REMINDER. The host middleware's automatic "launch a start_plan" reminders
  only fire on its own channel names; on client decree channels the arbiter adds
  the reminder itself from a keyword heuristic.

Wire protocol (JSON over HTTP, optional X-MP-Key header):
  GET  /ping                                             -> {"ok": true, "version": ...}
  POST /open   {player, line}     (raw AIDIPLO_*_OPEN)   -> {"ok": true, "channel": ...}
  POST /state  {player, line}     (raw AIDIPLO_STATE)    -> {"ok": true}
  POST /send   {player, text}                            -> {"ok": true, "reply": ...}
  POST /close  {player}                                 -> {"ok": true}
"""
import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import game_state as gs
import prompts
from mp_version import MP_VERSION, MP_PROTOCOL

DEFAULT_CONFIG = {
    "enabled": True,
    "port": 8710,
    "password": "",
    "max_requests_per_day": 8,
    "auto_pause": False,
}

_PLAN_WORDS = re.compile(
    r"\b(plan|programme|program|industriali[sz]e|industriali[sz]ation|rearm|"
    r"rearmament|mobilis[ez]e|mobilisation|mobilization|five.year|five year|"
    r"build.up|buildup|reform|modernis[ez]e|modernis[ez]ation|expansion|"
    r"undertaking|campaign|overhaul)\b", re.I)


class MPServer:
    """Attaches to a running middleware App and serves client requests."""

    def __init__(self, app, config_path=None):
        self.app = app
        here = os.path.dirname(os.path.abspath(__file__))
        path = config_path or os.path.join(here, "mp_config.json")
        cfg = dict(DEFAULT_CONFIG)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cfg.update(json.load(f))
            except Exception as e:
                print("[MP] bad mp_config.json, using defaults:", e)
        self.cfg = cfg
        self.enabled = bool(cfg.get("enabled", True))
        self.port = int(cfg.get("port", 8710))
        self.password = str(cfg.get("password", ""))
        self.max_requests = int(cfg.get("max_requests_per_day", 8))
        self.auto_pause = bool(cfg.get("auto_pause", False))
        self.sessions = {}            # player -> session dict
        self.lock = threading.Lock()
        self.llm_lock = threading.Semaphore(1)   # ONE AI pipeline at a time

    # ---------------- helper ----------------
    def _session(self, player):
        with self.lock:
            return self.sessions.get(player)

    def _note(self, msg):
        self.app.q.put(("sysnote", "[MP] " + str(msg)))

    def _game_day(self):
        try:
            return int(float(getattr(self.app, "day", 0) or 0))
        except Exception:
            return 0

    # ---------------- endpoints ----------------
    def ping(self):
        with self.lock:
            players = {p: s.get("channel") for p, s in self.sessions.items()}
        return {"ok": True, "version": MP_VERSION, "protocol": MP_PROTOCOL,
                "day": self._game_day(), "players": players}

    def open_channel(self, player, line):
        line = line or ""
        # 1) leader dialogue: AIDIPLO_OPEN|target=GER|tname=...|tleader=...
        op = gs.parse_open_line(line)
        if op:
            target = (op.get("target") or "").strip().upper()
            if len(target) != 3 or not target.isalpha():
                return {"ok": False, "error": "invalid target tag"}
            sess = self._session(player) or {}
            pname = (sess.get("state") or {}).get("name") or "our nation"
            channel = "leader:" + target
            system_prompt = prompts.build_leader_system(
                target, op.get("tname") or target,
                op.get("tleader") or op.get("tname") or target, pname)
            self._set_channel(player, channel,
                              op.get("tleader") or op.get("tname") or target,
                              system_prompt)
            self._note(str(player) + " opened " + channel)
            return {"ok": True, "channel": channel}
        # 2) head of state office: AIDIPLO_DECREE_OPEN|
        if gs.is_decree_open(line):
            sess = self._session(player) or {}
            st = sess.get("state") or {}
            ptag = st.get("tag") or "ROOT"
            pname = st.get("name") or "our nation"
            channel = "decree:" + str(player)
            system_prompt = prompts.build_decree_system(ptag, pname)
            self._set_channel(player, channel, "Supreme Command", system_prompt)
            self._note(str(player) + " opened their Head of State Office")
            return {"ok": True, "channel": channel}
        # 3) life of the head of state: AIDIPLO_LIFE_OPEN|tag=...|leader=...
        lf = gs.parse_life_open(line)
        if lf is not None and "AIDIPLO_LIFE_OPEN|" in line:
            sess = self._session(player) or {}
            st = sess.get("state") or {}
            ptag = lf.get("tag") or st.get("tag") or "ROOT"
            pname = st.get("name") or "our nation"
            leader = lf.get("leader") or st.get("leader") or "the Head of State"
            channel = "life:" + str(player)
            system_prompt = prompts.build_leaderlife_system(ptag, pname, leader)
            self._set_channel(player, channel, leader, system_prompt)
            self._note(str(player) + " opened Life of the Head of State")
            return {"ok": True, "channel": channel}
        return {"ok": False, "error": "unrecognized open line (use the in-game "
                "'Talk to the Leader' or 'Head of State Office' decision first)"}

    def _set_channel(self, player, channel, channel_name, system_prompt):
        with self.lock:
            sess = self.sessions.setdefault(player, {})
            prev = sess.get("channel")
            sess.update({
                "channel": channel,
                "channel_name": channel_name,
                "system_prompt": system_prompt,
                "requests": sess.get("requests", 0) if prev == channel else 0,
                "day": sess.get("day", self._game_day()),
                "state": sess.get("state"),
            })

    def set_state(self, player, line):
        st = gs.parse_state_line(line or "")
        if not st:
            return {"ok": False, "error": "bad AIDIPLO_STATE line"}
        with self.lock:
            sess = self.sessions.setdefault(player, {})
            sess["state"] = st
        return {"ok": True, "tag": st.get("tag"), "name": st.get("name")}

    def send(self, player, text):
        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "empty message"}
        sess = self._session(player)
        if not sess or not sess.get("channel"):
            return {"ok": False, "error": "no open channel: use the in-game "
                    "'Talk to the Leader' or 'Head of State Office' decision first"}
        # per-in-game-day budget
        day = self._game_day()
        if day != sess.get("day"):
            sess["day"] = day
            sess["requests"] = 0
        if self.max_requests > 0 and sess.get("requests", 0) >= self.max_requests:
            return {"ok": False, "error": "request budget exhausted for this "
                    "in-game day (resets next in-game day)"}
        with self.llm_lock:
            self._note(str(player) + " -> " + sess["channel"])
            if self.auto_pause:
                self.app._dispatch(["pause"])
            # plan-launch reminder for client decree channels (the host
            # middleware's own reminder only fires on its native channel names)
            if sess["channel"].startswith("decree:") and _PLAN_WORDS.search(text):
                text += ("\n\n[SYSTEM REMINDER: the player is asking to LAUNCH a "
                         "long-term plan/undertaking. You MUST emit a start_plan "
                         "action in THIS reply, with sensible 'stages' (2-4) and "
                         "'days', plus the immediate COST.]")
            saved_state = self.app.latest_state
            try:
                if sess.get("state"):
                    self.app.latest_state = dict(sess["state"])
                self.app._do_llm(text, sess["channel"], sess["channel_name"],
                                 sess["system_prompt"])
            except Exception as e:
                return {"ok": False, "error": "host pipeline failed: " + str(e)}
            finally:
                self.app.latest_state = saved_state
            reply = self._last_reply(sess["channel"])
        sess["requests"] = sess.get("requests", 0) + 1
        if reply is None:
            return {"ok": False, "error": "the AI did not reply (check the host log)"}
        return {"ok": True, "reply": reply,
                "requests_left": max(0, self.max_requests - sess["requests"])}

    def close(self, player):
        with self.lock:
            self.sessions.pop(player, None)
        return {"ok": True}

    def _last_reply(self, channel):
        try:
            hist = self.app.memory.get_history(channel, 1)
        except Exception:
            return None
        if hist and hist[-1].get("role") == "assistant":
            return hist[-1].get("content") or ""
        return None

    # ---------------- HTTP ----------------
    def start(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def _reply(self, code, obj):
                data = json.dumps(obj).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _auth(self):
                if not server.password:
                    return True
                return self.headers.get("X-MP-Key", "") == server.password

            def do_GET(self):
                if self.path != "/ping":
                    self._reply(404, {"ok": False, "error": "unknown endpoint"})
                    return
                self._reply(200, server.ping())

            def do_POST(self):
                if not self._auth():
                    self._reply(401, {"ok": False, "error": "bad key"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                except Exception:
                    self._reply(400, {"ok": False, "error": "bad JSON"})
                    return
                if self.path == "/open":
                    out = server.open_channel(body.get("player"), body.get("line"))
                elif self.path == "/state":
                    out = server.set_state(body.get("player"), body.get("line"))
                elif self.path == "/send":
                    out = server.send(body.get("player"), body.get("text"))
                elif self.path == "/close":
                    out = server.close(body.get("player"))
                else:
                    out = {"ok": False, "error": "unknown endpoint"}
                self._reply(200, out)

            def log_message(self, fmt, *args):
                pass

        self.httpd = ThreadingHTTPServer(("0.0.0.0", self.port), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        print("[MP] arbiter v" + MP_VERSION + " listening on 0.0.0.0:" + str(self.port))
        if not self.password:
            print("[MP] WARNING: no password set - anyone on your LAN can use "
                  "your AI and inject into your game.")
