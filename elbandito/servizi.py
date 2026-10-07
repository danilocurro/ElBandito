"""Operazioni sui bandi, condivise da dashboard locale e server MCP.

Sono le stesse regole di Codice.gs (la web app Apps Script): chi usa il
foglio Google e chi usa i CSV locali vede lo stesso comportamento.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone

from .config import iso, oggi
from .foglio import FoglioBase
from .modelli import STATI

AZIONI = {
    # azione: (nuovo stato, prossima azione, come calcolare la data)
    "interessa": ("Da preparare", "Preparare i materiali", "scadenza-10"),
    "scarta": ("Scartato", "", ""),
    "pronto": ("Pronto", "Inviare la candidatura", "scadenza-2"),
    "inviato": ("Inviato", "Attendere l'esito", "esito"),
    "vinto": ("Vinto", "Pianificare", "+7"),
    "non_selezionato": ("Non selezionato", "Annotare il feedback", "+7"),
    "prossimo_anno": ("In attesa edizione", "Controllare la nuova call", "apertura"),
    "riapri": ("Nuovo", "Valutare", "+3"),
    "archivia": ("Archiviato", "", ""),
}
APERTI = ("Nuovo", "Da preparare", "Pronto")


def _data(s: str) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _num(v) -> float | None:
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return None


def _bando(foglio: FoglioBase, id_bando: str) -> dict:
    for b in foglio.leggi("BANDI"):
        if b.get("ID") == id_bando:
            return b
    raise ValueError(f"Bando non trovato: {id_bando}")


def _checklist(c: dict) -> list[dict]:
    try:
        return json.loads(c.get("Checklist") or "[]")
    except json.JSONDecodeError:
        return []


# --- lettura -----------------------------------------------------------------

def dati(foglio: FoglioBase) -> dict:
    """Lo stesso JSON di getBandi() nella web app."""
    bandi = [b for b in foglio.leggi("BANDI") if b.get("Stato") != "Archiviato"]
    for b in bandi:
        try:
            b["Dettaglio punteggio"] = json.loads(b.get("Dettaglio punteggio") or "{}")
        except json.JSONDecodeError:
            b["Dettaglio punteggio"] = {}
    candidature = {}
    for c in foglio.leggi("CANDIDATURE"):
        c["Checklist"] = _checklist(c)
        candidature[c["ID bando"]] = c
    return {
        "oggi": iso(oggi()),
        "bandi": bandi,
        "candidature": candidature,
        "profilo": {r["Campo"]: r.get("Valore", "") for r in foglio.leggi("PROFILO") if r.get("Campo")},
        "fonti": foglio.leggi("FONTI"),
        "enti": foglio.leggi("ENTI"),
        "log": list(reversed(foglio.leggi("LOG")[-15:])),
        "stati": STATI,
        "linkGitHub": "",
    }


def cerca(foglio: FoglioBase, testo: str = "", tipo: str = "", stato: str = "", entro_giorni: int | None = None,
          quota_max: float | None = None, punteggio_min: float | None = None, mostra_esclusi: bool = False,
          limite: int = 20) -> list[dict]:
    q = testo.lower().strip()
    out = []
    for b in foglio.leggi("BANDI"):
        if b.get("Stato") == "Archiviato" and stato != "Archiviato":
            continue
        if not mostra_esclusi and b.get("Esclusione"):
            continue
        if stato and b.get("Stato") != stato:
            continue
        if not stato and not mostra_esclusi and b.get("Stato") in ("Scartato", "Vinto", "Non selezionato"):
            continue
        if tipo and b.get("Tipo") != tipo:
            continue
        if q and q not in " ".join(str(b.get(k, "")) for k in
                                   ("Titolo", "Ente", "Temi", "Città", "Paese", "Valore", "Motivazione")).lower():
            continue
        scad = _data(b.get("Scadenza", ""))
        if entro_giorni is not None and (scad is None or (scad - oggi()).days > entro_giorni):
            continue
        quota = _num(b.get("Quota iscrizione", ""))
        if quota_max is not None and (quota is None or quota > quota_max):
            continue
        if punteggio_min is not None and (_num(b.get("Punteggio", "")) or 0) < punteggio_min:
            continue
        out.append(b)
    out.sort(key=lambda b: -(_num(b.get("Punteggio", "")) or 0))
    return [compatto(b) for b in out[:limite]]


def compatto(b: dict) -> dict:
    scad = _data(b.get("Scadenza", ""))
    return {
        "ID": b.get("ID"), "Titolo": b.get("Titolo"), "Ente": b.get("Ente"), "Tipo": b.get("Tipo"),
        "Luogo": ", ".join(x for x in (b.get("Città"), b.get("Paese")) if x),
        "Scadenza": b.get("Scadenza"), "Giorni": (scad - oggi()).days if scad else None,
        "Scadenza confermata": b.get("Scadenza confermata"), "Quota": b.get("Quota iscrizione"),
        "Valore": b.get("Valore"), "Punteggio": b.get("Punteggio"), "Motivazione": b.get("Motivazione"),
        "Rischi": b.get("Rischi"), "Esclusione": b.get("Esclusione"), "Stato": b.get("Stato"),
    }


def scheda(foglio: FoglioBase, id_bando: str) -> dict:
    b = _bando(foglio, id_bando)
    c = next((c for c in foglio.leggi("CANDIDATURE") if c.get("ID bando") == id_bando), None)
    out = {k: v for k, v in b.items() if v not in ("", None)}
    if c:
        out["Candidatura"] = {**{k: v for k, v in c.items() if v}, "Checklist": _checklist(c)}
    return out


def statistiche(foglio: FoglioBase) -> dict:
    bandi = foglio.leggi("BANDI")
    per_stato: dict[str, int] = {}
    for b in bandi:
        per_stato[b.get("Stato", "?")] = per_stato.get(b.get("Stato", "?"), 0) + 1
    vivi = [b for b in bandi if b.get("Stato") in APERTI and not b.get("Esclusione")]
    vicine = sorted((b for b in vivi if (d := _data(b.get("Scadenza", ""))) and 0 <= (d - oggi()).days <= 21),
                    key=lambda b: b["Scadenza"])
    fonti = foglio.leggi("FONTI")
    log = foglio.leggi("LOG")
    return {
        "oggi": iso(oggi()),
        "bandi_totali": len(bandi),
        "per_stato": per_stato,
        "esclusi": sum(1 for b in bandi if b.get("Esclusione")),
        "migliori_da_valutare": [compatto(b) for b in sorted(
            (b for b in vivi if b.get("Stato") == "Nuovo"), key=lambda b: -(_num(b.get("Punteggio", "")) or 0))[:5]],
        "scadenze_entro_21_giorni": [compatto(b) for b in vicine],
        "da_verificare": sum(1 for b in vivi if b.get("Scadenza confermata") != "sicura"),
        "fonti_attive": sum(1 for f in fonti if str(f.get("Attiva", "")).lower() in ("sì", "si", "x", "true", "1")),
        "fonti_in_errore": [f.get("Nome") for f in fonti if int(_num(f.get("Errori consecutivi", "")) or 0) >= 3],
        "ultimo_giro": log[-1] if log else None,
    }


# --- azioni ------------------------------------------------------------------

def _prossima_data(regola: str, b: dict, data_esito: str = "") -> str:
    scad = _data(b.get("Scadenza", ""))
    if regola.startswith("scadenza-"):
        if not scad:
            return iso(oggi() + timedelta(days=7 if regola.endswith("10") else 2))
        return iso(max(oggi(), scad - timedelta(days=int(regola.split("-")[1]))))
    if regola.startswith("+"):
        return iso(oggi() + timedelta(days=int(regola[1:])))
    if regola == "esito":
        return data_esito
    if regola == "apertura":
        base = _data(b.get("Apertura", "")) or (scad - timedelta(days=60) if scad else None)
        return iso(base + timedelta(days=365 - 14)) if base else iso(oggi() + timedelta(days=300))
    return ""


def registra_azione(foglio: FoglioBase, id_bando: str, azione: str, data_esito: str = "", nota: str = "") -> dict:
    if azione not in AZIONI:
        raise ValueError(f"Azione sconosciuta: {azione}. Possibili: {', '.join(AZIONI)}")
    b = _bando(foglio, id_bando)
    stato, prossima, regola = AZIONI[azione]
    adesso = iso(oggi())
    storico = (b.get("Storico", "") + "\n" if b.get("Storico") else "") + f"{adesso} {azione.replace('_', ' ')}" + (
        f" — {nota}" if nota else "")
    campi = {"Stato": stato, "Prossima azione": prossima, "Data prossima azione": _prossima_data(regola, b, data_esito),
             "Aggiornato il": adesso, "Storico": storico}
    foglio.aggiorna("BANDI", "ID", {id_bando: campi})
    if azione == "interessa":
        _assicura_candidatura(foglio, b)
    if azione in ("inviato", "vinto", "non_selezionato"):
        _assicura_candidatura(foglio, b)
        c = {"Aggiornato il": adesso}
        if azione == "inviato":
            c["Inviata il"] = adesso
            if data_esito:
                c["Data esito"] = data_esito
        else:
            c["Esito"] = "Vinto" if azione == "vinto" else "Non selezionato"
        foglio.aggiorna("CANDIDATURE", "ID bando", {id_bando: c})
    return {**compatto({**b, **campi}), "Prossima azione": prossima, "Data prossima azione": campi["Data prossima azione"]}


def _assicura_candidatura(foglio: FoglioBase, b: dict) -> None:
    if any(c.get("ID bando") == b["ID"] for c in foglio.leggi("CANDIDATURE")):
        return
    voci = [v.strip() for v in re.split(r"[;\n]", b.get("Materiali richiesti", "")) if v.strip()] or [
        "Portfolio", "Statement", "CV"]
    foglio.aggiungi("CANDIDATURE", [{
        "ID bando": b["ID"], "Titolo": b.get("Titolo", ""),
        "Checklist": json.dumps([{"voce": v, "fatto": False} for v in voci], ensure_ascii=False),
        "Aggiornato il": iso(oggi()),
    }])


def salva_checklist(foglio: FoglioBase, id_bando: str, checklist: list[dict], cartella: str | None = None) -> None:
    _assicura_candidatura(foglio, _bando(foglio, id_bando))
    campi = {"Checklist": json.dumps(checklist, ensure_ascii=False), "Aggiornato il": iso(oggi())}
    if cartella is not None:
        campi["Cartella"] = cartella
    foglio.aggiorna("CANDIDATURE", "ID bando", {id_bando: campi})


def spunta(foglio: FoglioBase, id_bando: str, voce: str, fatto: bool = True) -> list[dict]:
    """Segna (o aggiunge) una voce della checklist cercandola per nome."""
    b = _bando(foglio, id_bando)
    _assicura_candidatura(foglio, b)
    c = next(c for c in foglio.leggi("CANDIDATURE") if c.get("ID bando") == id_bando)
    lista = _checklist(c)
    for v in lista:
        if voce.lower() in v["voce"].lower():
            v["fatto"] = fatto
            break
    else:
        lista.append({"voce": voce, "fatto": fatto})
    salva_checklist(foglio, id_bando, lista)
    return lista


def salva_feedback(foglio: FoglioBase, id_bando: str, feedback: str) -> None:
    _assicura_candidatura(foglio, _bando(foglio, id_bando))
    foglio.aggiorna("CANDIDATURE", "ID bando", {id_bando: {"Feedback": feedback, "Aggiornato il": iso(oggi())}})


def salva_note(foglio: FoglioBase, id_bando: str, note: str) -> None:
    _bando(foglio, id_bando)
    foglio.aggiorna("BANDI", "ID", {id_bando: {"Note": note, "Aggiornato il": iso(oggi())}})


def conferma_scadenza(foglio: FoglioBase, id_bando: str, data: str = "") -> None:
    """Le date estratte dall'AI entrano nei promemoria solo dopo questa conferma umana."""
    b = _bando(foglio, id_bando)
    if data and not _data(data):
        raise ValueError("La data va scritta come aaaa-mm-gg")
    foglio.aggiorna("BANDI", "ID", {id_bando: {
        "Scadenza": data or b.get("Scadenza", ""), "Scadenza confermata": "sicura", "Aggiornato il": iso(oggi()),
        "Storico": (b.get("Storico", "") + "\n" if b.get("Storico") else "") + f"{iso(oggi())} scadenza confermata a mano",
    }})


