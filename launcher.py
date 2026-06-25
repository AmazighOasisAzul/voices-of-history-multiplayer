#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VOICES OF HISTORY - Launcher
Un solo launcher grafico che sostituisce i vecchi .bat. Tre azioni:
  - Start Middleware : avvia la chat IA (trova Python, installa le dipendenze se mancano, lancia main.py)
  - Install / Update Mod : copia la mod nella cartella di Hearts of Iron IV e la registra per il launcher
  - Repair Launcher : svuota la cache del launcher Paradox (se mostra "path invalid")
Solo libreria standard di Python (tkinter/os/sys/subprocess/shutil): si impacchetta facilmente in .exe.
"""
import os
import sys
import threading
import subprocess
import shutil
import tkinter as tk

# ---------- tema (coerente con l'overlay della mod) ----------
C_BG     = "#15191e"
C_PANEL  = "#1b2026"
C_CARD   = "#232a32"
C_GOLD   = "#d7b56a"
C_TEXT   = "#e8e3d6"
C_MUTED  = "#8a97a0"
C_OK     = "#7ec27e"
C_ERR    = "#d98a8a"
C_HEADER = "#0f1216"

MOD_NAME = "HOI4_AI_Diplomacy"
MOD_TITLE = "HOI4 AI Mod Voices of History"
SUPPORTED = "1.19.*"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def app_dir():
    """Cartella del launcher (radice del progetto, accanto a middleware/ e mod/)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


# ============================================================
#  RICERCA PERCORSI
# ============================================================
def find_hoi4_dir():
    """La cartella REALE di HoI4 (quella con settings.txt; evita la 'fantasma' su OneDrive)."""
    up = os.environ.get("USERPROFILE", "") or os.path.expanduser("~")
    rel = os.path.join("Paradox Interactive", "Hearts of Iron IV")
    bases = []
    for env in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        v = os.environ.get(env)
        if v:
            bases.append(os.path.join(v, "Documents"))
    bases += [os.path.join(up, "OneDrive", "Documents"), os.path.join(up, "Documents")]
    cands = []
    for b in bases:
        for c in (os.path.join(b, rel),):
            if c not in cands:
                cands.append(c)
    for c in cands:                                  # preferisci quella con settings.txt
        if os.path.isfile(os.path.join(c, "settings.txt")):
            return c
    for c in cands:                                  # ripiego: la prima che esiste
        if os.path.isdir(c):
            return c
    return None


def find_python():
    """Un Python utilizzabile per il middleware: copia privata, oppure Python di sistema con tkinter."""
    priv = os.path.join(os.environ.get("LocalAppData", ""), "VoicesOfHistory", "Python", "python.exe")
    if os.path.isfile(priv):
        return priv
    for exe in ("python", "py", "python3"):
        try:
            r = subprocess.run([exe, "-c", "import tkinter"],
                               creationflags=NO_WINDOW, capture_output=True, timeout=15)
            if r.returncode == 0:
                return exe
        except Exception:
            pass
    return None


