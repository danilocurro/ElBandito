"""Dashboard locale: la stessa interfaccia della web app Apps Script, servita in locale.

Index.html chiama `chiama('nomeFunzione', …)`: dentro Apps Script va a
google.script.run, qui va a POST /api/<nomeFunzione>. Così c'è una sola
interfaccia per due backend (foglio Google o CSV locali).
Ascolta solo su 127.0.0.1.
"""

from __future__ import annotations

import json
import logging
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import servizi
from .config import RADICE, Ambiente
from .foglio import apri

log = logging.getLogger(__name__)
PAGINA = RADICE / "apps-script" / "Index.html"

_server: ThreadingHTTPServer | None = None


def _in_sottofondo(funzione, *args) -> None:
    def esegui():
        try:
            funzione(*args)
        except Exception:
            log.exception("Operazione in sottofondo fallita")

    threading.Thread(target=esegui, daemon=True).start()


def _api(amb: Ambiente, nome: str, args: list):
    foglio = apri(amb)
    tutto = lambda: json.dumps(servizi.dati(foglio), ensure_ascii=False)  # noqa: E731

    if nome == "getBandi":
        return tutto()
    if nome == "registraAzione":
        extra = args[2] if len(args) > 2 and args[2] else {}
        servizi.registra_azione(foglio, args[0], args[1], extra.get("dataEsito", ""), extra.get("nota", ""))
        return tutto()
    if nome == "salvaChecklist":
        servizi.salva_checklist(foglio, args[0], args[1], args[2] if len(args) > 2 else None)
        return tutto()
    if nome == "salvaFeedback":
        servizi.salva_feedback(foglio, args[0], args[1])
        return tutto()
    if nome == "salvaNote":
        servizi.salva_note(foglio, args[0], args[1])
        return tutto()
    if nome == "confermaScadenza":
        servizi.conferma_scadenza(foglio, args[0], args[1] if len(args) > 1 else "")
        return tutto()
    if nome == "aggiornaFonte":
        servizi.aggiorna_fonte(foglio, args[0], args[1])
        return tutto()
    if nome == "aggiungiFonte":
        f = args[0]
        servizi.aggiungi_fonte(foglio, f.get("Nome", ""), f.get("URL", ""), f.get("Connettore", "watch"),
                               f.get("Parametri", ""))
        return tutto()
    if nome == "salvaProfilo":
        servizi.salva_profilo(foglio, args[0], args[1])
        return tutto()
    if nome == "esportaICS":
        return servizi.esporta_ics(foglio)
    if nome == "aggiungiDaLink":
        from .pipeline import aggiungi_da_link

        _in_sottofondo(aggiungi_da_link, args[0], amb)
        return ("Avviato. Se non hai chiavi API la pagina va in coda: in Claude Code chiedi "
                "«estrai i bandi in coda». Ricarica fra poco.")
    if nome == "cercaAFondo":
        if amb.anthropic_key:
            from .pipeline import approfondisci

            _in_sottofondo(approfondisci, args[0], amb)
            return "Indagine avviata: il risultato compare nella scheda fra un paio di minuti."
        return f"In locale chiedilo a Claude Code: «approfondisci il bando {args[0]}»."
    if nome == "avviaCollettore":
        comando = args[0]
        if comando == "ricalcola":
            from .pipeline import ricalcola

            return f"Ricalcolati {ricalcola(amb)} bandi. Ricarica la pagina."
        if comando in ("giornaliero", "settimanale"):
            from .pipeline import Giro

            _in_sottofondo(lambda: Giro(comando, amb).esegui())
            return "Giro avviato in sottofondo: ricarica fra qualche minuto."
        raise ValueError(f"Comando non disponibile in locale: {comando}")
    if nome == "assistente":
        return json.dumps({"risposta": "In locale l'assistente è Claude Code: apri Claude Code nella cartella di "
                                       "ElBandito (o con il plugin) e chiedi, per esempio, «quali residenze estive "
                                       "con alloggio pagato ho?» oppure «scrivimi una bozza di statement per B0003».",
                           "azioni": []}, ensure_ascii=False)
    raise ValueError(f"Funzione sconosciuta: {nome}")


def _gestore(amb: Ambiente):
    class Gestore(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # niente rumore su stderr (lo stdout serve a MCP)
            log.debug(fmt, *args)

        def _rispondi(self, codice: int, corpo: bytes, tipo: str) -> None:
            self.send_response(codice)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def do_GET(self):
            if self.path.split("?")[0] in ("/", "/index.html", "/Index.html"):
                self._rispondi(200, PAGINA.read_bytes(), "text/html; charset=utf-8")
            else:
                self._rispondi(404, b"non trovato", "text/plain")

        def do_POST(self):
            if not self.path.startswith("/api/"):
                return self._rispondi(404, b"non trovato", "text/plain")
            nome = self.path[len("/api/"):]
            try:
                lunghezza = int(self.headers.get("Content-Length", 0))
                args = json.loads(self.rfile.read(lunghezza) or b"[]")
                corpo = json.dumps({"ok": _api(amb, nome, args)}, ensure_ascii=False)
                self._rispondi(200, corpo.encode(), "application/json")
            except Exception as e:
                log.exception("API %s", nome)
                self._rispondi(500, json.dumps({"errore": str(e)}, ensure_ascii=False).encode(), "application/json")

    return Gestore


def avvia(amb: Ambiente | None = None, porta: int = 8787, apri_browser: bool = False, blocca: bool = False) -> str:
    """Avvia la dashboard (una sola volta per processo) e restituisce l'indirizzo."""
    global _server
    amb = amb or Ambiente()
    if _server is None:
        for p in range(porta, porta + 20):
            try:
                _server = ThreadingHTTPServer(("127.0.0.1", p), _gestore(amb))
                break
            except OSError:
                continue
        else:
            raise RuntimeError("Nessuna porta libera per la dashboard")
        if not blocca:
            threading.Thread(target=_server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{_server.server_address[1]}/"
    if apri_browser:
        webbrowser.open(url)
    if blocca:
        print(f"ElBandito: dashboard su {url} (Ctrl+C per chiudere)")
        try:
            _server.serve_forever()
        except KeyboardInterrupt:
            pass
    return url
