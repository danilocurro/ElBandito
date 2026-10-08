"""Fogli condivisi: stessi bandi, decisioni separate, niente dati personali del proprietario."""

from elbandito import servizi
from elbandito.config import Ambiente
from elbandito.demo import crea_demo
from elbandito.foglio import FoglioLocale, apri
from elbandito.sincronizza import sincronizza_foglio


def test_copia_bandi_senza_dati_personali(tmp_path):
    amb = Ambiente()
    crea_demo(amb)
    mio = apri(amb)
    servizi.salva_profilo(mio, "Curriculum", "Premio X 2024; residenza Y 2025")
    servizi.salva_note(mio, "B0001", "nota privata")
    servizi.registra_azione(mio, "B0002", "scarta")

    amico = FoglioLocale(tmp_path / "amico")
    e = sincronizza_foglio(mio, amico)
    assert e["nuovi"] == 9
    bandi = {b["ID"]: b for b in amico.leggi("BANDI")}
    assert bandi["B0001"]["Note"] == "" and bandi["B0002"]["Stato"] == "Nuovo"  # decisioni non copiate
    assert bandi["B0001"]["Punteggio"] == next(b for b in mio.leggi("BANDI") if b["ID"] == "B0001")["Punteggio"]
    profilo = {r["Campo"]: r["Valore"] for r in amico.leggi("PROFILO")}
    assert profilo["Curriculum"] == "" and profilo["Quota massima"] == "50"
    assert all(not e["Storico"] for e in amico.leggi("ENTI"))
    assert amico.leggi("CANDIDATURE") == []


def test_le_scelte_dell_amico_restano_sue(tmp_path):
    amb = Ambiente()
    crea_demo(amb)
    mio = apri(amb)
    amico = FoglioLocale(tmp_path / "amico")
    sincronizza_foglio(mio, amico)
    servizi.registra_azione(amico, "B0003", "interessa")
    servizi.salva_note(amico, "B0003", "la mia nota")
    # il principale aggiorna il bando (nuova scadenza): l'amico riceve il dato, tiene stato e note
    mio.aggiorna("BANDI", "ID", {"B0003": {"Scadenza": "2027-02-01", "Scadenza confermata": "sicura"}})
    e = sincronizza_foglio(mio, amico)
    assert e["nuovi"] == 0 and e["aggiornati"] == 1
    b = next(b for b in amico.leggi("BANDI") if b["ID"] == "B0003")
    assert b["Scadenza"] == "2027-02-01" and b["Stato"] == "Da preparare" and b["Note"] == "la mia nota"
    assert next(x for x in mio.leggi("BANDI") if x["ID"] == "B0003")["Stato"] == "Nuovo"
