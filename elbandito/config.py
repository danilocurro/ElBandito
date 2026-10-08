"""Impostazioni: segreti da variabili d'ambiente, tutto il resto dal foglio.

Le chiavi API arrivano dall'ambiente (Secrets di GitHub, .env locale), mai
dal codice o dal foglio. Il profilo, i pesi e il tema stanno nella scheda
PROFILO: cambiare tema o soglie non richiede di toccare il codice.

Senza chiavi né Google, ElBandito funziona lo stesso: i dati stanno in CSV
locali e l'estrazione la fa Claude Code attraverso il server MCP.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("Europe/Rome")
RADICE = Path(__file__).resolve().parent.parent
_contatto = os.environ.get("ELBANDITO_CONTATTO", "").strip()
USER_AGENT = "ElBandito/0.2 (ricerca personale di bandi d'arte" + (f"; +{_contatto}" if _contatto else "") + ")"


def _cartella_dati() -> Path:
    """ELBANDITO_DATI se impostata; ~/.elbandito se gira come plugin; altrimenti dati/ nel repository."""
    if os.environ.get("ELBANDITO_DATI"):
        return Path(os.environ["ELBANDITO_DATI"]).expanduser()
    if os.environ.get("ELBANDITO_PLUGIN"):
        return Path.home() / ".elbandito"
    return RADICE / "dati"


def _carica_env() -> None:
    """Legge un file .env (chiave=valore) nella cartella dati o nel repository, senza sovrascrivere l'ambiente."""
    for f in (_cartella_dati() / ".env", RADICE / ".env"):
        if f.exists():
            for riga in f.read_text(encoding="utf-8").splitlines():
                if "=" in riga and not riga.lstrip().startswith("#"):
                    k, v = riga.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_carica_env()


def oggi() -> date:
    return datetime.now(FUSO).date()


def iso(d: date | None) -> str:
    return d.strftime("%Y-%m-%d") if d else ""


@dataclass
class Ambiente:
    sheet_id: str = field(default_factory=lambda: os.environ.get("ELBANDITO_SHEET_ID", ""))
    credenziali_google: str = field(default_factory=lambda: os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", ""))
    gemini_key: str = field(default_factory=lambda: os.environ.get("GEMINI_API_KEY", ""))
    anthropic_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    searxng_url: str = field(default_factory=lambda: os.environ.get("SEARXNG_URL", ""))
    cartella_dati: Path = field(default_factory=_cartella_dati)
    # "locale" = CSV in cartella_dati/foglio; "google" = il foglio Google (se c'è ELBANDITO_SHEET_ID)
    backend: str = field(default_factory=lambda: os.environ.get(
        "ELBANDITO_BACKEND", "google" if os.environ.get("ELBANDITO_SHEET_ID") else "locale"))


# Valori di partenza: usati se la riga manca in PROFILO.
PREDEFINITI = {
    "Tema": "fotografia",
    "Nome d'arte": "Artista di esempio",
    "Anno di nascita": "1990",
    "Base": "Bologna",
    "Città di riferimento": "Bologna",
    "Base lat": "44.4949",
    "Base lon": "11.3426",
    "Nazionalità": "italiana",
    "Paese": "Italia",
    "Regioni di residenza": "Emilia-Romagna",
    "Luoghi casa": "Emilia-Romagna, Bologna",
    "Etichetta casa": "vicino a casa",
    "Luoghi vicini": "",
    "Etichetta vicini": "regioni vicine",
    "Si candida come": "persona",
    "Lingue": "italiano, inglese",
    "Quota massima": "50",
    "Giorni minimi preparazione": "7",
    "Discipline piene": "fotografia, lens-based, fotografia d'autore, documentario, photography",
    "Discipline metà": "arti visive, multidisciplinare, video, cinema, visual arts",
    "Temi": "paesaggio, territorio, memoria",
    "Parole chiave": "bando fotografia, open call fotografia, premio fotografia, residenza artistica, "
    "photography open call, artist residency, photography grant, photo award",
    "Paesi UE": "Austria, Belgio, Bulgaria, Cipro, Croazia, Danimarca, Estonia, Finlandia, Francia, "
    "Germania, Grecia, Irlanda, Lettonia, Lituania, Lussemburgo, Malta, Paesi Bassi, Polonia, "
    "Portogallo, Repubblica Ceca, Romania, Slovacchia, Slovenia, Spagna, Svezia, Ungheria, "
    "Norvegia, Islanda, Svizzera, Regno Unito",
    "Peso disciplina": "25",
    "Peso tema": "5",
    "Peso geografia": "10",
    "Peso valore": "15",
    "Peso prestigio": "15",
    "Peso costo": "15",
    "Soglia avviso": "80",
    "Motore estrazione": "auto",
    "Modello estrazione": "gemini-flash-lite-latest",
    "Modello ripiego": "claude-haiku-5-5",
    "Modello ricerca": "claude-opus-5-5",
    "Motore ricerca": "agente",
    "Ricerche settimanali": "20",
}


class Profilo:
    """Le coppie Campo/Valore della scheda PROFILO, con letture tipizzate."""

    def __init__(self, righe: list[dict] | None = None):
        self.valori = dict(PREDEFINITI)
        for r in righe or []:
            campo = str(r.get("Campo", "")).strip()
            if campo:
                self.valori[campo] = str(r.get("Valore", "")).strip()

    def testo(self, campo: str, predefinito: str = "") -> str:
        return self.valori.get(campo, predefinito) or predefinito

    def lista(self, campo: str) -> list[str]:
        return [x.strip() for x in re.split(r"[,;\n]", self.testo(campo)) if x.strip()]

    def numero(self, campo: str, predefinito: float = 0.0) -> float:
        try:
            return float(self.testo(campo).replace(",", "."))
        except ValueError:
            return predefinito

    @property
    def eta(self) -> int:
        return oggi().year - int(self.numero("Anno di nascita", 1990))

    @property
    def pesi(self) -> dict[str, float]:
        nomi = ["disciplina", "tema", "geografia", "valore", "prestigio", "costo"]
        return {n: self.numero(f"Peso {n}") for n in nomi}

    def riassunto(self) -> str:
        """Profilo professionale per i prompt (mai dati personali o economici)."""
        return (
            f"Artista ({self.testo('Tema')}): {self.eta} anni, nazionalità {self.testo('Nazionalità')}, "
            f"base {self.testo('Base')}. Si candida come {self.testo('Si candida come')}.\n"
            f"Linguaggi: {', '.join(self.lista('Discipline piene'))}.\n"
            f"Temi ricorrenti: {', '.join(self.lista('Temi'))}.\n"
            f"Lingue di candidatura: {', '.join(self.lista('Lingue'))}. "
            f"Quota massima accettata: {self.numero('Quota massima'):.0f} €.\n"
            f"{self.testo('Curriculum')}"
        ).strip()