# ============================================================
#  AZIONI (girano su thread, scrivono nel log)
# ============================================================
class Launcher:
    def __init__(self, root):
        self.root = root
        self._busy = False
        self._build_ui()

    # ---- log ----
    def log(self, text, tag="info"):
        def _w():
            self.txt.config(state="normal")
            self.txt.insert("end", text + "\n", tag)
            self.txt.see("end")
            self.txt.config(state="disabled")
        self.root.after(0, _w)

    def _run(self, fn):
        if self._busy:
            self.log("Wait — another task is still running...", "muted")
            return
        self._busy = True
        def wrap():
            try:
                fn()
            except Exception as e:
                self.log(f"[ERROR] {e}", "err")
            finally:
                self._busy = False
        threading.Thread(target=wrap, daemon=True).start()

    # ---- 1) START MIDDLEWARE ----
    def start_middleware(self):
        mw = os.path.join(app_dir(), "middleware")
        if not os.path.isdir(mw):
            self.log("[ERROR] 'middleware' folder not found next to the launcher.", "err")
            return
        py = find_python()
        if not py:
            self.log("[ERROR] Python not found. Install Python 3.10+ from python.org", "err")
            self.log("        (tick 'Add to PATH' and keep 'tcl/tk and IDLE' checked), then retry.", "muted")
            return
        self.log(f"Using Python: {py}", "muted")
        # dipendenze: installa SOLO se mancano
        try:
            chk = subprocess.run([py, "-c", "import requests, pydirectinput, pygetwindow, pyautogui, pyperclip"],
                                 cwd=mw, creationflags=NO_WINDOW, capture_output=True, timeout=20)
        except Exception:
            chk = None
        if chk is None or chk.returncode != 0:
            self.log("Installing dependencies (first time only, please wait)...", "info")
            try:
                subprocess.run([py, "-m", "pip", "install", "--disable-pip-version-check",
                                "--no-input", "--no-warn-script-location", "--timeout", "60",
                                "-r", "requirements.txt"], cwd=mw, creationflags=NO_WINDOW, timeout=600)
            except Exception as e:
                self.log(f"[WARNING] Could not install dependencies: {e}", "err")
        # lancia il middleware (finestra propria; lasciala aperta mentre giochi)
        try:
            subprocess.Popen([py, "main.py"], cwd=mw)
            self.log("Middleware started. Keep its window open while you play. "
                     "(Press ENTER in the chat box to send.)", "ok")
        except Exception as e:
            self.log(f"[ERROR] Could not start the middleware: {e}", "err")

    # ---- 2) INSTALL / UPDATE MOD ----
    def install_mod(self):
        src = os.path.join(app_dir(), "mod", MOD_NAME)
        if not os.path.isdir(src):
            self.log(f"[ERROR] Source mod not found: {src}", "err")
            return
        hoi4 = find_hoi4_dir()
        if not hoi4:
            self.log("[ERROR] Hearts of Iron IV folder not found. Launch the game once, then retry.", "err")
            return
        self.log(f"HoI4 folder: {hoi4}", "muted")
        modroot = os.path.join(hoi4, "mod")
        moddir = os.path.join(modroot, MOD_NAME)
        modfile = os.path.join(modroot, MOD_NAME + ".mod")
        try:
            os.makedirs(modroot, exist_ok=True)
            if os.path.isdir(moddir):
                shutil.rmtree(moddir, ignore_errors=True)
            if os.path.isfile(modfile):
                os.remove(modfile)
            self.log("Copying the mod files...", "info")
            shutil.copytree(src, moddir)
        except Exception as e:
            self.log(f"[ERROR] Copy failed: {e}", "err")
            return
        if not os.path.isfile(os.path.join(moddir, "descriptor.mod")):
            self.log("[ERROR] Copy failed: descriptor.mod missing.", "err")
            return
        modpath = moddir.replace("\\", "/")
        descriptor = ('version="0.1.0"\n'
                      f'name="{MOD_TITLE}"\n'
                      f'supported_version="{SUPPORTED}"\n'
                      'tags={\n\t"Gameplay"\n}\n'
                      f'path="{modpath}"\n')
        try:
            with open(modfile, "w", encoding="utf-8") as f:        # .mod esterno (path assoluto)
                f.write(descriptor)
            with open(os.path.join(moddir, "descriptor.mod"), "w", encoding="utf-8") as f:
                f.write(descriptor)                                 # descriptor interno (stesso path)
        except Exception as e:
            self.log(f"[ERROR] Could not write the .mod descriptors: {e}", "err")
            return
        self.log("[OK] Mod installed/updated. Now open the HoI4 Launcher, enable the mod, "
                 "and play in -debug mode.", "ok")
        self.log("     If the launcher says 'path invalid', use Repair Launcher (with the launcher closed).",
                 "muted")

    # ---- 3) REPAIR LAUNCHER ----
    def repair_launcher(self):
        hoi4 = find_hoi4_dir()
        if not hoi4:
            self.log("[ERROR] Hearts of Iron IV folder not found.", "err")
            return
        self.log("Close the HoI4 Launcher BEFORE this (it resets the playset list).", "muted")
        names = ("launcher-v2.sqlite", "launcher-v2.sqlite-wal", "launcher-v2.sqlite-shm",
                 "launcher-v2_openbeta.sqlite", "launcher-v2_openbeta.sqlite-wal",
                 "launcher-v2_openbeta.sqlite-shm")
        deleted = 0
        for n in names:
            p = os.path.join(hoi4, n)
            if os.path.isfile(p):
                try:
                    os.remove(p)
                    deleted += 1
                except Exception as e:
                    self.log(f"[WARNING] Could not delete {n}: {e}", "err")
        self.log(f"[OK] Launcher cache cleared ({deleted} file(s)). Reopen the launcher and re-enable the mod.",
                 "ok")

    # ============================================================
    #  UI
    # ============================================================
    def _card(self, parent, emoji, title, desc, cmd):
        card = tk.Frame(parent, bg=C_CARD, highlightbackground="#2f3843",
                        highlightthickness=1)
        card.pack(fill="x", pady=7)
        btn = tk.Button(card, text=f"  {emoji}   {title}", command=lambda: self._run(cmd),
                        bg=C_CARD, fg=C_GOLD, font=("Georgia", 14, "bold"), relief="flat",
                        activebackground="#2b333c", activeforeground=C_GOLD, anchor="w",
                        cursor="hand2", padx=14, pady=10, bd=0)
        btn.pack(fill="x")
        tk.Label(card, text=desc, bg=C_CARD, fg=C_MUTED, font=("Segoe UI", 9),
                 wraplength=560, justify="left", anchor="w", padx=18).pack(fill="x", pady=(0, 10))

    def _build_ui(self):
        r = self.root
        r.title("Voices of History — Launcher")
        r.configure(bg=C_BG)
        w, h = 640, 660
        try:
            sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
            r.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//3}")
        except Exception:
            r.geometry(f"{w}x{h}")
        r.minsize(560, 560)

        # header
        head = tk.Frame(r, bg=C_HEADER)
        head.pack(fill="x")
        tk.Label(head, text="VOICES OF HISTORY", bg=C_HEADER, fg=C_GOLD,
                 font=("Georgia", 22, "bold")).pack(pady=(18, 0))
        tk.Label(head, text="Hearts of Iron IV — AI Mod  ·  Launcher", bg=C_HEADER,
                 fg=C_MUTED, font=("Segoe UI", 10)).pack(pady=(2, 16))

        body = tk.Frame(r, bg=C_BG)
        body.pack(fill="both", expand=True, padx=22, pady=16)

        self._card(body, "▶", "Start Middleware",
                   "Launch the AI chat that links the mod to your local AI (Player2). "
                   "Keep its window open while you play. In the chat box, press ENTER to send.",
                   self.start_middleware)
        self._card(body, "⬇", "Install / Update Mod",
                   "Copy the mod into your Hearts of Iron IV folder and register it for the "
                   "Paradox launcher. Run this once, and again after every update.",
                   self.install_mod)
        self._card(body, "🛠", "Repair Launcher",
                   "Only if the Paradox launcher shows \"path invalid / does not exist\": clears "
                   "its cache so it rebuilds from the mod. Close the launcher first.",
                   self.repair_launcher)

        tk.Label(body, text="Activity", bg=C_BG, fg=C_GOLD,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(8, 2))
        logbox = tk.Frame(body, bg=C_PANEL, highlightbackground="#2f3843", highlightthickness=1)
        logbox.pack(fill="both", expand=True)
        self.txt = tk.Text(logbox, bg=C_PANEL, fg=C_TEXT, font=("Consolas", 9), relief="flat",
                           wrap="word", height=8, padx=10, pady=8, state="disabled")
        self.txt.pack(side="left", fill="both", expand=True)
        sb = tk.Scrollbar(logbox, command=self.txt.yview, troughcolor=C_PANEL, bg=C_CARD,
                          relief="flat", bd=0, width=12)
        sb.pack(side="right", fill="y")
        self.txt.config(yscrollcommand=sb.set)
        self.txt.tag_config("info", foreground=C_TEXT)
        self.txt.tag_config("muted", foreground=C_MUTED)
        self.txt.tag_config("ok", foreground=C_OK)
        self.txt.tag_config("err", foreground=C_ERR)

        self.log("Welcome. First time: 1) Install / Update Mod  →  2) Start Middleware  →  "
                 "open HoI4 in -debug and enable the mod.", "muted")


def main():
    root = tk.Tk()
    Launcher(root)
    root.mainloop()


if __name__ == "__main__":
    main()
