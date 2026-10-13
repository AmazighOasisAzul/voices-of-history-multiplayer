"""
mp_selftest.py - OFFLINE self-test for the multiplayer layer.

Verifies the arbiter wiring end-to-end WITHOUT HoI4 and WITHOUT an LLM:
it stubs the middleware App (queue, memory, pipeline, state) and exercises
the real HTTP wire protocol the same way a client agent does.

    python mp_selftest.py

All green = the multiplayer layer itself works; any failure in a real session
is then a game-sync or LLM problem, not a wiring problem. Testers should run
this on the host BEFORE hosting (see BETA_TESTING.md, Phase 1).
"""
import json
import queue
import sys
import threading
import time
import urllib.error
import urllib.request

from mp_server import MPServer
from mp_version import MP_VERSION

TEST_PORT = 18710


class FakeMemory:
    """Minimal stand-in for the middleware's SQLite Memory."""

    def __init__(self):
        self.hist = {}
        self.lock = threading.Lock()

    def get_history(self, channel, n):
        with self.lock:
            return list(self.hist.get(channel, []))[-n:]

    def add_message(self, channel, role, content):
        with self.lock:
            self.hist.setdefault(channel, []).append({"role": role, "content": content})

    def facts_block(self):
        return ""


class FakeApp:
    """Minimal stand-in for the middleware App: records what the arbiter does."""

    def __init__(self):
        self.q = queue.Queue()
        self.memory = FakeMemory()
        self.latest_state = {}
        self.day = 42
        self.pipeline_calls = []
        self.dispatched = []
        self._lock = threading.Lock()

    def _do_llm(self, text, channel, channel_name, system_prompt):
        with self._lock:
            self.pipeline_calls.append((text, channel, system_prompt))
        self.memory.add_message(channel, "user", text)
        self.memory.add_message(channel, "assistant", "STUB-REPLY to: " + text)

    def _dispatch(self, cmds):
        with self._lock:
            self.dispatched.extend(cmds)


def http(path, obj, key=None, port=TEST_PORT):
    data = json.dumps(obj).encode("utf-8")
    req = urllib.request.Request("http://127.0.0.1:" + str(port) + path, data=data,
                                 headers={"Content-Type": "application/json"})
    if key:
        req.add_header("X-MP-Key", key)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    app = FakeApp()
    srv = MPServer(app)
    srv.password = "test-key"
    srv.max_requests = 2
    srv.port = TEST_PORT
    srv.start()
    time.sleep(0.3)

    failures = []

    def check(name, cond, detail=""):
        print(("PASS " if cond else "FAIL ") + name + ("  " + detail if detail and not cond else ""))
        if not cond:
            failures.append(name)

    # 1. ping + version
    r = http("/ping", {}, key="test-key")
    check("ping ok", r.get("ok") is True)
    check("ping version reported", r.get("version") == MP_VERSION, str(r))
    check("ping day", r.get("day") == 42, str(r))

    # 2. auth enforced
    try:
        http("/ping", {}, key="wrong")
        check("bad key rejected", False, "server accepted wrong key")
    except urllib.error.HTTPError as e:
        check("bad key rejected", e.code == 401, str(e.code))
    check("open rejected without channel", http("/send", {"player": "A", "text": "hi"}, key="test-key").get("ok") is False)

    # 3. client state submission (real mod line format)
    st_line = ("AIDIPLO_STATE|date=1936.1.2|tag=POR|name=Portugal|stab=0.6|"
               "ws=0.7|pp=23|civ=14|mil=6|mp=1.2|wt=0.0|war=none|leader=Salazar")
    r = http("/state", {"player": "Alice", "line": st_line}, key="test-key")
    check("client state accepted", r.get("ok") is True and r.get("tag") == "POR", str(r))

    # 4. open leader channel (real mod line format)
    open_line = "AIDIPLO_OPEN|target=GER|tname=Germany|tleader=Adolf Hitler"
    r = http("/open", {"player": "Alice", "line": open_line}, key="test-key")
    check("leader channel opens", r.get("ok") is True and r.get("channel") == "leader:GER", str(r))

    # 5. send through the host pipeline: state swap + reply + ROOT substitution hook
    r = http("/send", {"player": "Alice", "text": "Hello, fuhrer."}, key="test-key")
    check("send returns reply", r.get("ok") is True and "STUB-REPLY" in r.get("reply", ""), str(r))
    text, channel, sp = app.pipeline_calls[-1]
    check("state restored after swap", app.latest_state == {} and text == "Hello, fuhrer.", "state not restored")
    check("shared leader channel memory", app.memory.get_history("leader:GER", 10)[-1]["role"] == "assistant")

    # 6. decree channel: per-player + plan reminder injection
    r = http("/open", {"player": "Bob", "line": "AIDIPLO_DECREE_OPEN|"}, key="test-key")
    check("decree channel opens", r.get("ok") is True and r.get("channel") == "decree:Bob", str(r))
    http("/send", {"player": "Bob", "text": "Begin the rearmament programme now."}, key="test-key")
    text2, channel2, _ = app.pipeline_calls[-1]
    check("plan reminder injected on decree channel", "start_plan" in text2, text2)
    check("decree channel is per-player", channel2 == "decree:Bob")

    # 7. actor channel: per-player + coup reminder (stages >= 5)
    r = http("/open", {"player": "Bob", "line": "AIDIPLO_ACTOR_OPEN|tag=POR"}, key="test-key")
    check("actor channel opens", r.get("ok") is True and r.get("channel") == "actor:Bob", str(r))
    http("/send", {"player": "Bob", "text": "We are plotting a coup."}, key="test-key")
    text3, channel3, _ = app.pipeline_calls[-1]
    check("coup reminder injected on actor channel", "start_plan" in text3 and "stages" in text3, text3)

    # 8. budget enforcement
    http("/send", {"player": "Bob", "text": "another"}, key="test-key")
    r = http("/send", {"player": "Bob", "text": "over budget"}, key="test-key")
    check("budget enforced", r.get("ok") is False and "budget" in r.get("error", ""), str(r))

    # 9. close
    check("close ok", http("/close", {"player": "Bob"}, key="test-key").get("ok") is True)

    print("")
    if failures:
        print("SELF-TEST FAILED: " + ", ".join(failures))
        sys.exit(1)
    print("ALL SELF-TESTS PASSED - multiplayer layer v" + MP_VERSION + " is wired correctly.")
    print("Next: run the Phase 0 kill test from BETA_TESTING.md in a real MP session.")


if __name__ == "__main__":
    main()
