"""
mp_agent.py - CLIENT SIDE. Run this on every client machine (never the host):

    python mp_agent.py --host 192.168.1.50 --password <pw> --player Alice
    (or use START_MP_CLIENT.bat)

What it does:
- Tails YOUR local game.log and forwards the RAW trigger lines to the host:
  AIDIPLO_STATE (your nation's state, so the AI sees YOUR country),
  AIDIPLO_OPEN (Talk to the Leader), AIDIPLO_DECREE_OPEN (Head of State Office),
  AIDIPLO_LIFE_OPEN (Life of the Head of State),
  AIDIPLO_ACTOR_OPEN (Act as Another Figure).
- You type here; the HOST's AI answers and the HOST's console executes the
  effects, which reach your game through the normal multiplayer sync.
- This machine runs no LLM and injects nothing: display only.

Keys: Enter sends, Shift+Enter inserts a new line.

Requirements: Python 3.10+ (tkinter, stdlib only).
"""
import argparse
import json
import os
import queue
import threading
import time
import tkinter as tk
import urllib.request

from mp_version import MP_VERSION, MP_PROTOCOL

MARK_STATE = "AIDIPLO_STATE|"
MARK_OPEN = "AIDIPLO_OPEN|"
MARK_DECREE = "AIDIPLO_DECREE_OPEN|"
MARK_LIFE = "AIDIPLO_LIFE_OPEN|"
MARK_ACTOR = "AIDIPLO_ACTOR_OPEN|"


def autodetect_game_log():
    home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    candidates = []
    for base in (home, os.path.join(home, "OneDrive")):
        candidates.append(os.path.join(
            base, "Documents", "Paradox Interactive",
            "Hearts of Iron IV", "logs", "game.log"))
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[0]


