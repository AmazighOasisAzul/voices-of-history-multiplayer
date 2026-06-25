"""
llm_client.py
Client per l'API locale di Player2 (formato compatibile OpenAI).
- Chat completions su POST {base_url}{chat_path}
- Heartbeat su GET {base_url}{health_path}  (richiesto da Player2 per il
  programma di revenue-share, 1 ping/minuto)
Funziona anche con OpenAI/altri backend OpenAI-compatibili cambiando base_url.
"""
import json
import re
import time
import requests


class LLMClient:
    def __init__(self, cfg):
        p2 = cfg["player2"]
        self.base_url = p2["base_url"].rstrip("/")
        self.chat_url = self.base_url + p2["chat_path"]
        self.health_url = self.base_url + p2["health_path"]
        self.game_key = p2.get("game_key", "hoi4-ai-diplomacy")
        self.model = p2.get("model", "") or None
        self.timeout = p2.get("timeout_sec", 120)
        self.temperature = p2.get("temperature", 0.8)
        self._last_heartbeat = 0.0

    # ---------- Heartbeat ----------
    def heartbeat(self):
        try:
            r = requests.get(
                self.health_url,
                headers={"player2-game-key": self.game_key},
                timeout=10,
            )
            return r.ok
        except Exception:
            return False

    def heartbeat_if_due(self, every=60):
        now = time.time()
        if now - self._last_heartbeat > every:
            self._last_heartbeat = now
            return self.heartbeat()
        return None

    # ---------- Chat ----------
    def chat(self, messages):
        """messages = lista di {role, content}. Ritorna il testo dell'assistente."""
        body = {
            "messages": messages,
            "temperature": self.temperature,
            "stream": False,
        }
        if self.model:
            body["model"] = self.model

        headers = {
            "Content-Type": "application/json",
            "player2-game-key": self.game_key,
        }
        r = requests.post(self.chat_url, json=body, headers=headers, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()
        return self._extract_text(data)

    @staticmethod
    def _extract_text(data):
        # Formato OpenAI standard
        try:
            return data["choices"][0]["message"]["content"]
        except Exception:
            pass
        # Alcune build di Player2 rispondono con campi diversi
        for k in ("content", "message", "text", "response"):
            if isinstance(data, dict) and k in data:
                v = data[k]
                return v if isinstance(v, str) else json.dumps(v)
        return json.dumps(data)

    # ---------- Parsing risposta JSON dell'IA ----------
    @staticmethod
    def parse_ai_json(text):
        """
        L'IA deve rispondere con un oggetto JSON:
        { "reason": "...", "message": "...", "actions": [ {"name":..,"args":{..}} ] }
        Qui estraiamo quel JSON anche se circondato da testo o code-fence.
        """
        if not text:
            return {"reason": "", "message": "", "actions": []}

        cleaned = text.strip()
        # rimuove eventuali ```json ... ```
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

        # prova diretta, poi con riparazione (valori bareword tipo  "days": px )
        for attempt in (cleaned, LLMClient._repair(cleaned)):
            try:
                return LLMClient._normalize(json.loads(attempt))
            except Exception:
                pass

        # cerca il primo blocco {...} bilanciato (diretto + riparato)
        start = cleaned.find("{")
        if start != -1:
            depth = 0
            for i in range(start, len(cleaned)):
                c = cleaned[i]
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        chunk = cleaned[start:i + 1]
                        for attempt in (chunk, LLMClient._repair(chunk)):
                            try:
                                return LLMClient._normalize(json.loads(attempt))
                            except Exception:
                                pass
                        break

        # fallback: nessun JSON valido -> mostra SOLO il testo umano (mai il JSON grezzo).
        # loose_text estrae il campo message/narration; se non c'e', ripulisce le scorie.
        return {"reason": "", "message": LLMClient.loose_text(text), "actions": []}

    @staticmethod
    def _repair(s):
        """Ripara errori JSON comuni dell'IA: mette tra virgolette i valori 'bareword'
        non quotati (es.  "days": px  ->  "days": "px" ), lasciando intatti numeri e
        true/false/null. Cosi' il parsing non fallisce e il middleware applica i suoi
        default (es. _num scarta 'px' e usa il valore predefinito)."""
        return re.sub(r':\s*(?!true\b|false\b|null\b)([A-Za-z_]\w*)\s*([,}\]])',
                      r': "\1"\2', s)

    @staticmethod
    def parse_obj(text):
        """Estrae il primo oggetto JSON come dict GREZZO (senza normalizzare).
        Robusto: prova diretto, poi riparato, poi il primo blocco {...} bilanciato
        (diretto + riparato). Se proprio nulla, ritorna {} (chi chiama usa un fallback)."""
        if not text:
            return {}
        cleaned = re.sub(r"^```(?:json)?", "", text.strip()).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
        for attempt in (cleaned, LLMClient._repair(cleaned)):
            try:
                o = json.loads(attempt)
                if isinstance(o, dict):
                    return o
            except Exception:
                pass
        start = cleaned.find("{")
        if start != -1:
            depth = 0
            for i in range(start, len(cleaned)):
                ch = cleaned[i]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        chunk = cleaned[start:i + 1]
                        for attempt in (chunk, LLMClient._repair(chunk)):
                            try:
                                o = json.loads(attempt)
                                if isinstance(o, dict):
                                    return o
                            except Exception:
                                pass
                        break
        return {}

    @staticmethod
    def loose_text(text):
        """Estrae il testo 'umano' da una risposta dell'IA che NON si e' riusciti a
        parsare come JSON: cosi' non perdiamo MAI cio' che l'IA ha scritto. Prova a tirare
        fuori il campo narration/message; se non c'e', pulisce code-fence e parentesi e
        ritorna il testo grezzo leggibile."""
        if not text:
            return ""
        # 1) prova a estrarre il campo umano (message/narration) anche se il resto del
        #    JSON e' corrotto (es. valori spazzatura altrove): questo e' il caso piu' comune.
        m = re.search(r'"(?:narration|message)"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.S)
        if m:
            try:
                return json.loads('"' + m.group(1) + '"')
            except Exception:
                return m.group(1).replace('\\"', '"').replace("\\n", " ").strip()
        # 2) niente campo testo: ripulisci code-fence ed eventuale etichetta iniziale ("X: {")
        s = re.sub(r"^```(?:json)?", "", text.strip()).strip()
        s = re.sub(r"```$", "", s).strip()
        s = re.sub(r'^[^\n{]{0,40}:\s*(?=\{)', "", s).strip()
        # se sembra un oggetto JSON fallito, togli graffe/chiavi tecniche per leggibilita'
        if s.startswith("{") or '"reason"' in s or '"actions"' in s:
            s = re.sub(r'[{}\[\]"]', "", s)
            s = re.sub(r'\b(narration|phase_done|story_done|actions|newspaper|'
                       r'next_in_days|reason|message|name|args|title|days|stages|'
                       r'summary|build|effects|outcome|target|ideology|value|desc)\s*:', "", s)
            s = re.sub(r",\s*", " ", s)
            s = re.sub(r"\s{2,}", " ", s).strip()
        # 3) guardia finale: se DOPO la pulizia il testo e' ancora chiaramente spazzatura
        #    JSON (resta poco di leggibile), mostra un messaggio pulito invece delle scorie.
        if not s or sum(c.isalpha() for c in s) < 12:
            return "(The AI response was garbled — please send your message again.)"
        return s.strip()

    @staticmethod
    def _normalize(obj):
        if not isinstance(obj, dict):
            return {"reason": "", "message": str(obj), "actions": []}
        actions = obj.get("actions") or []
        # tollera "command" singolo in stile ChatClef
        if not actions and obj.get("command"):
            actions = [{"name": "raw_console", "args": {"command": obj["command"]}}]
        norm = []
        for a in actions:
            if isinstance(a, dict) and a.get("name"):
                norm.append({"name": a["name"], "args": a.get("args", {}) or {}})
        return {
            "reason": obj.get("reason", ""),
            "message": obj.get("message", ""),
            "actions": norm,
        }
