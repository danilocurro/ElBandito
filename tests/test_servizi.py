"""Ciclo di vita, ricerca e calendario sui dati d'esempio (foglio locale)."""

import pytest

from elbandito import servizi
from elbandito.config import Ambiente
from elbandito.demo import crea_demo
from elbandito.foglio import apri


@pytest.fixture
def foglio(tmp_path):
    amb = Ambiente()
    crea_demo(amb)
    return apri(amb)


def test_demo_passa_dai_filtri_veri(foglio):
    bandi = {b["ID"]: b for b in foglio.leggi("BANDI")}
    assert len(bandi) == 9
    assert all("(esempio)" in b["Titolo"] for b in bandi.values())
    assert "età" in bandi["B0004"]["Esclusione"]           # under 30
    assert "enti" in bandi["B0005"]["Esclusione"]          # solo persone giuridiche
    assert "senza premio" in bandi["B0006"]["Esclusione"]  # call a pagamento senza premio
    assert bandi["B0001"]["Esclusione"] == "" and int(bandi["B0001"]["Punteggio"]) >= 75


def test_seconda_demo_non_duplica(foglio):
    assert crea_demo(Ambiente()) == 0


def test_mi_interessa_crea_checklist_e_data_a_ritroso(foglio):
    r = servizi.registra_azione(foglio, "B0001", "interessa")
    assert r["Stato"] == "Da preparare"
    assert r["Data prossima azione"] == "2026-11-11"  # scadenza 21/11 - 10 giorni
    c = servizi.scheda(foglio, "B0001")["Candidatura"]
    assert [v["voce"] for v in c["Checklist"]] == ["portfolio 15 immagini", "statement", "CV"]
    lista = servizi.spunta(foglio, "B0001", "statement")
    assert [v["fatto"] for v in lista] == [False, True, False]


def test_inviato_ed_esito(foglio):
    servizi.registra_azione(foglio, "B0008", "inviato", data_esito="2027-01-10")
    b = servizi.scheda(foglio, "B0008")
    assert b["Stato"] == "Inviato" and b["Data prossima azione"] == "2027-01-10"
    assert b["Candidatura"]["Inviata il"] == "2026-10-07"
    servizi.registra_azione(foglio, "B0008", "non_selezionato")
    assert servizi.scheda(foglio, "B0008")["Candidatura"]["Esito"] == "Non selezionato"


def test_azione_sconosciuta(foglio):
    with pytest.raises(ValueError):
        servizi.registra_azione(foglio, "B0001", "vola")


def test_conferma_scadenza(foglio):
    servizi.conferma_scadenza(foglio, "B0002", "2026-12-01")
    b = servizi.scheda(foglio, "B0002")
    assert b["Scadenza"] == "2026-12-01" and b["Scadenza confermata"] == "sicura"


def test_cerca_con_filtri(foglio):
    tutti = servizi.cerca(foglio)
    assert all(not b["Esclusione"] for b in tutti)
    assert [b["Punteggio"] for b in tutti] == sorted((b["Punteggio"] for b in tutti), key=lambda x: -float(x))
    assert {b["ID"] for b in servizi.cerca(foglio, tipo="residenza")} == {"B0002", "B0007"}
    assert all(b["Giorni"] <= 30 for b in servizi.cerca(foglio, entro_giorni=30))
    assert len(servizi.cerca(foglio, mostra_esclusi=True)) == 9


def test_profilo_e_fonti(foglio):
    servizi.salva_profilo(foglio, "Quota massima", "10")
    assert any(r["Valore"] == "10" for r in foglio.leggi("PROFILO") if r["Campo"] == "Quota massima")
    nuovo = servizi.aggiungi_fonte(foglio, "Festival X", "https://festival.example/open-call")
    servizi.aggiorna_fonte(foglio, nuovo, {"Attiva": "no"})
    assert next(f for f in foglio.leggi("FONTI") if f["ID"] == nuovo)["Attiva"] == "no"


def test_ics(foglio):
    ics = servizi.esporta_ics(foglio)
    assert ics.startswith("BEGIN:VCALENDAR") and ics.count("BEGIN:VEVENT") == 6  # esclusi fuori


def test_statistiche(foglio):
    s = servizi.statistiche(foglio)
    assert s["bandi_totali"] == 9 and s["per_stato"]["Nuovo"] == 7
    assert s["migliori_da_valutare"][0]["Punteggio"]
