#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STRUMENTO PER SVILUPPATORI / AUDIT — i giocatori NON devono eseguirlo.
I giocatori scaricano direttamente VoicesOfHistory.exe (gia' pronto).
Questo script serve solo a chi vuole RICOSTRUIRE l'exe dal sorgente (per verificare che
corrisponda al codice pubblicato, o per modificarlo). Su Windows:
    python build_launcher.py
Installa PyInstaller se manca, crea l'exe (onefile, senza console, con richiesta admin) e lo
copia nella radice del progetto, accanto a middleware/ e mod/.
"""
import os
import sys
import shutil
import subprocess


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    os.chdir(here)

    # 1) assicura PyInstaller
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller non trovato: lo installo...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=False)

    # 2) build (onefile, niente console, richiede privilegi admin per la protezione digitazione)
    cmd = [sys.executable, "-m", "PyInstaller", "--onefile", "--noconsole",
           "--name", "VoicesOfHistory", "--uac-admin", "--clean", "-y"]
    ico = os.path.join(here, "launcher.ico")
    if os.path.isfile(ico):
        cmd += ["--icon", ico]
    cmd.append("launcher.py")
    print("Build:", " ".join(cmd))
    if subprocess.run(cmd).returncode != 0:
        print("\n[ERRORE] Build fallita. Controlla l'output di PyInstaller qui sopra.")
        return

    # 3) copia l'exe nella radice (accanto a middleware/ e mod/)
    built = os.path.join(here, "dist", "VoicesOfHistory.exe")
    if os.path.isfile(built):
        dest = os.path.join(here, "VoicesOfHistory.exe")
        try:
            shutil.copy2(built, dest)
            print("\n[OK] Creato:", dest)
        except Exception as e:
            print("\n[OK] Creato:", built, "(copia nella radice non riuscita:", e, ")")
    else:
        print("\n[ERRORE] Exe non trovato in dist/. Build incompleta.")


if __name__ == "__main__":
    main()
