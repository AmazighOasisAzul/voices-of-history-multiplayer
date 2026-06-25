"""
injector.py  -  esecuzione comandi in HoI4

Lezioni imparate:
 * la console di HoI4 NON accetta l'incolla (Ctrl+V): bisogna DIGITARE i tasti.
 * il tasto che apre la console (su tastiera IT spesso il backslash) "lascia"
   un carattere nella riga: lo ripuliamo con dei Backspace prima di scrivere.
 * digitiamo con pydirectinput (SCANCODE = indipendente dal layout) la stringa
   semplice "run aidiplo.txt"; i comandi veri (anche con { } =) stanno nel file.
 * il focus sul gioco si ottiene con SetForegroundWindow (SENZA AttachThreadInput,
   che congelava la UI): funziona perche' al momento dell'invio la finestra in
   primo piano e' il nostro overlay, e un processo in foreground PUO' cedere il
   focus a un altro.
"""
import os
import time

try:
    import pydirectinput as pdi
    pdi.PAUSE = 0.0
    pdi.FAILSAFE = False
except Exception:
    pdi = None

try:
    import pyautogui as pag
    pag.FAILSAFE = False
except Exception:
    pag = None

try:
    import pygetwindow as gw
except Exception:
    gw = None

# ctypes Win32 (focus + rilevamento finestra)
try:
    import ctypes
    from ctypes import wintypes
    _u32 = ctypes.windll.user32
    _u32.FindWindowW.restype = wintypes.HWND
    _u32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    _u32.GetForegroundWindow.restype = wintypes.HWND
    _u32.SetForegroundWindow.argtypes = [wintypes.HWND]
    _u32.SetForegroundWindow.restype = wintypes.BOOL
    _u32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _u32.BringWindowToTop.argtypes = [wintypes.HWND]
    _u32.BlockInput.argtypes = [wintypes.BOOL]
    _u32.BlockInput.restype = wintypes.BOOL
    _u32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    _u32.GetAsyncKeyState.restype = ctypes.c_short
    _u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _u32.GetWindowThreadProcessId.restype = wintypes.DWORD
except Exception:
    _u32 = None


KEY_ALIASES = {"grave": "`", "tilde": "~", "backtick": "`", "section": "§",
               "backslash": "\\", "less": "<"}


