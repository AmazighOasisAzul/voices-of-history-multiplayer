"""
mp_main.py - HOST SIDE ONLY. Runs the normal middleware with the multiplayer
arbiter attached:

    python mp_main.py

If mp_config.json is missing or "enabled" is false, this behaves exactly like
python main.py. No existing middleware file is modified; the arbiter only wraps
the App after it is constructed.
"""
import main
from mp_server import MPServer

_orig_init = main.App.__init__


def _mp_init(self, cfg):
    _orig_init(self, cfg)
    try:
        mp = MPServer(self)
        if mp.enabled:
            mp.start()
            self.mp = mp
            if not mp.password:
                print("[MP] WARNING: no password in mp_config.json - "
                      "anyone on your LAN can use your AI and inject into your game.")
        else:
            print("[MP] disabled in mp_config.json")
    except Exception as e:
        print("[MP] arbiter failed to start:", e)


main.App.__init__ = _mp_init
main.main()
