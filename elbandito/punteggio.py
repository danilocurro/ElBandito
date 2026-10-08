"""Match col profilo: filtri rigidi che escludono + punteggio 0-100 che ordina.

Ogni bando porta il perché: il dettaglio per componente, una frase di
motivazione e i rischi. I pesi stanno in PROFILO e si cambiano dal foglio.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from .config import Profilo, oggi
from .dedup import normalizza
from .estrazione import SchedaVerificata

LINGUE_EQUIVALENTI = {
    "italiano": {"italiano", "italian", "ita", "it"},
    "inglese": {"inglese", "english", "eng", "en"},
    "francese": {"francese", "french", "fr"},
    "spagnolo": {"spagnolo", "spanish", "es"},
    "tedesco": {"tedesco", "german", "de"},
}
APERTI = re.compile(r"ital|europ|\bue\b|\beu\b|tutt|any|all |internazional|international|worldwide|open to all", re.I)


@dataclass
class Esito:
    punteggio: int
    dettaglio: dict = field(default_factory=dict)
    motivazione: str = ""
    rischi: str = ""
    esclusione: str = ""


def _contiene(testo: str, voci: list[str]) -> list[str]:
    t = normalizza(testo)
    return [v for v in voci if normalizza(v) and re.search(rf"\b{re.escape(normalizza(v))}", t)]


def _lingue_ok(lingue_bando: list[str], lingue_profilo: list[str]) -> bool:
    if not lingue_bando:
        return True
    mie = set()
    for l in lingue_profilo:
        mie |= LINGUE_EQUIVALENTI.get(l.lower(), {l.lower()})
    return any(l.strip().lower() in mie for l in lingue_bando)


def filtri_rigidi(v: SchedaVerificata, profilo: Profilo) -> str:
    s = v.scheda
    motivi = []
    if v.scadenza:
        giorni = (v.scadenza - oggi()).days
        if giorni < profilo.numero("Giorni minimi preparazione", 7):
            motivi.append(f"Scadenza troppo vicina ({giorni} giorni)")
    eta = profilo.eta
    if s.eta_max and eta > s.eta_max:
        motivi.append(f"Limite d'età: fino a {s.eta_max} anni")
    if s.eta_min and eta < s.eta_min:
        motivi.append(f"Età minima {s.eta_min} anni")
    if s.nazionalita_ammesse and not any(APERTI.search(n) for n in s.nazionalita_ammesse):
        motivi.append(f"Nazionalità: {', '.join(s.nazionalita_ammesse)}")
    if s.residenza_richiesta:
        miei = profilo.lista("Regioni di residenza") + profilo.lista("Base") + [profilo.testo("Paese")]
        if not _contiene(s.residenza_richiesta, miei) and not APERTI.search(s.residenza_richiesta):
            motivi.append(f"Richiede residenza: {s.residenza_richiesta}")
    if s.solo_enti and profilo.testo("Si candida come").lower().startswith("persona"):
        motivi.append("Riservato a enti, associazioni o imprese")
    massimo = profilo.numero("Quota massima", 50)
    if s.quota_iscrizione_eur and s.quota_iscrizione_eur > massimo:
        motivi.append(f"Quota {s.quota_iscrizione_eur:.0f} € oltre la soglia di {massimo:.0f} €")
    if (s.quota_iscrizione_eur or 0) > 0 and not (s.valore_eur or 0) and not (
        s.include_mostra or s.copre_viaggio or s.copre_alloggio
    ):
        motivi.append("Call a pagamento senza premio né esposizione")
    if not _lingue_ok(s.lingue_candidatura, profilo.lista("Lingue")):
        motivi.append(f"Lingua di candidatura: {', '.join(s.lingue_candidatura)}")
    return "; ".join(motivi)


def _prestigio(ente: str, enti: list[dict]) -> tuple[float, str]:
    n = normalizza(ente)
    if not n:
        return 0.0, ""
    for e in enti:
        # il nome noto deve comparire per parole intere nell'ente del bando ("Fondazione CRT Torino"),
        # o i due nomi devono essere quasi identici: "On the Move" non è "Cortona On The Move"
        ne = normalizza(e.get("Nome", "").split("–")[0])
        if ne and (re.search(rf"(?<!\w){re.escape(ne)}(?!\w)", n) or fuzz.ratio(n, ne) >= 90):
            livello = str(e.get("Livello", "")).strip()
            return {"1": 1.0, "2": 0.7, "3": 0.45}.get(livello, 0.5), e.get("Nome", "")
    return 0.0, ""


def _geografia(v: SchedaVerificata, profilo: Profilo) -> tuple[float, str]:
    """Casa > luoghi vicini > paese > Europa > resto del mondo. I luoghi stanno in PROFILO."""
    s = v.scheda
    luogo = normalizza(f"{s.citta} {s.regione} {s.paese}")
    if s.online and not luogo:
        return 0.5, "online"
    if _contiene(luogo, profilo.lista("Luoghi casa")):
        return 1.0, profilo.testo("Etichetta casa", "vicino a casa")
    if _contiene(luogo, profilo.lista("Luoghi vicini")):
        return 0.8, profilo.testo("Etichetta vicini", "regioni vicine")
    paese = normalizza(profilo.testo("Paese", "Italia"))
    if (paese and paese in luogo) or (paese == "italia" and re.search(r"\bitaly\b", luogo)) or (s.regione and not s.paese):
        return 0.6, profilo.testo("Paese", "Italia")
    if _contiene(luogo, profilo.lista("Paesi UE")) or re.search(
            r"\b(europ|unione europea|france|germany|spain|greece|portugal|netherlands|belgium|ireland)\b", luogo):
        return 0.4, "Europa"
    if luogo:
        return 0.2, s.paese or "estero"
    return 0.3, ""


def _maiuscola(s: str) -> str:
    return s[:1].upper() + s[1:]


def valuta(v: SchedaVerificata, profilo: Profilo, enti: list[dict], n_fonti: int = 1) -> Esito:
    s = v.scheda
    testo = " ".join([s.titolo, s.disciplina, " ".join(s.temi), s.valore, s.eleggibilita])
    pesi = profilo.pesi
    frazioni: dict[str, float] = {}
    note: list[str] = []
    rischi: list[str] = []

    # Disciplina
    if _contiene(f"{s.disciplina} {s.titolo}", profilo.lista("Discipline piene")):
        frazioni["disciplina"] = 1.0
        note.append("fotografia esplicita")
    elif _contiene(s.disciplina, profilo.lista("Discipline metà")):
        frazioni["disciplina"] = 0.5
    else:
        frazioni["disciplina"] = 0.0

    # Tema (parole chiave; gli embedding si possono aggiungere qui)
    temi = _contiene(testo, profilo.lista("Temi"))
    frazioni["tema"] = min(1.0, len(temi) / 2) if temi else (0.3 if not s.temi else 0.0)
    if temi:
        note.append("tema " + " e ".join(temi[:2]))

    # Geografia
    frazioni["geografia"], dove = _geografia(v, profilo)
    if dove and frazioni["geografia"] >= 0.6:
        note.append(dove)

    # Valore
    val = s.valore_eur or 0
    frazione = min(0.7, 0.7 * math.log10(1 + val) / math.log10(1 + 5000)) if val else 0.0
    frazione += 0.1 * s.copre_viaggio + 0.1 * s.copre_alloggio + 0.1 * s.include_mostra
    frazioni["valore"] = min(1.0, frazione)
    if val >= 1000:
        note.append(f"valore {val:,.0f} €".replace(",", "."))
    if s.copre_alloggio:
        note.append("alloggio coperto")

    # Prestigio: nomi noti + quante fonti ne parlano
    pr, nome = _prestigio(s.ente, enti)
    pr = min(1.0, pr + (0.15 if n_fonti >= 2 else 0) + (0.15 if n_fonti >= 3 else 0))
    frazioni["prestigio"] = pr if pr else 0.2
    if nome:
        note.append(f"ente noto ({nome})")

    # Costo
    q = s.quota_iscrizione_eur
    massimo = profilo.numero("Quota massima", 50) or 50
    if q is None:
        frazioni["costo"] = 0.6
        rischi.append("Quota non indicata")
    elif q == 0:
        frazioni["costo"] = 1.0
        note.append("gratuito")
    else:
        frazioni["costo"] = max(0.0, 1 - q / (massimo * 1.5))

    totale = sum(pesi.values()) or 1
    punteggio = round(sum(frazioni[k] * pesi.get(k, 0) for k in frazioni) / totale * 100)

    if not v.confermata:
        rischi.append("Scadenza o requisiti da verificare sul sito")
    if s.lingue_candidatura and not _lingue_ok(s.lingue_candidatura, ["italiano"]):
        rischi.append(f"Candidatura in {', '.join(s.lingue_candidatura)}")
    if s.residenza_richiesta:
        rischi.append(f"Residenza: {s.residenza_richiesta}")
    if s.date_attivita and s.tipo == "residenza":
        rischi.append(f"Presenza richiesta: {s.date_attivita}")

    return Esito(
        punteggio=punteggio,
        dettaglio={k: round(f * pesi.get(k, 0), 1) for k, f in frazioni.items()},
        motivazione=_maiuscola(" · ".join(note[:4])),
        rischi="; ".join(rischi),
        esclusione=filtri_rigidi(v, profilo),
    )
