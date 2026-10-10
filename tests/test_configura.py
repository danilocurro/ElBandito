"""Il questionario `elbandito configura` e i preset dei pesi."""

import csv

from elbandito import mcp_server
from elbandito.config import Ambiente, Profilo
from elbandito.configura import PRESET_PESI, configura
from elbandito.foglio import apri


def test_questionario_salva_profilo_e_copia_personale():
    risposte = iter([
        "illustrazione", "illustrazione, fumetto", "", "1985", "",           # chi sei
        "Napoli", "", "", "Campania", "", "Campania, Napoli, Salerno", "Campania", "Lazio, Puglia",  # dove
        "", "italiano, inglese, francese", "30", "", "",                       # come
        "mare, città, lavoro", "", "",                                        # lavoro
        "2",                                                                  # preset "conta il tema"
        "agente",                                                             # motore
    ])
    amb = Ambiente()
    nuovi = configura(amb, chiedi=lambda _: next(risposte), scrivi=lambda _: None, geocodifica=False)
    p = Profilo(apri(amb).leggi("PROFILO"))
    assert p.testo("Tema") == "illustrazione" and p.eta == 41
    assert p.testo("Città di riferimento") == "Napoli"  # proposta dalla nuova base
    assert p.lista("Luoghi casa") == ["Campania", "Napoli", "Salerno"]
    assert p.numero("Quota massima") == 30 and p.testo("Motore estrazione") == "agente"
    assert p.pesi == {k: float(v) for k, v in PRESET_PESI["conta il tema"].items()}
    assert "Discipline metà" not in nuovi  # Invio = valore invariato
    copia = amb.cartella_dati / "personale" / "profilo.csv"
    righe = {r["Campo"]: r["Valore"] for r in csv.DictReader(copia.open(encoding="utf-8"))}
    assert righe["Tema"] == "illustrazione"


def test_tutti_i_campi_del_seed_hanno_una_nota():
    from elbandito.foglio import CARTELLA_SEED

    righe = list(csv.DictReader((CARTELLA_SEED / "profilo.csv").open(encoding="utf-8")))
    senza = [r["Campo"] for r in righe if not r["Note"].strip()]
    assert senza == [], f"Campi senza spiegazione: {senza}"


def test_preset_pesi_da_mcp():
    mcp_server.crea_dati_esempio()
    prima = {b["ID"]: b["Punteggio"] for b in mcp_server.cerca_bandi(mostra_esclusi=True, limite=20)}
    r = mcp_server.applica_preset_pesi("vicino a casa")
    assert r["ricalcolati"] == 9
    dopo = {b["ID"]: b["Punteggio"] for b in mcp_server.cerca_bandi(mostra_esclusi=True, limite=20)}
    assert prima != dopo
    # Oslo scende rispetto a Bologna quando la geografia pesa di più
    assert float(dopo["B0003"]) - float(dopo["B0001"]) < float(prima["B0003"]) - float(prima["B0001"])


def test_ricalcola_senza_storico_grezzo_conserva_le_esclusioni(tmp_path):
    from elbandito.pipeline import ricalcola

    amb = Ambiente()
    mcp_server.crea_dati_esempio()
    (amb.cartella_dati / "archivio.sqlite").unlink()  # come se la cache dell'archivio fosse persa
    assert ricalcola(amb) == 9
    bandi = {b["ID"]: b for b in apri(amb).leggi("BANDI")}
    assert "età" in bandi["B0004"]["Esclusione"] and "enti" in bandi["B0005"]["Esclusione"]
    assert int(bandi["B0001"]["Punteggio"]) >= 75
