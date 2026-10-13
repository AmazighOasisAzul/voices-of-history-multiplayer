"""
mp_agent.py - CLIENT SIDE. Run this on every client machine (never the host):

    python mp_agent.py --host 192.168.1.50 --password <the host password> --player Alice

What it does:
- Tails YOUR local game.log. When you use the in-game decision 'Talk to the
  Leader (AI)', the mod writes AIDIPLO_OPEN to YOUR log; the agent forwards it
  to the host arbiter, which opens the channel through the HOST's middleware.
- You type here; the HOST's AI answers and the HOST's console executes the
  effects. This machine runs no LLM and injects nothing: display only.

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

MARK_OPEN = "AIDIPLO_OPEN|"
MARK_STATE = "AIDIPLO_STATE|"


def parse_fields(line, marker):
    idx = line.find(marker)
    if idx == -1:
        return None
    out = {}
    for part in line[idx + len(marker):].strip().split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


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
        self.own_tag = ""
        self.own_name = ""

    def http(self, path, obj):
        data = json.dumps(obj).encode("utf-8")
        req = urllib.request.Request(
            "http://" + self.args.host + ":" + str(self.args.port) + path, data=data,
            headers={"Content-Type": "application/json"})
        if self.args.password:
            req.add_header("X-MP-Key", self.args.password)
        with urllib.request.urlopen(req, timeout=300) as resp:
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
        st = parse_fields(line, MARK_STATE)
        if st and st.get("tag"):
            self.own_tag = st.get("tag", "")
            self.own_name = st.get("name", "")
            return
        op = parse_fields(line, MARK_OPEN)
        if op and op.get("target"):
            try:
                res = self.http("/open", {
                    "player": self.args.player,
                    "tag": self.own_tag, "name": self.own_name,
                    "target": op.get("target"),
                    "tname": op.get("tname", op.get("target")),
                    "tleader": op.get("tleader", "")})
                if res.get("ok"):
                    self.ui_queue.put(("sys", "Channel opened with " +
                                       (op.get("tleader") or op.get("tname") or
                                        op.get("target")) + ". Type below."))
                else:
                    self.ui_queue.put(("sys", "Host refused: " + str(res.get("error"))))
            except Exception as e:
                self.ui_queue.put(("sys", "Cannot reach host: " + str(e)))

    # ---- sending ----
    def send(self, text):
        def work():
            try:
                res = self.http("/send", {"player": self.args.player, "text": text})
                if res.get("ok"):
                    self.ui_queue.put(("ai", res.get("reply", "")))
                    left = res.get("requests_left")
                    if left is not None:
                        self.ui_queue.put(("sys", "requests left today: " + str(left)))
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
        btn = tk.Button(entry_frame, text="Send", command=self.on_send)
        btn.pack(side="right", padx=6)
        entry_frame.pack()
        root.bind("<Return>", lambda e: self.on_send())

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
                        btn.configure(state="normal" if not payload else "disabled")
                    self.log.configure(state="disabled")
                    self.log.see("end")
            except queue.Empty:
                pass
            root.after(200, pump)

        threading.Thread(target=self.tail_loop, daemon=True).start()
        pump()
        self.ui_queue.put(("sys", "Connecting to " + self.args.host + ":" + str(self.args.port)))
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