def aggiorna_fonte(foglio: FoglioBase, id_fonte: str, campi: dict) -> None:
    if not any(f.get("ID") == id_fonte for f in foglio.leggi("FONTI")):
        raise ValueError(f"Fonte non trovata: {id_fonte}")
    foglio.aggiorna("FONTI", "ID", {id_fonte: campi})


def aggiungi_fonte(foglio: FoglioBase, nome: str, url: str, connettore: str = "watch", parametri: str = "",
                   frequenza: str = "settimanale", livello: str = "", tipo: str = "") -> str:
    if not re.match(r"^https?://", url):
        raise ValueError("Serve un URL completo (https://…)")
    fonti = foglio.leggi("FONTI")
    n = max((int(m.group()) for f in fonti if (m := re.search(r"\d+", str(f.get("ID", ""))))), default=0) + 1
    nuovo = f"F{n:02d}"
    foglio.aggiungi("FONTI", [{
        "ID": nuovo, "Nome": nome, "URL": url, "Connettore": connettore, "Parametri": parametri,
        "Frequenza": frequenza, "Livello": livello, "Tipo": tipo, "Attiva": "sì", "Bandi portati": 0,
        "Errori consecutivi": 0, "Note": "Aggiunta da ElBandito",
    }])
    return nuovo


