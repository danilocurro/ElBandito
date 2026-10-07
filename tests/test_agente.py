"""Senza chiavi API: le pagine vanno in coda e le schede arrivano da Claude Code."""

from conftest import leggi, rete_finta

from elbandito import pipeline
from elbandito.archivio import Archivio
from elbandito.config import Ambiente
from elbandito.foglio import apri

FEED = "https://rivista.example/feed/"
BANDO = "https://rivista.example/2026/10/premio-portici/"


def giro_senza_chiavi(monkeypatch):
    amb = Ambiente()
    foglio = apri(amb)
    foglio.prepara(con_seed=True)
    foglio._scrivi("FONTI", [{"ID": "F02", "Nome": "Rivista", "URL": FEED, "Connettore": "rss",
                              "Parametri": "filtro=premio", "Frequenza": "giornaliera", "Attiva": "sì"}])
    rete = rete_finta({FEED: (200, "application/rss+xml", leggi("feed.xml")),
                       BANDO: (200, "text/html", leggi("bando.html"))})
    monkeypatch.setattr(pipeline, "Rete", lambda: rete)
    monkeypatch.setattr(pipeline, "geocodifica", lambda *a: None)
    return amb, foglio, pipeline.Giro("giornaliero", amb, foglio).esegui()


def test_senza_chiavi_la_pagina_va_in_coda(monkeypatch):
    amb, foglio, res = giro_senza_chiavi(monkeypatch)
    assert res.in_coda == 1 and res.nuovi == 0 and not res.errori
    assert Archivio(amb.cartella_dati / "archivio.sqlite").in_coda()[0]["url"] == BANDO
    assert foglio.leggi("LOG")[0]["In coda"] == "1"


def test_schede_da_claude_code_passano_le_verifiche(monkeypatch, scheda_mare):
    amb, foglio, _ = giro_senza_chiavi(monkeypatch)
    buona = scheda_mare.model_dump()
    inventata = dict(buona, titolo="Altro premio", ente="Altro ente", scadenza="1 marzo 2027",
                     scadenza_citazione="Scadenza: 1 marzo 2027")  # frase che non esiste nel testo
    rotta = {"titolo": "senza tipo"}
    r = pipeline.salva_estratte(BANDO, [buona, inventata, rotta], amb)
    assert r["nuovi"] == 2 and len(r["errori"]) == 1
    conferme = {b["Titolo"]: b["Scadenza confermata"] for b in r["bandi"]}
    assert conferme == {"Premio Portici per la fotografia 2027": "sicura", "Altro premio": "da verificare"}
    assert Archivio(amb.cartella_dati / "archivio.sqlite").quanti_in_coda() == 0


def test_lista_vuota_svuota_la_coda(monkeypatch):
    amb, _, _ = giro_senza_chiavi(monkeypatch)
    r = pipeline.salva_estratte(BANDO, [], amb)
    assert r["nuovi"] == 0
    assert Archivio(amb.cartella_dati / "archivio.sqlite").quanti_in_coda() == 0


def test_ricerca_agente_non_chiama_api(monkeypatch):
    amb, foglio, _ = giro_senza_chiavi(monkeypatch)
    res = pipeline.Giro("settimanale", amb, foglio).esegui()
    assert any("Claude Code" in n for n in res.note)
