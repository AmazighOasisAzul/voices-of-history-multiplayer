"""
mp_server.py - HOST-SIDE multiplayer arbiter for Voices of History (experiment).

Run ON THE HOST MACHINE ONLY. It attaches to the normal middleware (see mp_main.py)
and exposes a tiny HTTP API so client machines can use the HOST's AI and - more
importantly - the HOST's console injector. The host stays the ONLY executor: every
LLM call and every console injection still goes through the single host App
instance, so the game's synchronized state is only ever modified by the host.

Wire protocol (JSON over HTTP):
  GET  /ping                                        -> {"ok": true, "day": N, ...}
  POST /open   {player, tag, name, target, tname, tleader}  -> {"ok": true}
  POST /send   {player, text}                       -> {"ok": true, "reply": "..."}
  POST /close  {player}                             -> {"ok": true}

Config: mp_config.json next to this file (port, password, max_requests_per_day).
"""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import prompts

DEFAULT_CONFIG = {
    "enabled": True,
    "port": 8710,
    "password": "",
    "max_requests_per_day": 8,
}


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
        self.sessions = {}            # player -> {channel, channel_name, system_prompt, requests, day}
        self.lock = threading.Lock()
        self.llm_lock = threading.Semaphore(1)   # ONE AI pipeline at a time

    # ---------------- sessions ----------------
    def open_channel(self, player, target, tname, tleader, player_tag, player_name):
        target = (target or "").strip().upper()
        if len(target) != 3 or not target.isalpha():
            return {"ok": False, "error": "invalid target tag"}
        name = player_name or (player_tag or "our nation")
        channel = "leader:" + target
        system_prompt = prompts.build_leader_system(
            target, tname or target, tleader or tname or target, name)
        with self.lock:
            self.sessions[player] = {
                "channel": channel,
                "channel_name": tleader or tname or target,
                "system_prompt": system_prompt,
                "requests": 0,
                "day": self._game_day(),
            }
        self.app.q.put(("sysnote", "[MP] " + str(player) + " opened channel " + channel))
        return {"ok": True, "channel": channel}

    def send(self, player, text):
        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "empty message"}
        with self.lock:
            sess = self.sessions.get(player)
        if not sess:
            return {"ok": False, "error": "no open channel: use the in-game "
                    "'Talk to the Leader' decision first"}
        day = self._game_day()
        if day != sess["day"]:
            sess["day"] = day
            sess["requests"] = 0
        if self.max_requests > 0 and sess["requests"] >= self.max_requests:
            return {"ok": False, "error": "request budget exhausted for this in-game day"}
        with self.llm_lock:
            self.app.q.put(("sysnote", "[MP] " + str(player) + " -> " + sess["channel"]))
            try:
                # Runs the FULL host pipeline (LLM + memory + console injection).
                # Serialized by llm_lock so two clients never interleave injections.
                self.app._do_llm(text, sess["channel"], sess["channel_name"],
                                 sess["system_prompt"])
            except Exception as e:
                return {"ok": False, "error": "host pipeline failed: " + str(e)}
            reply = self._last_reply(sess["channel"])
        sess["requests"] += 1
        if reply is None:
            return {"ok": False, "error": "the AI did not reply (check the host log)"}
        return {"ok": True, "reply": reply,
                "requests_left": max(0, self.max_requests - sess["requests"])}

    def close(self, player):
        with self.lock:
            self.sessions.pop(player, None)
        return {"ok": True}

    def _game_day(self):
        try:
            return int(float(getattr(self.app, "day", 0) or 0))
        except Exception:
            return 0

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
                self._reply(200, {"ok": True, "day": server._game_day(),
                                  "players": list(server.sessions.keys())})

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
                    out = server.open_channel(body.get("player"), body.get("target"),
                                               body.get("tname"), body.get("tleader"),
                                               body.get("tag"), body.get("name"))
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
        print("[MP] arbiter listening on 0.0.0.0:" + str(self.port))