def salva_profilo(foglio: FoglioBase, campo: str, valore: str) -> None:
    if any(r.get("Campo") == campo for r in foglio.leggi("PROFILO")):
        foglio.aggiorna("PROFILO", "Campo", {campo: {"Valore": valore}})
    else:
        foglio.aggiungi("PROFILO", [{"Campo": campo, "Valore": valore}])


# --- calendario --------------------------------------------------------------

def _ics(s: str) -> str:
    return str(s).replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def esporta_ics(foglio: FoglioBase) -> str:
    adesso = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    righe = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//ElBandito//IT", "CALSCALE:GREGORIAN",
             "X-WR-CALNAME:ElBandito"]
    for b in foglio.leggi("BANDI"):
        if not b.get("Scadenza") or b.get("Stato") not in APERTI or b.get("Esclusione"):
            continue
        titolo = ("" if b.get("Scadenza confermata") == "sicura" else "[da verificare] ") + f"Scadenza: {b['Titolo']}"
        righe += [
            "BEGIN:VEVENT", f"UID:{b['ID']}-scadenza@elbandito", f"DTSTAMP:{adesso}",
            f"DTSTART;VALUE=DATE:{b['Scadenza'].replace('-', '')}", f"SUMMARY:{_ics(titolo)}",
            f"DESCRIPTION:{_ics(str(b.get('Ente', '')) + ' · punteggio ' + str(b.get('Punteggio', '')) + ' · ' + str(b.get('Link bando', '')))}",
            f"URL:{b.get('Link bando', '')}",
            "BEGIN:VALARM", "TRIGGER:-P7D", "ACTION:DISPLAY", f"DESCRIPTION:{_ics(titolo)}", "END:VALARM",
            "END:VEVENT",
        ]
    righe.append("END:VCALENDAR")
    return "\r\n".join(righe)