class Injector:
    def __init__(self, cfg, logger=print):
        inj = cfg["injection"]
        self.key = KEY_ALIASES.get(inj.get("console_key", "grave"), inj.get("console_key", "`"))
        self.window_title = inj.get("window_title", "Hearts of Iron IV")
        self.pre = inj.get("pre_command_delay", 0.40)
        self.post = inj.get("post_command_delay", 0.15)
        self.dry_run = inj.get("dry_run", False)
        self.loc_path = os.path.expandvars(cfg["paths"]["mod_localisation"])
        self.log = logger
        self._hwnd = None

        gl = os.path.expandvars(cfg["paths"]["game_log"])
        userdir = os.path.dirname(os.path.dirname(gl)) if gl else "."
        self.run_name = "aidiplo.txt"
        self.run_file = os.path.join(userdir, self.run_name)

    # ---------------- diagnostica ----------------
    def available(self):
        return (pdi is not None) or (pag is not None)

    def status_text(self):
        libs = ["pydirectinput" if pdi else "pydirectinput MISSING",
                "pyautogui" if pag else "pyautogui MISSING"]
        if not self.available():
            return ("WARNING: input libraries missing: relaunch "
                    "START_MIDDLEWARE.bat. [" + ", ".join(libs) + "]")
        return f"Ready. Command file: {self.run_file}  [" + ", ".join(libs) + "]"

    def manual_hint(self):
        return f"run {self.run_name}"

    # ---------------- finestra ----------------
    def _get_hwnd(self):
        if _u32 is not None:
            h = _u32.FindWindowW(None, self.window_title)
            if h:
                self._hwnd = h
                return h
        if gw is not None:
            try:
                wins = gw.getWindowsWithTitle(self.window_title)
                if wins:
                    self._hwnd = wins[0]._hWnd
                    return self._hwnd
            except Exception:
                pass
        return None

    def is_game_foreground(self):
        if _u32 is None:
            return False
        h = self._get_hwnd()
        return bool(h) and _u32.GetForegroundWindow() == h

    def can_inject_now(self):
        """Digitiamo SOLO quando HoI4 e' la finestra ATTIVA. Se davanti c'e' l'overlay del
        middleware (la chat) o una terza app (browser...), ASPETTIAMO. Cosi' 'run aidiplo.txt'
        non viene MAI digitato per sbaglio nella chat del middleware: l'evento parte appena
        torni su HoI4 (l'iniezione non si perde, attende soltanto)."""
        if _u32 is None:
            return True
        try:
            h = self._get_hwnd()
            return bool(h) and _u32.GetForegroundWindow() == h
        except Exception:
            return False

    def _focus_game(self):
        h = self._get_hwnd()
        if not h:
            self.log("[injector] finestra HoI4 non trovata")
            return False
        if _u32 is not None:
            try:
                _u32.ShowWindow(h, 9)          # SW_RESTORE
                _u32.BringWindowToTop(h)
                _u32.SetForegroundWindow(h)
            except Exception as e:
                self.log(f"[injector] focus fallito: {e}")
        elif gw is not None:
            try:
                gw.getWindowsWithTitle(self.window_title)[0].activate()
            except Exception:
                pass
        time.sleep(0.35)
        ok = self.is_game_foreground()
        self.log("[injector] HoI4 in primo piano: " + ("si" if ok else "NO"))
        return ok

    # ---------------- tasti ----------------
    def _press(self, key):
        if pdi is not None:
            pdi.press(key)
        elif pag is not None:
            pag.press(key)

    def _type(self, text):
        # SCANCODE (layout-indipendente) per lettere/spazio/punto di "run aidiplo.txt"
        if pdi is not None:
            pdi.typewrite(text, interval=0.03)
        elif pag is not None:
            pag.typewrite(text, interval=0.03)

    # ---------------- scrittura del run-file ----------------
    @staticmethod
    def _fix(c):
        c = c.strip()
        if c.startswith("effect "):
            c = "eval_" + c
        return c

    def write_run_file(self, commands):
        cmds = [self._fix(c) for c in commands if c and c.strip()]
        if not cmds:
            return 0
        try:
            os.makedirs(os.path.dirname(self.run_file), exist_ok=True)
            with open(self.run_file, "w", encoding="utf-8") as f:
                f.write("\n".join(cmds) + "\n")
            self.log(f"[run-file] {len(cmds)} comandi -> {self.run_file}")
            return len(cmds)
        except Exception as e:
            self.log(f"[injector] errore scrittura run-file: {e}")
            return 0

    def _block_input(self, on):
        """Blocca (o sblocca) mouse/tastiera FISICI dell'utente per la frazione di
        secondo in cui digitiamo: cosi' l'utente non puo' cliccare o cambiare focus a
        meta' comando e rovinare l'iniezione. Il nostro input sintetico passa lo stesso.
        Best-effort: se non e' permesso (privilegi), prosegue senza bloccare."""
        if _u32 is None:
            return
        try:
            _u32.BlockInput(True if on else False)
        except Exception:
            pass

    def _anything_pressed(self):
        """True se l'utente sta tenendo premuto un tasto o un pulsante del mouse ADESSO."""
        if _u32 is None:
            return False
        try:
            # mouse: L=1 R=2 M=4 X1=5 X2=6 ; tastiera: scansione vk 8..254
            for vk in (1, 2, 4, 5, 6):
                if _u32.GetAsyncKeyState(vk) & 0x8000:
                    return True
            for vk in range(8, 255):
                if _u32.GetAsyncKeyState(vk) & 0x8000:
                    return True
        except Exception:
            return False
        return False

    def _wait_for_input_idle(self, timeout=3.0):
        """Aspetta che l'utente NON stia premendo nulla prima di digitare: cosi' un tasto
        o un click in corso non rovina/blocca l'iniezione del comando. Se dopo 'timeout'
        l'utente preme ancora di continuo, procede comunque (caso limite)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self._anything_pressed():
                return True
            time.sleep(0.05)
        return False

    # ---------------- esecuzione automatica ----------------
    def execute(self):
        """Porta HoI4 in primo piano e digita 'run <file>' nella console.
        Digita SOLO se HoI4 e' davvero in primo piano (cosi' non scrive mai per
        sbaglio nell'overlay). Ritorna True se ha digitato, False altrimenti.
        Prima di digitare ASPETTA che l'utente non stia premendo tasti/mouse, poi blocca
        l'input fisico: cosi' l'iniezione non si rompe mai per un tasto premuto."""
        if self.dry_run or not self.available():
            self.log(f"[DRY/NO-LIB] run {self.run_name}")
            return False
        if not self._focus_game():
            self.log(f"[injector] HoI4 non in primo piano: ritento / fallback manuale  run {self.run_name}")
            return False
        self._wait_for_input_idle()            # niente digitazione mentre l'utente preme
        self._block_input(True)
        try:
            time.sleep(0.12)
            self._press(self.key)              # apre la console (puo' lasciare un char)
            time.sleep(self.pre)
            for _ in range(6):                 # ripulisce eventuali caratteri spuri
                self._press("backspace")
            time.sleep(0.05)
            self._type(f"run {self.run_name}")
            time.sleep(self.post)
            self._press("enter")
            time.sleep(self.post)
            self._press(self.key)              # chiude la console
        finally:
            self._block_input(False)
        self.log(f"[console] run {self.run_name}")
        return True

    # ---------------- localizzazione dinamica (per gli eventi) ----------------
    def _set_loc_keys(self, mapping):
        path = self.loc_path
        if not os.path.isfile(path):
            self.log(f"[injector] file loc non trovato: {path}")
            return
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                lines = f.readlines()
            out, done = [], set()
            for line in lines:
                rep = False
                for key, val in mapping.items():
                    if line.strip().startswith(f"{key}:"):
                        safe = str(val).replace('"', "'").replace("\n", " ")
                        out.append(f' {key}:0 "{safe}"\n'); done.add(key); rep = True
                        break
                if not rep:
                    out.append(line)
            for key, val in mapping.items():
                if key not in done:
                    safe = str(val).replace('"', "'").replace("\n", " ")
                    out.append(f' {key}:0 "{safe}"\n')
            with open(path, "w", encoding="utf-8-sig") as f:
                f.writelines(out)
            # FIRMA DEL CONTENUTO: i comandi degli eventi sono sempre uguali
            # ("reload loc"+"event aidiplo.X"); il testo vero sta QUI. Esponiamo una firma
            # del contenuto cosi' la deduplica del dispatch distingue eventi DIVERSI con gli
            # stessi comandi (e non sopprime per sbaglio un evento legittimo del piano).
            self._loc_sig = repr(sorted((str(k), str(v)) for k, v in mapping.items()))
        except Exception as e:
            self.log(f"[injector] errore loc: {e}")

    def loc_sig(self):
        """Firma dell'ultimo contenuto di localizzazione scritto (per la deduplica)."""
        return getattr(self, "_loc_sig", "")

    def prepare_dynamic_event(self, title, desc, option_a="So be it.", option_b=""):
        self._set_loc_keys({
            "aidiplo.1.t": title, "aidiplo.1.d": desc,
            "aidiplo.1.a": option_a or "So be it.",
            "aidiplo.1.b": option_b or "Noted.",
        })
        return ["reload loc", "event aidiplo.1"]

    def prepare_act_event(self, act, actor, target, title, narration):
        """Riempie l'evento aidiplo.2 con titolo + narrazione (scritta dall'IA) e
        prepara i comandi: salva il bersaglio, imposta l'azione, lancia l'evento."""
        self._set_loc_keys({
            "aidiplo.2.t": title or "Supreme Command Decision",
            "aidiplo.2.d": narration or "The games are over: it is time to act.",
        })
        return ["reload loc",
                f"eval_effect {target} = {{ save_global_event_target_as = aidiplo_tgt }}",
                f"eval_effect {actor} = {{ set_variable = {{ aidiplo_act = {act} }} }}",
                f"event aidiplo.2 {actor}"]

    def prepare_decision_event(self, title, desc, opt_a, opt_b, opt_c=None):
        """Evento DECISIONE intermedia (aidiplo.46): 2 opzioni preimpostate + una 3a
        ('scrivi tu') che apre il canale evento del middleware. Le etichette delle opzioni
        e il titolo vengono ACCORCIATI per non sforare i bottoni/lo spazio dell'evento."""
        def _cap(s, n):
            s = (s or "").strip()
            return s if len(s) <= n else s[:n - 1].rstrip() + "…"
        self._set_loc_keys({
            "aidiplo.46.t": _cap(title, 48) or "Plan Crossroads",
            "aidiplo.46.d": desc or "The plan requires a decision.",
            "aidiplo.46.a": _cap(opt_a, 42) or "Option A",
            "aidiplo.46.b": _cap(opt_b, 42) or "Option B",
            "aidiplo.46.c": opt_c or "Take personal command (write your own move)",
        })
        return ["reload loc", "event aidiplo.46"]

    def prepare_reject(self, reason):
        self._set_loc_keys({
            "aidiplo.10.d": reason or "Our experts report that this is impossible.",
        })
        return ["reload loc", "event aidiplo.10"]

    def prepare_rename(self, name, target="ROOT"):
        """Cambia il NOME visualizzato di una nazione al volo: riscrive le chiavi loc
        della tag cosmetica AIDIPLO_DYN (la bandiera AIDIPLO_DYN.tga e' gia' nella mod),
        ricarica la localizzazione e applica set_cosmetic_tag. Cosi' lo Stato prende il
        nome ESATTO deciso dal giocatore (es. 'Stato Teocratico di Palestina')."""
        nm = str(name).replace('"', "'").replace("\n", " ").strip()
        self._set_loc_keys({
            "AIDIPLO_DYN": nm,
            "AIDIPLO_DYN_DEF": nm,
            "AIDIPLO_DYN_ADJ": nm,
        })
        return ["reload loc",
                f"eval_effect {target} = {{ set_cosmetic_tag = AIDIPLO_DYN }}"]

    def prepare_set_leader(self, name, ideo_num, target="ROOT", radical=False):
        """Installa il NUOVO capo di Stato. PRIMA scrive il nome scelto nella chiave di loc
        AIDIPLO_LEADER e ricarica la localizzazione (reload loc); POI lancia l'EVENTO aidiplo.60.
        Dentro l'evento, set_politics porta al governo il partito dell'ideologia scelta (il capo
        diventa il leader di quel partito, UNO solo) e set_country_leader_name = "AIDIPLO_LEADER"
        lo rinomina col nome scelto. La rinomina sta DENTRO l'evento (compilato al caricamento):
        da console set_country_leader_name da' "errore di compilazione". Niente create_country_leader
        (aggiungerebbe un leader concorrente e il gioco potrebbe promuoverne un altro)."""
        try:
            n = int(ideo_num)
        except Exception:
            n = 4
        if n not in (1, 2, 3, 4):
            n = 4
        nm = str(name).replace('"', "'").replace("\n", " ").strip() or "New Leader"
        self._set_loc_keys({"AIDIPLO_LEADER": nm})
        # UN SOLO invio ORDINATO (come i titoli degli eventi dinamici, che funzionano): scrive il
        # nome nella chiave loc, RICARICA la loc, poi lancia aidiplo.60 che fa set_politics +
        # recruit_character + promote_character del nostro personaggio. promote_character = priorita'
        # assoluta: il nostro capo (col nome scelto) scavalca i leader del gioco, anche su ideologie
        # diverse. Il nome si risolve perche' reload loc gira PRIMA dell'evento, nello STESSO run.
        # aidiplo_radical=1 solo se cambia davvero l'ideologia (offerta reset focus via aidiplo.62).
        return ["reload loc",
                f"eval_effect {target} = {{ set_variable = {{ aidiplo_newideo = {n} }} }}",
                f"eval_effect {target} = {{ set_variable = {{ aidiplo_radical = {1 if radical else 0} }} }}",
                f"event aidiplo.60 {target}",
                "retire_country_leader",
                "retire_country_leader",
                "retire_country_leader",
                "retire_country_leader",
                f"event aidiplo.63 {target}"]
