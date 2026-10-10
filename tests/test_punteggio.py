import csv
from datetime import date

from conftest import PAGINE  # noqa: F401  (assicura il path dei test)

from elbandito.config import Profilo
from elbandito.estrazione import SchedaVerificata
from elbandito.foglio import CARTELLA_SEED
from elbandito.punteggio import valuta


def profilo():
    with (CARTELLA_SEED / "profilo.csv").open(encoding="utf-8") as f:
        return Profilo(list(csv.DictReader(f)))


def enti():
    with (CARTELLA_SEED / "enti.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def v(scheda, scadenza=date(2027, 1, 15), confermata=True):
    return SchedaVerificata(scheda, scadenza, confermata, "")


def test_bando_ideale_punteggio_alto(scheda_mare):
    e = valuta(v(scheda_mare), profilo(), enti())
    assert e.esclusione == ""
    assert e.punteggio >= 80
    assert "fotografia" in e.motivazione.lower()
    assert "Emilia-Romagna" in e.motivazione  # "Luoghi casa" del profilo d'esempio


def test_under_30_escluso(scheda_mare):
    scheda_mare.eta_max = 30
    assert "età" in valuta(v(scheda_mare), profilo(), enti()).esclusione


def test_limite_eta_dal_profilo(scheda_mare):
    # profilo d'esempio: nato nel 1990, quindi 36 anni nel 2026
    scheda_mare.eta_max = 35
    assert "età" in valuta(v(scheda_mare), profilo(), enti()).esclusione
    scheda_mare.eta_max = 40
    assert valuta(v(scheda_mare), profilo(), enti()).esclusione == ""


def test_geografia_segue_il_profilo(scheda_mare):
    p = profilo()
    casa = valuta(v(scheda_mare), p, enti()).dettaglio["geografia"]
    scheda_mare.citta, scheda_mare.regione = "Firenze", "Toscana"  # "Luoghi vicini"
    vicino = valuta(v(scheda_mare), p, enti()).dettaglio["geografia"]
    scheda_mare.citta, scheda_mare.regione = "Bari", "Puglia"
    paese = valuta(v(scheda_mare), p, enti()).dettaglio["geografia"]
    scheda_mare.citta, scheda_mare.regione, scheda_mare.paese = "Lione", "", "Francia"
    europa = valuta(v(scheda_mare), p, enti()).dettaglio["geografia"]
    assert casa > vicino > paese > europa


def test_solo_enti_escluso(scheda_mare):
    scheda_mare.solo_enti = True
    assert "enti" in valuta(v(scheda_mare), profilo(), enti()).esclusione


def test_quota_oltre_soglia(scheda_mare):
    scheda_mare.quota_iscrizione_eur = 80
    assert "80 €" in valuta(v(scheda_mare), profilo(), enti()).esclusione


def test_vanity_call(scheda_mare):
    scheda_mare.quota_iscrizione_eur = 30
    scheda_mare.valore_eur = None
    scheda_mare.copre_viaggio = scheda_mare.copre_alloggio = scheda_mare.include_mostra = False
    assert "senza premio" in valuta(v(scheda_mare), profilo(), enti()).esclusione


def test_lingua_non_parlata(scheda_mare):
    scheda_mare.lingue_candidatura = ["tedesco"]
    assert "Lingua" in valuta(v(scheda_mare), profilo(), enti()).esclusione


def test_scadenza_troppo_vicina(scheda_mare):
    assert "vicina" in valuta(v(scheda_mare, scadenza=date(2026, 10, 10)), profilo(), enti()).esclusione


def test_residenza_altra_regione(scheda_mare):
    scheda_mare.residenza_richiesta = "residenti in Lombardia"
    assert "Lombardia" in valuta(v(scheda_mare), profilo(), enti()).esclusione
    scheda_mare.residenza_richiesta = "residenti in Italia"
    assert valuta(v(scheda_mare), profilo(), enti()).esclusione == ""


def test_ente_noto_pesa_sul_prestigio(scheda_mare):
    base = valuta(v(scheda_mare), profilo(), enti()).dettaglio["prestigio"]
    scheda_mare.ente = "Cortona On The Move"
    assert valuta(v(scheda_mare), profilo(), enti()).dettaglio["prestigio"] > base


def test_arti_visive_generiche_valgono_meta(scheda_mare):
    p = profilo()
    piena = valuta(v(scheda_mare), p, enti()).dettaglio["disciplina"]
    scheda_mare.disciplina = "arti visive"
    scheda_mare.titolo = "Premio Portici 2027"
    assert valuta(v(scheda_mare), p, enti()).dettaglio["disciplina"] == piena / 2


def test_da_verificare_compare_nei_rischi(scheda_mare):
    assert "verificare" in valuta(v(scheda_mare, confermata=False), profilo(), enti()).rischi


def test_enti_noti_solo_per_parole_intere(scheda_mare):
    p, e = profilo(), enti()
    for falso in ("On the Move", "Teatri Riflessi Festival", ".ART"):
        scheda_mare.ente = falso
        assert valuta(v(scheda_mare), p, e).dettaglio["prestigio"] == 3.0, falso  # 20%: ente non noto
    scheda_mare.ente = "Fondazione CRT – Torino"
    assert valuta(v(scheda_mare), p, e).dettaglio["prestigio"] == 10.5  # livello 2


def test_importi_con_separatore_delle_migliaia():
    from elbandito.pipeline import scheda_da_riga

    assert scheda_da_riga({"Titolo": "x", "Valore": "fino a 32.700 € e alloggio"}).valore_eur == 32700
    assert scheda_da_riga({"Titolo": "x", "Valore": "premio di 1.500,50 euro"}).valore_eur == 1500.5


def test_bandi_per_enti_con_partner(scheda_mare):
    from elbandito.config import Profilo

    scheda_mare.solo_enti = True
    solo_persona = profilo()
    assert "enti" in valuta(v(scheda_mare), solo_persona, enti()).esclusione
    righe = [{"Campo": k, "Valore": v_} for k, v_ in solo_persona.valori.items()]
    con_associazione = Profilo(righe + [{"Campo": "Si candida come", "Valore": "persona e associazione"}])
    e = valuta(v(scheda_mare), con_associazione, enti())
    assert e.esclusione == "" and "ente proponente" in e.rischi
