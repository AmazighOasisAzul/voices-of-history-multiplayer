"""
overlay.py
Interfaccia in stile Hearts of Iron IV:
- un PANNELLO LATERALE slim, ancorato al bordo destro, senza barra del titolo
  del sistema operativo (overrideredirect) e con tema scuro/oro come HoI4;
- quando non si sta chattando il pannello e' nascosto e resta solo una piccola
  LINGUETTA "IA" sul bordo destro; cliccandola (o aprendo una chat in gioco)
  il pannello scorre dentro.
Tutto cio' che tocca la UI gira sul thread principale di Tk.
"""
import tkinter as tk
from tkinter import scrolledtext

# --- palette stile HoI4 ---
C_BG      = "#1c2427"   # sfondo pannello
C_HEADER  = "#2a3a33"   # barra titolo
C_GOLD    = "#d7b56a"   # oro / accento
C_TEXT    = "#cfd6dd"
C_MUTED   = "#8a97a0"
C_HIST    = "#12181b"
C_INPUT   = "#0e1316"
C_BTN     = "#33433b"
C_PLAYER  = "#7fb3ff"
C_AI      = "#e0bd6b"
C_ACT     = "#84e0a0"

PANEL_W = 430


class ChatOverlay:
    def __init__(self, on_send, on_close=None, on_decree=None, on_life=None, on_test=None,
                 on_event_send=None, on_set_mode=None, current_mode="realistic",
                 on_event_close=None):
        self.on_send = on_send
        self.on_close = on_close
        self.on_decree = on_decree
        self.on_life = on_life
        self.on_test = on_test
        self.on_event_send = on_event_send
        self.on_set_mode = on_set_mode
        self.current_mode = current_mode
        self.on_event_close = on_event_close
        self.busy = False
        self.ev_busy = False

        self.root = tk.Tk()
        self.root.title("HoI4 - Voices of History (AI Mod)")
        self.root.configure(bg=C_BG)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.sw = self.root.winfo_screenwidth()
        self.sh = self.root.winfo_screenheight()

        self._build_panel()
        self._build_tab()
        self._build_event_window()
        self._build_settings()
        self._style_scrollbars()

        # all'avvio: prima il selettore della MODALITA', poi la linguetta
        self.root.withdraw()
        self.tab.withdraw()
        self.settings_show()

    # ============ PANNELLO ============
    def _build_panel(self):
        r = self.root
        # --- barra titolo personalizzata (trascinabile) ---
        self.header = tk.Frame(r, bg=C_HEADER, height=40)
        self.header.pack(fill="x")
        self.header.bind("<Button-1>", self._start_move)
        self.header.bind("<B1-Motion>", self._on_move)

        self.title_lbl = tk.Label(self.header, text="VOICES OF HISTORY", bg=C_HEADER,
                                  fg=C_GOLD, font=("Georgia", 13, "bold"), padx=10)
        self.title_lbl.pack(side="left", pady=6)
        self.title_lbl.bind("<Button-1>", self._start_move)
        self.title_lbl.bind("<B1-Motion>", self._on_move)

        # --- riga azioni rapide (con CHIUDI/RIDUCI a destra, sempre visibili) ---
        bar = tk.Frame(r, bg=C_BG)
        bar.pack(fill="x", padx=8, pady=(6, 0))
        # Supreme Command / Leader's Life si aprono IN GIOCO (decisioni). Qui solo Settings.
        tk.Button(bar, text="Settings", command=self.settings_show, bg=C_BTN, fg=C_GOLD,
                  font=("Segoe UI", 8, "bold"), relief="flat",
                  activebackground=C_HEADER).pack(side="left", padx=2)
        # quadrato ROSSO con X = riduci il pannello alla linguetta IA
        tk.Button(bar, text="X", command=self.hide_panel, bg="#b03030", fg="#ffffff",
                  font=("Segoe UI", 10, "bold"), relief="flat", width=3,
                  activebackground="#d04040").pack(side="right", padx=(4, 0))
        tk.Button(bar, text="Exit", command=self._quit, bg=C_BTN, fg="#d88",
                  font=("Segoe UI", 8, "bold"), relief="flat",
                  activebackground=C_HEADER).pack(side="right", padx=2)

        self.status = tk.Label(r, text="", bg=C_BG, fg=C_MUTED,
                               font=("Consolas", 8), anchor="w", padx=10, justify="left",
                               wraplength=PANEL_W - 20)
        self.status.pack(fill="x", pady=(4, 0))

        # --- storico ---
        self.history = scrolledtext.ScrolledText(
            r, wrap="word", bg=C_HIST, fg=C_TEXT, font=("Segoe UI", 10),
            state="disabled", padx=10, pady=10, relief="flat",
            insertbackground=C_TEXT)
        self.history.pack(fill="both", expand=True, padx=8, pady=6)
        self.history.tag_config("player", foreground=C_PLAYER, font=("Segoe UI", 10, "bold"))
        self.history.tag_config("ai", foreground=C_AI, font=("Georgia", 10, "bold"))
        self.history.tag_config("aitext", foreground=C_TEXT, font=("Segoe UI", 10))
        self.history.tag_config("sys", foreground=C_MUTED, font=("Segoe UI", 8, "italic"))
        self.history.tag_config("act", foreground=C_ACT, font=("Consolas", 8))
        # avviso EVIDENZIATO (es. "scrivi qui il nome del capo di Stato"): oro, grassetto, leggibile
        self.history.tag_config("hl", foreground=C_GOLD, font=("Segoe UI", 11, "bold"))

        # --- input ---
        bottom = tk.Frame(r, bg=C_BG)
        bottom.pack(fill="x", padx=8, pady=8)
        self.entry = tk.Text(bottom, height=3, wrap="word", bg=C_INPUT, fg="#ffffff",
                             font=("Segoe UI", 10), insertbackground="#fff", relief="flat")
        self.entry.pack(side="left", fill="both", expand=True)
        # ENTER = invia il messaggio; SHIFT+ENTER = vai a capo (per messaggi su piu' righe).
        self.entry.bind("<Return>", self._send_event)
        self.entry.bind("<Shift-Return>", lambda e: None)   # newline normale (non invia)
        self.entry.bind("<Control-Return>", self._send_event)   # compatibilita'
        self.send_btn = tk.Button(bottom, text="SEND", command=self._send_click,
                                  bg=C_GOLD, fg="#1b1f24", font=("Georgia", 10, "bold"),
                                  width=8, relief="flat")
        self.send_btn.pack(side="right", fill="y", padx=(8, 0))

        self.root.bind("<Escape>", lambda e: self.hide_panel())
        self._append("sys", "System", "Ready. Open a chat (right-click a nation in game, "
                     "or use the buttons above).")

    # ============ LINGUETTA ============
    def _build_tab(self):
        self.tab = tk.Toplevel(self.root)
        self.tab.overrideredirect(True)
        self.tab.attributes("-topmost", True)
        self.tab.configure(bg=C_HEADER)
        tw, th = 34, 130
        self.tab.geometry(f"{tw}x{th}+{self.sw - tw}+{self.sh // 2 - th // 2}")
        b = tk.Button(self.tab, text="I\nA", command=self.show_panel, bg=C_HEADER,
                      fg=C_GOLD, font=("Georgia", 13, "bold"), relief="flat",
                      activebackground=C_BTN, bd=0)
        b.pack(fill="both", expand=True)

    # ============ show / hide ============
    def show_panel(self):
        self.tab.withdraw()
        self.root.deiconify()
        self.root.geometry(f"{PANEL_W}x{self.sh}+{self.sw - PANEL_W}+0")
        self.root.lift()
        self.root.attributes("-topmost", True)
        try:
            self.root.after(60, self.entry.focus_force)
        except Exception:
            pass

    def hide_panel(self):
        self.root.withdraw()
        self.tab.deiconify()
        self.tab.lift()
        self.tab.attributes("-topmost", True)

    def can_autohide(self):
        """True se il pannello e' aperto e il player NON sta scrivendo: usato per ridurlo da
        solo alla linguetta dopo che l'IA lancia un piano (cosi' HoI4 torna in primo piano e
        l'evento viene iniettato), senza interrompere chi sta digitando."""
        # NON chiudere se il player sta scrivendo qualcosa. (self.entry e' un tk.Text: get()
        # VUOLE gli indici.) hide_panel() a pannello gia' chiuso e' comunque un no-op innocuo.
        try:
            return not self.entry.get("1.0", "end").strip()
        except Exception:
            return True

    def _quit(self):
        if self.on_close:
            self.on_close()

    # ============ API per main.py ============
    def set_header(self, text):
        if len(text) > 36:
            text = text[:35] + "..."
        self.title_lbl.config(text=text)
    def set_status(self, text): self.status.config(text=text)

    def set_busy(self, busy):
        self.busy = busy
        self.send_btn.config(state="disabled" if busy else "normal",
                             text="..." if busy else "SEND")
        if not busy:
            self._clear_think(self.history)

    def clear_history(self):
        self.history.config(state="normal")
        self.history.delete("1.0", "end")
        self.history.config(state="disabled")

    def append_player(self, text): self._append("player", "You", text)
    def append_ai(self, name, text):
        self._clear_think(self.history)
        self._append_ai(name, text)
    def append_system(self, text): self._append("sys", "System", text)
    def append_action(self, text): self._append("act", "  ⚙", text)
    def append_highlight(self, text): self._append("hl", "  ►", text)

    def append_thinking(self):
        self._clear_think(self.history)
        self.history.config(state="normal")
        self.history.tag_config("think", foreground=C_GOLD, font=("Segoe UI", 9, "italic"))
        self.history.insert("end", "AI is thinking…\n\n", "think")
        self.history.see("end"); self.history.config(state="disabled")

    def _clear_think(self, w):
        try:
            w.config(state="normal")
            while True:
                r = w.tag_ranges("think")
                if not r:
                    break
                w.delete(r[0], r[1])
            w.config(state="disabled")
        except Exception:
            pass

    # ============ interni ============
    def _append(self, tag, who, text):
        self.history.config(state="normal")
        self.history.insert("end", f"{who}: ", tag)
        self.history.insert("end", f"{text}\n\n", tag if tag in ("sys", "act") else "aitext")
        self.history.see("end")
        self.history.config(state="disabled")

    def _append_ai(self, name, text):
        self.history.config(state="normal")
        self.history.insert("end", f"{name}: ", "ai")
        self.history.insert("end", f"{text}\n\n", "aitext")
        self.history.see("end")
        self.history.config(state="disabled")

    def _start_move(self, e):
        self._dx, self._dy = e.x, e.y

    def _on_move(self, e):
        self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def _decree(self):
        if self.on_decree: self.on_decree()

    def _life(self):
        if self.on_life: self.on_life()

    def _test(self):
        if self.on_test: self.on_test()

    def _send_click(self): self._do_send()

    def _send_event(self, _e):
        self._do_send(); return "break"

    def _do_send(self):
        if self.busy: return
        text = self.entry.get("1.0", "end").strip()
        if not text: return
        self.entry.delete("1.0", "end")
        self.append_player(text)
        self.append_thinking()
        self.on_send(text)

    # ============ FINESTRA EVENTI (centrale, stile pergamena HoI4) ============
    #  Separata dal pannello laterale. Mostra eventi interattivi a testo libero:
    #  il player legge e SCRIVE le sue azioni qui. Si apre al centro, piccola, e si
    #  chiude da sola quando la fase e' risolta (oppure manualmente con X).
    def _build_event_window(self):
        EV_PARCH = "#d8c7a0"; EV_DARK = "#3a2c19"; EV_BAR = "#6f5230"; EV_GOLD = "#f0e2bf"
        self._ev_open = False
        self.ev = tk.Toplevel(self.root)
        self.ev.overrideredirect(True)
        self.ev.attributes("-topmost", True)
        self.ev.configure(bg=EV_DARK)
        self.ev_w, self.ev_h = 560, 500

        outer = tk.Frame(self.ev, bg=EV_DARK, bd=0)
        outer.pack(fill="both", expand=True, padx=3, pady=3)

        # --- barra titolo (in alto) ---
        bar = tk.Frame(outer, bg=EV_BAR, height=34)
        bar.pack(side="top", fill="x")
        bar.bind("<Button-1>", self._ev_start_move)
        bar.bind("<B1-Motion>", self._ev_on_move)
        self.ev_title = tk.Label(bar, text="Event", bg=EV_BAR, fg=EV_GOLD,
                                 font=("Georgia", 12, "bold"), padx=10)
        self.ev_title.pack(side="left", pady=6)
        self.ev_title.bind("<Button-1>", self._ev_start_move)
        self.ev_title.bind("<B1-Motion>", self._ev_on_move)
        tk.Button(bar, text="X", command=self.event_close, bg="#8a3030", fg="#fff",
                  font=("Segoe UI", 9, "bold"), relief="flat", width=3,
                  activebackground="#a84040").pack(side="right", padx=4, pady=4)

        # --- AREA DI SCRITTURA (in basso, side=bottom: SEMPRE visibile) ---
        bottom = tk.Frame(outer, bg=EV_DARK)
        bottom.pack(side="bottom", fill="x", padx=6, pady=6)
        tk.Label(bottom, text="Write what you do, then press RESPOND (or Ctrl+Enter):",
                 bg=EV_DARK, fg=EV_GOLD, font=("Georgia", 9, "italic"),
                 anchor="w").pack(fill="x", pady=(0, 3))
        row = tk.Frame(bottom, bg=EV_DARK)
        row.pack(fill="x")
        self.ev_entry = tk.Text(row, height=3, wrap="word", bg="#efe4c8", fg=EV_DARK,
                                font=("Georgia", 11), insertbackground=EV_DARK, relief="flat",
                                highlightthickness=1, highlightbackground=EV_BAR)
        self.ev_entry.pack(side="left", fill="both", expand=True)
        self.ev_entry.bind("<Control-Return>", self._ev_send_event)
        self.ev_send_btn = tk.Button(row, text="RESPOND", command=self._ev_do_send,
                                     bg=EV_BAR, fg=EV_GOLD, font=("Georgia", 10, "bold"),
                                     width=10, relief="flat", activebackground="#8a6a40")
        self.ev_send_btn.pack(side="right", fill="y", padx=(8, 0))

        # --- testo dell'evento (in mezzo): tk.Text SENZA scrollbar bianca (rotella mouse) ---
        self.ev_hist = tk.Text(outer, wrap="word", bg=EV_PARCH, fg=EV_DARK,
                               font=("Georgia", 11), state="disabled", padx=14, pady=12,
                               relief="flat", insertbackground=EV_DARK, cursor="arrow",
                               highlightthickness=0, bd=0)
        self.ev_hist.pack(side="top", fill="both", expand=True, padx=6, pady=(6, 0))
        self.ev_hist.tag_config("evai", foreground=EV_DARK, font=("Georgia", 11))
        self.ev_hist.tag_config("evyou", foreground="#5a3a12", font=("Georgia", 11, "bold italic"))
        self.ev_hist.tag_config("evsys", foreground="#6a5a3a", font=("Georgia", 9, "italic"))
        self.ev_hist.bind("<MouseWheel>", lambda e: (self.ev_hist.yview_scroll(int(-1 * (e.delta / 120)), "units"), "break")[1])
        self.ev.withdraw()

    def _ev_center(self):
        x = (self.sw - self.ev_w) // 2
        y = (self.sh - self.ev_h) // 3
        self.ev.geometry(f"{self.ev_w}x{self.ev_h}+{x}+{y}")

    def event_is_open(self):
        return self._ev_open

    def event_show(self, title):
        self.ev_title.config(text=(title or "Event")[:46])
        self.ev_hist.config(state="normal"); self.ev_hist.delete("1.0", "end")
        self.ev_hist.config(state="disabled")
        self._ev_open = True
        self._ev_center()
        self.ev.deiconify(); self.ev.lift()
        self.ev.attributes("-topmost", True)
        def _focus():
            try:
                self.ev.focus_force()
                self.ev_entry.focus_force()
            except Exception:
                pass
        try:
            self.ev.after(100, _focus)
            self.ev.after(400, _focus)
        except Exception:
            pass

    def event_close(self):
        was_open = self._ev_open
        self._ev_open = False
        try:
            self.ev.withdraw()
        except Exception:
            pass
        if was_open and self.on_event_close:
            try:
                self.on_event_close()
            except Exception:
                pass

    def event_set_busy(self, busy):
        self.ev_busy = busy
        self.ev_send_btn.config(state="disabled" if busy else "normal",
                                text="..." if busy else "RESPOND")
        if not busy:
            self._clear_think(self.ev_hist)

    def event_append_thinking(self):
        self._clear_think(self.ev_hist)
        self.ev_hist.config(state="normal")
        self.ev_hist.tag_config("think", foreground="#6a5a3a", font=("Georgia", 10, "italic"))
        self.ev_hist.insert("end", "AI is thinking…\n\n", "think")
        self.ev_hist.see("end"); self.ev_hist.config(state="disabled")

    def event_append_ai(self, text):
        self._clear_think(self.ev_hist)
        self._ev_put("evai", text)

    def event_append_player(self, text):
        self._ev_put("evyou", "You: " + text)

    def event_append_sys(self, text):
        self._ev_put("evsys", text)

    def _ev_put(self, tag, text):
        self.ev_hist.config(state="normal")
        self.ev_hist.insert("end", text + "\n\n", tag)
        self.ev_hist.see("end")
        self.ev_hist.config(state="disabled")

    def _ev_start_move(self, e): self._evdx, self._evdy = e.x, e.y
    def _ev_on_move(self, e):
        self.ev.geometry(f"+{e.x_root - self._evdx}+{e.y_root - self._evdy}")

    def _ev_send_event(self, _e):
        self._ev_do_send(); return "break"

    def _ev_do_send(self):
        if self.ev_busy:
            return
        text = self.ev_entry.get("1.0", "end").strip()
        if not text:
            return
        self.ev_entry.delete("1.0", "end")
        self.event_append_player(text)
        self.event_append_thinking()
        if self.on_event_send:
            self.on_event_send(text)

    # ============ SELETTORE MODALITA' (Realism mode) ============
    def _build_settings(self):
        self.set_w, self.set_h = 500, 380
        self.settings = tk.Toplevel(self.root)
        self.settings.overrideredirect(True)
        self.settings.attributes("-topmost", True)
        self.settings.configure(bg=C_HEADER)
        f = tk.Frame(self.settings, bg=C_BG)
        f.pack(fill="both", expand=True, padx=3, pady=3)
        tk.Label(f, text="VOICES OF HISTORY", bg=C_BG, fg=C_GOLD,
                 font=("Georgia", 15, "bold")).pack(pady=(16, 2))
        tk.Label(f, text="Choose the realism mode (changeable anytime via Settings):",
                 bg=C_BG, fg=C_TEXT, font=("Segoe UI", 9), wraplength=460).pack(pady=(0, 10))
        modes = [
            ("Realistic", "realistic",
             "Strict historical plausibility. The AI rejects anachronisms and scenarios that could not credibly happen."),
            ("Plausible", "plausible",
             "Alternate history allowed if grounded and consistent. Bold or secret schemes are accepted if you build them up."),
            ("Sandbox", "sandbox",
             "Anything goes. The AI embraces any premise, even fantastical, and almost never refuses for realism."),
        ]
        for label, key, desc in modes:
            box = tk.Frame(f, bg=C_BTN)
            box.pack(fill="x", padx=16, pady=5)
            tk.Button(box, text=label, command=lambda k=key: self._set_mode_click(k),
                      bg=C_BTN, fg=C_GOLD, font=("Georgia", 12, "bold"), relief="flat",
                      activebackground=C_HEADER, anchor="w", padx=10).pack(fill="x")
            tk.Label(box, text=desc, bg=C_BTN, fg=C_MUTED, font=("Segoe UI", 8),
                     wraplength=440, justify="left", anchor="w", padx=12).pack(fill="x", pady=(0, 5))
        self.settings.withdraw()

    def settings_show(self):
        x = (self.sw - self.set_w) // 2
        y = (self.sh - self.set_h) // 3
        self.settings.geometry(f"{self.set_w}x{self.set_h}+{x}+{y}")
        self.root.withdraw(); self.tab.withdraw()
        self.settings.deiconify(); self.settings.lift()
        self.settings.attributes("-topmost", True)

    def settings_hide(self):
        try:
            self.settings.withdraw()
        except Exception:
            pass

    def _set_mode_click(self, mode):
        self.current_mode = mode
        if self.on_set_mode:
            self.on_set_mode(mode)
        self.settings_hide()
        self.tab.deiconify(); self.tab.lift()
        self.tab.attributes("-topmost", True)

    def _style_scrollbars(self):
        # scrollbar SCURE (niente barra bianca di Windows)
        try:
            self.history.vbar.config(bg=C_BTN, troughcolor=C_HIST, activebackground=C_GOLD,
                                     relief="flat", borderwidth=0, width=12, highlightthickness=0)
        except Exception:
            pass
        try:
            self.ev_hist.vbar.config(bg="#6f5230", troughcolor="#b7a577", activebackground="#8a6a40",
                                     relief="flat", borderwidth=0, width=12, highlightthickness=0)
        except Exception:
            pass

    # ============ DIALOGHI MODALI SEMPRE IN PRIMO PIANO ============
    #  simpledialog/messagebox finivano DIETRO HoI4 (il player doveva fare alt-tab per vederli).
    #  Questi sono -topmost, prendono il focus e compaiono SUBITO sopra il gioco (borderless).
    def _bring_front(self):
        try:
            self.root.deiconify(); self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.focus_force()
        except Exception:
            pass

    def ask_text(self, title, prompt):
        """Chiede una stringa al player con una finestra modale SEMPRE in primo piano. Il campo di
        scrittura e' ad ALTO CONTRASTO (sfondo bianco, testo nero, bordo evidente) cosi' si vede
        sempre cosa si scrive. Ritorna il testo, oppure None se annullata."""
        self._bring_front()
        win = tk.Toplevel(self.root)
        win.configure(bg=C_GOLD)                 # cornice dorata, ben visibile sul gioco
        win.attributes("-topmost", True)
        try:
            win.overrideredirect(True)
        except Exception:
            pass
        w, h = 560, 300
        x = (self.sw - w) // 2; y = (self.sh - h) // 3
        win.geometry(f"{w}x{h}+{x}+{y}")
        frm = tk.Frame(win, bg=C_BG); frm.pack(fill="both", expand=True, padx=3, pady=3)
        tk.Label(frm, text=title or "", bg=C_BG, fg=C_GOLD,
                 font=("Georgia", 15, "bold")).pack(pady=(18, 6))
        tk.Label(frm, text=prompt or "", bg=C_BG, fg=C_TEXT, font=("Segoe UI", 10),
                 wraplength=510, justify="center").pack(padx=20, pady=(0, 4))
        tk.Label(frm, text="Type the name in the white box below, then click OK (or press Enter):",
                 bg=C_BG, fg="#d8c79a", font=("Segoe UI", 9, "italic"),
                 wraplength=510, justify="center").pack(padx=20, pady=(0, 10))
        var = tk.StringVar()
        # CAMPO AD ALTO CONTRASTO: bianco con testo nero e bordo spesso -> sempre leggibile
        ent = tk.Entry(frm, textvariable=var, bg="#ffffff", fg="#000000",
                       insertbackground="#000000", font=("Segoe UI", 14),
                       width=32, relief="solid", borderwidth=2, justify="center")
        ent.pack(padx=20, pady=6, ipady=6)
        out = {"v": None}
        def _ok(*_):
            out["v"] = var.get(); win.destroy()
        def _cancel(*_):
            out["v"] = None; win.destroy()
        bar = tk.Frame(frm, bg=C_BG); bar.pack(pady=16)
        tk.Button(bar, text="OK", command=_ok, bg=C_GOLD, fg="#1a1206",
                  font=("Georgia", 12, "bold"), relief="flat", activebackground="#e9d9a8",
                  padx=26, pady=4).pack(side="left", padx=10)
        tk.Button(bar, text="Cancel", command=_cancel, bg=C_BTN, fg=C_TEXT,
                  font=("Segoe UI", 11), relief="flat", activebackground=C_HEADER,
                  padx=18, pady=4).pack(side="left", padx=10)
        ent.bind("<Return>", _ok); win.bind("<Return>", _ok); win.bind("<Escape>", _cancel)
        win.protocol("WM_DELETE_WINDOW", _cancel)
        try:
            win.transient(self.root); win.grab_set()
        except Exception:
            pass
        win.lift(); win.attributes("-topmost", True)
        ent.focus_force(); ent.icursor("end")
        self.root.wait_window(win)
        return out["v"]

    def ask_yes_no(self, title, prompt):
        """Domanda Si'/No con finestra modale SEMPRE in primo piano. Ritorna True/False."""
        self._bring_front()
        win = tk.Toplevel(self.root)
        win.configure(bg=C_HEADER)
        win.attributes("-topmost", True)
        try:
            win.overrideredirect(True)
        except Exception:
            pass
        w, h = 520, 300
        x = (self.sw - w) // 2; y = (self.sh - h) // 3
        win.geometry(f"{w}x{h}+{x}+{y}")
        frm = tk.Frame(win, bg=C_BG); frm.pack(fill="both", expand=True, padx=3, pady=3)
        tk.Label(frm, text=title or "", bg=C_BG, fg=C_GOLD,
                 font=("Georgia", 13, "bold")).pack(pady=(14, 4))
        tk.Label(frm, text=prompt or "", bg=C_BG, fg=C_TEXT, font=("Segoe UI", 9),
                 wraplength=480, justify="left").pack(padx=16, pady=(0, 8))
        out = {"v": False}
        def _yes(*_):
            out["v"] = True; win.destroy()
        def _no(*_):
            out["v"] = False; win.destroy()
        bar = tk.Frame(frm, bg=C_BG); bar.pack(pady=12)
        tk.Button(bar, text="Yes", command=_yes, bg=C_BTN, fg=C_GOLD,
                  font=("Georgia", 11, "bold"), relief="flat", activebackground=C_HEADER,
                  padx=20).pack(side="left", padx=8)
        tk.Button(bar, text="No", command=_no, bg=C_BTN, fg=C_MUTED,
                  font=("Segoe UI", 10), relief="flat", activebackground=C_HEADER,
                  padx=16).pack(side="left", padx=8)
        win.bind("<Escape>", _no)
        win.protocol("WM_DELETE_WINDOW", _no)
        try:
            win.transient(self.root); win.grab_set()
        except Exception:
            pass
        win.lift(); win.attributes("-topmost", True); win.focus_force()
        self.root.wait_window(win)
        return out["v"]

    def after(self, ms, fn): self.root.after(ms, fn)
    def run(self): self.root.mainloop()
