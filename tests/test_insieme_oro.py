"""L'insieme d'oro: la rete di fonti deve coprire le opportunità note."""

import csv

from elbandito.foglio import CARTELLA_SEED
from elbandito.richiamo import copertura, insieme_oro, richiamo


def fonti_seed():
    with (CARTELLA_SEED / "fonti.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_le_fonti_di_partenza_coprono_l_insieme_d_oro():
    scoperte = [v["Opportunità"] for v, trovate in copertura(fonti_seed())
                if v["Canale"] != "passaparola" and not trovate]
    assert scoperte == [], f"Opportunità senza una fonte attiva: {scoperte}"


def test_il_riconoscimento_funziona_sui_titoli_reali():
    titoli = [
        {"Titolo": "Premio Driving Energy 2026 – Fotografia Contemporanea", "Ente": "Terna"},
        {"Titolo": "Strategia Fotografia 2026", "Ente": "MiC"},
        {"Titolo": "Italian Council – 14ª edizione", "Ente": "MiC"},
        {"Titolo": "Arte Laguna Prize 2027", "Ente": "Arte Laguna"},
    ]
    trovati = {v["Opportunità"] for v, ok in richiamo(titoli, []) if ok}
    assert {"Premio Driving Energy", "Strategia Fotografia", "Italian Council", "Arte Laguna Prize"} <= trovati


def test_insieme_oro_ha_le_colonne_attese():
    for voce in insieme_oro():
        assert voce["Opportunità"] and voce["Riconosci"] and voce["Canale"] in ("fonti", "passaparola")
