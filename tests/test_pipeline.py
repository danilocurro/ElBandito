"""Un giro completo sul foglio locale (CSV), con rete e LLM finti."""

from conftest import leggi, rete_finta

from elbandito import pipeline
from elbandito.config import Ambiente
from elbandito.foglio import FoglioLocale
from elbandito.modelli import Estrazione

FEED = "https://rivista.example/feed/"
BANDO = "https://rivista.example/2026/10/premio-portici/"
UFFICIALE = "https://portici.example/premio"


def prepara(tmp_path, monkeypatch, scheda, fonti):
    amb = Ambiente(backend="locale", cartella_dati=tmp_path)
    foglio = FoglioLocale(tmp_path)
    foglio.prepara(con_seed=True)
    foglio._scrivi("FONTI", fonti)
    rete = rete_finta({
        FEED: (200, "application/rss+xml", leggi("feed.xml")),
        BANDO: (200, "text/html", leggi("bando.html")),
        UFFICIALE: (200, "text/html", leggi("bando.html")),
    })
    monkeypatch.setattr(pipeline, "Rete", lambda: rete)
    monkeypatch.setattr(pipeline.Estrattore, "_llm", lambda self, prompt: Estrazione(bandi=[scheda.model_copy(deep=True)]))
    monkeypatch.setattr(pipeline, "geocodifica", lambda *a: (38.19, 15.55))
    return amb, foglio


FONTE_RSS = {"ID": "F02", "Nome": "Rivista", "URL": FEED, "Connettore": "rss", "Parametri": "filtro=premio",
             "Frequenza": "giornaliera", "Attiva": "sì"}
FONTE_WATCH = {"ID": "F20", "Nome": "Fondazione", "URL": UFFICIALE, "Connettore": "watch",
               "Frequenza": "giornaliera", "Attiva": "sì"}


def test_giro_scrive_bando_fonte_e_log(tmp_path, monkeypatch, scheda_mare):
    amb, foglio = prepara(tmp_path, monkeypatch, scheda_mare, [FONTE_RSS])
    res = pipeline.Giro("giornaliero", amb, foglio).esegui()
    assert res.nuovi == 1
    [b] = foglio.leggi("BANDI")
    assert b["ID"] == "B0001"
    assert b["Stato"] == "Nuovo" and b["Prossima azione"] == "Valutare"
    assert b["Data prossima azione"] == "2026-10-10"
    assert b["Scadenza"] == "2027-01-15" and b["Scadenza confermata"] == "sicura"
    assert int(b["Punteggio"]) >= 80 and b["Esclusione"] == ""
    assert b["Lat"] == "38.19"
    [f] = foglio.leggi("FONTI")
    assert f["Ultimo esito"].startswith("ok") and f["Bandi portati"] == "1"
    [log] = foglio.leggi("LOG")
    assert log["Bandi nuovi"] == "1"


def test_stesso_bando_da_due_fonti_si_unisce(tmp_path, monkeypatch, scheda_mare):
    amb, foglio = prepara(tmp_path, monkeypatch, scheda_mare, [FONTE_RSS, FONTE_WATCH])
    res = pipeline.Giro("giornaliero", amb, foglio).esegui()
    assert res.nuovi == 1
    [b] = foglio.leggi("BANDI")
    assert b["Fonte"] == "F02, F20" and b["N. fonti"] == "2"
    assert b["Link bando"] == UFFICIALE or "rivista.example" in b["Link bando"]


def test_secondo_giro_non_duplica(tmp_path, monkeypatch, scheda_mare):
    amb, foglio = prepara(tmp_path, monkeypatch, scheda_mare, [FONTE_RSS])
    pipeline.Giro("giornaliero", amb, foglio).esegui()
    res = pipeline.Giro("giornaliero", amb, foglio).esegui()
    assert res.nuovi == 0
    assert len(foglio.leggi("BANDI")) == 1


def test_nuova_edizione_riapre_il_bando(tmp_path, monkeypatch, scheda_mare):
    amb, foglio = prepara(tmp_path, monkeypatch, scheda_mare, [FONTE_RSS])
    foglio.aggiungi("BANDI", [{
        "ID": "B0001", "Impronta": "vecchia", "Titolo": scheda_mare.titolo.replace("2027", "2026"),
        "Ente": scheda_mare.ente, "Scadenza": "2026-01-15", "Stato": "In attesa edizione", "Edizione": "2",
        "Fonte": "F02",
    }])
    res = pipeline.Giro("giornaliero", amb, foglio).esegui()
    assert res.nuovi == 0 and res.aggiornati == 1
    [b] = foglio.leggi("BANDI")
    assert b["Scadenza"] == "2027-01-15" and b["Edizione"] == "3" and b["Stato"] == "Nuovo"


def test_fonte_in_errore_conta_gli_errori(tmp_path, monkeypatch, scheda_mare):
    rotta = dict(FONTE_RSS, ID="F09", URL="https://rotto.example/feed/", **{"Errori consecutivi": "2"})
    amb, foglio = prepara(tmp_path, monkeypatch, scheda_mare, [rotta])
    res = pipeline.Giro("giornaliero", amb, foglio).esegui()
    assert res.fonti_errore == ["Rivista"]
    [f] = foglio.leggi("FONTI")
    assert f["Errori consecutivi"] == "3" and f["Ultimo esito"].startswith("errore")


def test_frequenze():
    assert pipeline.da_leggere({"Attiva": "sì", "Connettore": "rss", "Frequenza": "giornaliera"}, "giornaliero")
    assert not pipeline.da_leggere({"Attiva": "", "Connettore": "rss"}, "giornaliero")
    assert not pipeline.da_leggere({"Attiva": "sì", "Connettore": "ai_search"}, "settimanale")
    # il 7/10/2026 è mercoledì: le fonti settimanali aspettano lunedì o il giro settimanale
    assert not pipeline.da_leggere({"Attiva": "sì", "Connettore": "watch", "Frequenza": "settimanale"}, "giornaliero")
    assert pipeline.da_leggere({"Attiva": "sì", "Connettore": "watch", "Frequenza": "settimanale"}, "settimanale")


def test_geocodifica_open_meteo(tmp_path):
    import json

    from conftest import rete_finta

    from elbandito.archivio import Archivio

    citta = {"results": [{"name": "Venezia", "country": "Stati Uniti", "latitude": 1, "longitude": 1, "feature_code": "PPL"},
                         {"name": "Venezia", "country": "Italia", "latitude": 45.437, "longitude": 12.333, "feature_code": "PPLA"}]}
    rete = rete_finta({pipeline.GEOCODER: (200, "application/json", json.dumps(citta))})
    arch = Archivio(tmp_path / "a.sqlite")
    assert pipeline.geocodifica(rete, arch, "Venezia", "Italia") == (45.437, 12.333)  # il paese giusto vince
    assert arch.geo("Venezia, Italia") == (45.437, 12.333)
    vuota = rete_finta({pipeline.GEOCODER: (200, "application/json", '{"results": []}')})
    assert pipeline.geocodifica(vuota, arch, "Nessunposto", "") is None
    assert arch.geo("Nessunposto") is None  # i fallimenti non si memorizzano: al prossimo giro si riprova
