"""Strumenti comuni ai test: data fissa, rete finta, scheda di esempio."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import pytest

PAGINE = Path(__file__).parent / "pagine"
OGGI = date(2026, 10, 7)


@pytest.fixture(autouse=True)
def isolamento(monkeypatch, tmp_path):
    """Ogni test usa una cartella dati vuota, il seed anonimo e nessuna chiave API."""
    import elbandito.foglio as foglio

    monkeypatch.setenv("ELBANDITO_DATI", str(tmp_path / "dati"))
    monkeypatch.setenv("ELBANDITO_BACKEND", "locale")
    for k in ("ELBANDITO_SHEET_ID", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "ELBANDITO_PLUGIN"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(foglio, "CARTELLA_PERSONALE", tmp_path / "nessun-dato-personale")


@pytest.fixture(autouse=True)
def data_fissa(monkeypatch):
    """Tutti i test girano al 7/10/2026."""
    import elbandito.config as config

    monkeypatch.setattr(config, "oggi", lambda: OGGI)
    for modulo in ("elbandito.estrazione", "elbandito.punteggio", "elbandito.pipeline", "elbandito.archivio",
                   "elbandito.connettori", "elbandito.ricerca_ai", "elbandito.servizi", "elbandito.demo",
                   "elbandito.mcp_server"):
        mod = __import__(modulo, fromlist=["oggi"])
        if hasattr(mod, "oggi"):
            monkeypatch.setattr(mod, "oggi", lambda: OGGI)


def rete_finta(risposte: dict[str, tuple[int, str, str]]):
    """Rete con risposte preparate: {url: (stato, content-type, corpo)}. robots.txt assente."""
    from elbandito.rete import Rete

    def gestore(req: httpx.Request) -> httpx.Response:
        url = str(req.url).split("?")[0]
        if url.endswith("/robots.txt"):
            return httpx.Response(404)
        if url not in risposte:
            return httpx.Response(404, text="non trovato")
        stato, tipo, corpo = risposte[url]
        return httpx.Response(stato, headers={"content-type": tipo}, text=corpo)

    rete = Rete(pausa=(0, 0))
    rete.client = httpx.Client(transport=httpx.MockTransport(gestore), follow_redirects=True)
    return rete


def leggi(nome: str) -> str:
    return (PAGINE / nome).read_text(encoding="utf-8")


@pytest.fixture
def scheda_mare():
    """La scheda che un LLM onesto estrarrebbe da tests/pagine/bando.html."""
    from elbandito.modelli import SchedaEstratta

    return SchedaEstratta(
        titolo="Premio Portici per la fotografia 2027",
        ente="Fondazione Portici",
        tipo="premio",
        disciplina="fotografia",
        temi=["territorio", "memoria", "paesaggio"],
        paese="Italia", regione="Emilia-Romagna", citta="Bologna",
        scadenza="15 gennaio 2027",
        scadenza_citazione="Le candidature vanno inviate entro il 15 gennaio 2027 alle ore 23:59 tramite il modulo online.",
        fuso_scadenza="23:59",
        quota_iscrizione_eur=0,
        quota_citazione="La partecipazione è gratuita.",
        valore="3.000 € + residenza sull'Appennino + mostra personale",
        valore_eur=3000, copre_viaggio=True, copre_alloggio=True, include_mostra=True,
        eleggibilita="Maggiorenni di qualsiasi nazionalità",
        eleggibilita_citazione="Possono partecipare fotografi e fotografe maggiorenni di qualsiasi nazionalità, senza limiti di età.",
        materiali_richiesti=["portfolio 15 immagini", "statement", "CV"],
        lingue_candidatura=["italiano", "inglese"],
        ricorrente=True, edizione=3,
    )
