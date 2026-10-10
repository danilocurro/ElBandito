from datetime import date

from conftest import leggi

from elbandito.connettori import testo_da_html as pulisci
from elbandito.estrazione import citazione_presente, leggi_data, verifica


def test_date_in_piu_lingue():
    assert leggi_data("15 gennaio 2027") == date(2027, 1, 15)
    assert leggi_data("entro il 30 novembre 2026, ore 12:00") == date(2026, 11, 30)
    assert leggi_data("March 3rd, 2027 23:59 CET") == date(2027, 3, 3)
    assert leggi_data("1er décembre 2026") == date(2026, 12, 1)
    assert leggi_data("2027-02-01") == date(2027, 2, 1)
    assert leggi_data("") is None


def test_data_senza_anno_va_nel_futuro():
    # il 7/10/2026 "15 gennaio" è il prossimo gennaio
    assert leggi_data("15 gennaio") == date(2027, 1, 15)


def test_citazione_tollera_spazi_e_apostrofi():
    testo = "Le candidature   vanno inviate entro il 15 gennaio 2027 all’indirizzo indicato."
    assert citazione_presente("vanno inviate entro il 15 gennaio 2027 all'indirizzo", testo)
    assert not citazione_presente("entro il 20 marzo 2027", testo)
    assert not citazione_presente("", testo)


def test_scheda_onesta_resta_sicura(scheda_mare):
    testo = pulisci(leggi("bando.html"))
    v = verifica(scheda_mare, testo)
    assert v is not None
    assert v.scadenza == date(2027, 1, 15)
    assert v.confermata
    assert "15 gennaio 2027" in v.estratto


def test_citazione_inventata_rende_da_verificare(scheda_mare):
    testo = pulisci(leggi("bando.html"))
    scheda_mare.quota_iscrizione_eur = 10
    scheda_mare.quota_citazione = "Quota di iscrizione: 10 euro."  # non esiste nel testo
    v = verifica(scheda_mare, testo)
    assert v is not None
    assert not v.confermata
    assert v.scheda.quota_iscrizione_eur is None  # il dato senza fonte si svuota


def test_scadenza_passata_si_scarta(scheda_mare):
    scheda_mare.scadenza = "15 gennaio 2026"
    scheda_mare.scadenza_citazione = ""
    assert verifica(scheda_mare, "testo qualsiasi") is None


def test_scadenze_ricorrenti():
    # avvisi annuali: "il 30 ottobre di ogni anno" vale come la prossima occorrenza
    assert leggi_data("entro e non oltre il 30 ottobre di ogni anno") == date(2026, 10, 30)
    assert leggi_data("March 1st every year") == date(2027, 3, 1)
