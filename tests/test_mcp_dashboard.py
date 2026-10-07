"""Il server MCP espone gli strumenti; la dashboard locale risponde come Apps Script."""

import asyncio
import json

import httpx

from elbandito import dashboard, mcp_server


def test_strumenti_mcp_registrati():
    nomi = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
    attesi = {"stato", "cerca_bandi", "scheda_bando", "registra_azione", "esegui_giro", "pagine_da_estrarre",
              "salva_schede", "aggiungi_da_link", "contesto_ricerca", "apri_dashboard", "crea_dati_esempio"}
    assert attesi <= nomi


def test_strumenti_mcp_sui_dati_esempio():
    assert "9" in mcp_server.crea_dati_esempio()
    s = mcp_server.stato()
    assert s["bandi_totali"] == 9 and s["configurazione"]["backend"] == "locale"
    primo = mcp_server.cerca_bandi(limite=1)[0]
    assert mcp_server.scheda_bando(primo["ID"])["Titolo"] == primo["Titolo"]
    assert mcp_server.pagine_da_estrarre()["pagine"] == []
    contesto = mcp_server.contesto_ricerca()
    assert contesto["filoni"] and "Artista" in contesto["profilo"]


def test_dashboard_locale(monkeypatch):
    mcp_server.crea_dati_esempio()
    monkeypatch.setattr(dashboard, "_server", None)
    url = dashboard.avvia(porta=8890)
    try:
        pagina = httpx.get(url)
        assert pagina.status_code == 200 and "ElBandito" in pagina.text
        r = httpx.post(url + "api/getBandi", json=[]).json()
        assert len(json.loads(r["ok"])["bandi"]) == 9
        r = httpx.post(url + "api/registraAzione", json=["B0001", "interessa", {}]).json()
        assert next(b for b in json.loads(r["ok"])["bandi"] if b["ID"] == "B0001")["Stato"] == "Da preparare"
        assert "errore" in httpx.post(url + "api/inesistente", json=[]).json()
    finally:
        dashboard._server.shutdown()