class Client:
    def __init__(self, args):
        self.args = args
        self.ui_queue = queue.Queue()
        self.last_state_line = ""

    def http(self, path, obj):
        data = json.dumps(obj).encode("utf-8")
        req = urllib.request.Request(
            "http://" + self.args.host + ":" + str(self.args.port) + path, data=data,
            headers={"Content-Type": "application/json"})
        if self.args.password:
            req.add_header("X-MP-Key", self.args.password)
        with urllib.request.urlopen(req, timeout=600) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # ---- background: tail the local game.log ----
    def tail_loop(self):
        path = self.args.game_log
        pos = 0
        announced = False
        while True:
            try:
                if not os.path.exists(path):
                    if not announced:
                        self.ui_queue.put(("sys", "game.log not found: " + path))
                        announced = True
                    time.sleep(2)
                    continue
                size = os.path.getsize(path)
                if size < pos:
                    pos = 0
                chunk = ""
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    f.seek(pos)
                    chunk = f.read()
                    pos = f.tell()
                for line in chunk.splitlines():
                    self.handle_line(line)
            except Exception as e:
                self.ui_queue.put(("sys", "tail error: " + str(e)))
            time.sleep(0.5)

    def handle_line(self, line):
        # state: forward (deduped) so the host's AI knows OUR nation
        if MARK_STATE in line:
            if line.strip() != self.last_state_line:
                self.last_state_line = line.strip()
                self.post_quiet("/state", {"player": self.args.player, "line": line})
            return
        # channel opens: forward raw, host parses with its own game_state module
        # (MARK_ACTOR is checked FIRST: AIDIPLO_ACTOR_OPEN contains no other mark,
        #  but keep the order explicit anyway)
        for mark, label in ((MARK_ACTOR, "underground"), (MARK_OPEN, "leader"),
                            (MARK_DECREE, "office"), (MARK_LIFE, "life")):
            if mark in line:
                try:
                    res = self.http("/open", {"player": self.args.player, "line": line})
                    if res.get("ok"):
                        self.ui_queue.put(("sys", "Channel open (" + label + "): " +
                                          str(res.get("channel")) + ". Type below."))
                    else:
                        self.ui_queue.put(("sys", "Host refused: " + str(res.get("error"))))
                except Exception as e:
                    self.ui_queue.put(("sys", "Cannot reach host: " + str(e)))
                return

    def post_quiet(self, path, obj):
        def work():
            try:
                self.http(path, obj)
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()

    # ---- sending ----
    def send(self, text):
        def work():
            try:
                res = self.http("/send", {"player": self.args.player, "text": text})
                if res.get("ok"):
                    self.ui_queue.put(("ai", res.get("reply", "")))
                    left = res.get("requests_left")
                    if left is not None:
                        self.ui_queue.put(("sys", "requests left this in-game day: " + str(left)))
                else:
                    self.ui_queue.put(("sys", "Host: " + str(res.get("error"))))
            except Exception as e:
                self.ui_queue.put(("sys", "Send failed: " + str(e)))
            finally:
                self.ui_queue.put(("busy", False))
        threading.Thread(target=work, daemon=True).start()

    # ---- UI ----
    def run(self):
        root = tk.Tk()
        root.title("Voices of History - MP client (" + self.args.player + ")")
        self.log = tk.Text(root, width=72, height=22, state="disabled")
        self.log.pack(padx=6, pady=6)
        entry_frame = tk.Frame(root)
        self.entry = tk.Text(entry_frame, width=60, height=3)
        self.entry.pack(side="left", padx=6, pady=6)
        self.btn = tk.Button(entry_frame, text="Send", command=self.on_send)
        self.btn.pack(side="right", padx=6)
        entry_frame.pack()

        # Enter sends; Shift+Enter keeps a newline (default Text binding inserts it)
        self.entry.bind("<Return>", lambda e: (self.on_send(), "break")[1])
        self.entry.bind("<Shift-Return>", lambda e: None)

        def pump():
            try:
                while True:
                    kind, payload = self.ui_queue.get_nowait()
                    self.log.configure(state="normal")
                    if kind == "ai":
                        self.log.insert("end", "[AI] " + payload + "\n\n")
                    elif kind == "sys":
                        self.log.insert("end", "[*] " + payload + "\n")
                    elif kind == "me":
                        self.log.insert("end", "[" + self.args.player + "] " + payload + "\n")
                    elif kind == "busy":
                        self.btn.configure(state="normal" if not payload else "disabled")
                        self.btn.configure(text="..." if payload else "Send")
                    self.log.configure(state="disabled")
                    self.log.see("end")
            except queue.Empty:
                pass
            root.after(200, pump)

        threading.Thread(target=self.tail_loop, daemon=True).start()
        pump()
        self.ui_queue.put(("sys", "Agent v" + MP_VERSION +
                          " -> " + self.args.host + ":" + str(self.args.port)))

        def ping():
            try:
                res = self.http("/ping", {})
                proto = res.get("protocol")
                if proto is not None and proto != MP_PROTOCOL:
                    self.ui_queue.put(("sys", "VERSION MISMATCH: host protocol " +
                                      str(proto) + ", agent protocol " + str(MP_PROTOCOL) +
                                      " - update both to the same release."))
                self.ui_queue.put(("sys", "Host reachable (v" + str(res.get("version")) +
                                   "). In-game day: " + str(res.get("day"))))
            except Exception as e:
                self.ui_queue.put(("sys", "PING FAILED: " + str(e)))
        threading.Thread(target=ping, daemon=True).start()
        root.mainloop()

    def on_send(self):
        text = self.entry.get("1.0", "end").strip()
        if not text:
            return
        self.entry.delete("1.0", "end")
        self.ui_queue.put(("me", text))
        self.ui_queue.put(("busy", True))
        self.send(text)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", required=True, help="host machine IP (LAN/VPN)")
    p.add_argument("--port", type=int, default=8710)
    p.add_argument("--password", default="")
    p.add_argument("--player", required=True, help="your display name")
    p.add_argument("--game-log", default=autodetect_game_log())
    Client(p.parse_args()).run()


if __name__ == "__main__":
    main()
