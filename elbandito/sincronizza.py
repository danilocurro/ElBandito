"""Fogli condivisi: un giro di raccolta, più persone con decisioni separate.

Il collettore lavora sul foglio principale. `sincronizza` copia i bandi in
uno o più fogli collegati (ELBANDITO_FOGLI_CONDIVISI, ID separati da virgola):
i dati del bando e il punteggio arrivano dal principale, mentre stato,
prossima azione, storico e note restano di chi usa quel foglio.

Pensato per chi ha lo stesso profilo di ricerca (stessa età, residenza,
lingue, quota): i punteggi del principale valgono anche per gli altri.
Dati personali del proprietario (curriculum, storico con gli enti, note,
candidature) non vengono copiati.
"""

from __future__ import annotations

import os
from datetime import timedelta

from .config import Ambiente, iso, oggi
from .foglio import FoglioBase, GoogleFoglio, apri
from .modelli import COLONNE

# Colonne di BANDI che appartengono a chi usa il foglio, non al bando
PERSONALI = {"Stato", "Prossima azione", "Data prossima azione", "Storico", "Note"}
# Campi del profilo che non escono dal foglio principale
PROFILO_PRIVATO = {"Curriculum", "Nome d'arte"}


def fogli_condivisi() -> list[str]:
    return [x.strip() for x in os.environ.get("ELBANDITO_FOGLI_CONDIVISI", "").split(",") if x.strip()]


def _prepara_destinazione(origine: FoglioBase, dest: FoglioBase) -> list[str]:
    """Alla prima volta crea le schede e copia profilo (senza i campi privati), fonti ed enti."""
    fatto = dest.prepara(con_seed=False)
    sh = getattr(dest, "_sh", None)
    for nome in ("Foglio1", "Sheet1"):
        try:
            if sh is not None and len(sh.worksheets()) > 1:
                sh.del_worksheet(sh.worksheet(nome))
        except Exception:
            pass
    if not dest.leggi("PROFILO"):
        righe = [dict(r, Valore="") if r.get("Campo") in PROFILO_PRIVATO else r for r in origine.leggi("PROFILO")]
        dest.aggiungi("PROFILO", righe)
        fatto.append(f"PROFILO: {len(righe)} campi copiati (curriculum escluso)")
    if not dest.leggi("ENTI"):
        dest.aggiungi("ENTI", [dict(e, Storico="") for e in origine.leggi("ENTI")])
        fatto.append("ENTI copiati (senza storico)")
    return fatto


def sincronizza_foglio(origine: FoglioBase, dest: FoglioBase) -> dict:
    note = _prepara_destinazione(origine, dest)
    esistenti = {b.get("ID"): b for b in dest.leggi("BANDI")}
    nuovi, modifiche = [], {}
    adesso = iso(oggi())
    oggettive = [c for c in COLONNE["BANDI"] if c not in PERSONALI]
    for b in origine.leggi("BANDI"):
        if not b.get("ID"):
            continue
        if b["ID"] not in esistenti:
            if b.get("Stato") == "Archiviato":
                continue
            riga = {c: b.get(c, "") for c in oggettive}
            riga.update({"Stato": "Nuovo", "Prossima azione": "Valutare",
                         "Data prossima azione": iso(oggi() + timedelta(days=3)),
                         "Storico": f"{adesso} arrivato dal foglio condiviso", "Note": ""})
            nuovi.append(riga)
            continue
        mio = esistenti[b["ID"]]
        diff = {c: b.get(c, "") for c in oggettive if str(b.get(c, "")) != str(mio.get(c, ""))}
        if diff:
            modifiche[b["ID"]] = diff
    dest.aggiungi("BANDI", nuovi)
    dest.aggiorna("BANDI", "ID", modifiche)
    # fonti: elenco e stato come nel principale (sono la stessa rete)
    fonti = {f["ID"]: f for f in dest.leggi("FONTI")}
    nuove_fonti = [f for f in origine.leggi("FONTI") if f.get("ID") not in fonti]
    dest.aggiungi("FONTI", nuove_fonti)
    dest.aggiorna("FONTI", "ID", {f["ID"]: {k: v for k, v in f.items() if k != "ID"}
                                  for f in origine.leggi("FONTI") if f.get("ID") in fonti})
    dest.aggiungi("LOG", [{"Data": adesso, "Tipo giro": "sincronizzazione", "Bandi nuovi": len(nuovi),
                           "Bandi aggiornati": len(modifiche), "Note": "; ".join(note)}])
    return {"nuovi": len(nuovi), "aggiornati": len(modifiche), "note": note}


def sincronizza(amb: Ambiente | None = None, destinazioni: list[str] | None = None) -> dict[str, dict]:
    amb = amb or Ambiente()
    origine = apri(amb)
    esiti = {}
    for sheet_id in destinazioni if destinazioni is not None else fogli_condivisi():
        dest = GoogleFoglio(Ambiente(sheet_id=sheet_id, credenziali_google=amb.credenziali_google))
        esiti[sheet_id] = sincronizza_foglio(origine, dest)
    return esiti
