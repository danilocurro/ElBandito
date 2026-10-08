"""Lettura e scrittura del foglio "ElBandito".

Due backend con la stessa interfaccia:
- GoogleFoglio: il foglio vero, via gspread e service account;
- FoglioLocale: file CSV in una cartella, per provare tutto senza Google.

Le colonne si trovano per nome di intestazione. Le celle viaggiano come
testo (RAW): le date restano stringhe yyyy-MM-dd, come nel gestionale.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .config import Ambiente
from .modelli import COLONNE

from .config import RADICE

CARTELLA_SEED = RADICE / "seed"


class FoglioBase:
    def leggi(self, scheda: str) -> list[dict]:
        raise NotImplementedError

    def aggiungi(self, scheda: str, righe: list[dict]) -> None:
        raise NotImplementedError

    def aggiorna(self, scheda: str, chiave_col: str, modifiche: dict[str, dict]) -> None:
        """modifiche = {valore_chiave: {colonna: nuovo_valore}}"""
        raise NotImplementedError

    def prepara(self, con_seed: bool = True) -> list[str]:
        """Crea le schede mancanti con le intestazioni e, se vuote, le riempie dal seed."""
        raise NotImplementedError


CARTELLA_PERSONALE: Path | None = None  # dati/personale: le tue righe, fuori da git


def file_seed(nome: str) -> Path:
    """Prima dati/personale/<nome>.csv (se esiste), poi seed/<nome>.csv (esempio anonimo)."""
    from .config import _cartella_dati

    personale = (CARTELLA_PERSONALE or _cartella_dati() / "personale") / f"{nome}.csv"
    return personale if personale.exists() else CARTELLA_SEED / f"{nome}.csv"


def _seed(scheda: str) -> list[dict]:
    percorso = file_seed(scheda.lower())
    if not percorso.exists():
        return []
    with percorso.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _riga(intestazioni: list[str], dati: dict) -> list:
    out = []
    for col in intestazioni:
        v = dati.get(col, "")
        if v is None:
            v = ""
        elif isinstance(v, (list, tuple)):
            v = ", ".join(str(x) for x in v)
        elif isinstance(v, dict):
            v = json.dumps(v, ensure_ascii=False)
        elif isinstance(v, bool):
            v = "sì" if v else ""
        out.append(v)
    return out


class GoogleFoglio(FoglioBase):
    def __init__(self, amb: Ambiente):
        import gspread

        if not amb.sheet_id or not amb.credenziali_google:
            raise RuntimeError("Mancano ELBANDITO_SHEET_ID o GOOGLE_SERVICE_ACCOUNT_JSON")
        cred = amb.credenziali_google
        info = json.loads(Path(cred).read_text() if not cred.lstrip().startswith("{") else cred)
        self._gc = gspread.service_account_from_dict(info)
        self._sh = self._gc.open_by_key(amb.sheet_id)
        self._cache: dict[str, list[list[str]]] = {}

    def _ws(self, scheda: str):
        return self._sh.worksheet(scheda)

    def _valori(self, scheda: str) -> list[list[str]]:
        if scheda not in self._cache:
            self._cache[scheda] = self._ws(scheda).get_all_values()
        return self._cache[scheda]

    def leggi(self, scheda: str) -> list[dict]:
        valori = self._valori(scheda)
        if not valori:
            return []
        intest = valori[0]
        return [dict(zip(intest, r + [""] * (len(intest) - len(r)))) for r in valori[1:] if any(r)]

    def aggiungi(self, scheda: str, righe: list[dict]) -> None:
        if not righe:
            return
        valori = self._valori(scheda)
        intest = valori[0] if valori else COLONNE[scheda]
        nuove = [_riga(intest, r) for r in righe]
        self._ws(scheda).append_rows(nuove, value_input_option="RAW")
        valori.extend([[str(c) for c in r] for r in nuove])

    def aggiorna(self, scheda: str, chiave_col: str, modifiche: dict[str, dict]) -> None:
        from gspread.utils import rowcol_to_a1

        if not modifiche:
            return
        valori = self._valori(scheda)
        intest = valori[0]
        ic = intest.index(chiave_col)
        lotto = []
        for n, r in enumerate(valori[1:], start=2):
            chiave = r[ic] if ic < len(r) else ""
            if chiave not in modifiche:
                continue
            for col, v in modifiche[chiave].items():
                if col not in intest:
                    continue
                j = intest.index(col)
                cella = _riga([col], {col: v})[0]
                lotto.append({"range": rowcol_to_a1(n, j + 1), "values": [[cella]]})
                while len(r) <= j:
                    r.append("")
                r[j] = str(cella)
        if lotto:
            self._ws(scheda).batch_update(lotto, value_input_option="RAW")

    def prepara(self, con_seed: bool = True) -> list[str]:
        esistenti = {ws.title for ws in self._sh.worksheets()}
        fatto = []
        for scheda, intest in COLONNE.items():
            if scheda not in esistenti:
                ws = self._sh.add_worksheet(scheda, rows=200, cols=len(intest))
                ws.append_row(intest, value_input_option="RAW")
                ws.freeze(rows=1)
                fatto.append(f"creata {scheda}")
            else:
                ws = self._ws(scheda)
                attuali = ws.row_values(1)
                mancanti = [c for c in intest if c not in attuali]
                if mancanti:
                    if ws.col_count < len(attuali) + len(mancanti):
                        ws.add_cols(len(attuali) + len(mancanti) - ws.col_count)
                    ws.update([attuali + mancanti], "A1", value_input_option="RAW")
                    fatto.append(f"{scheda}: aggiunte colonne {', '.join(mancanti)}")
            self._cache.pop(scheda, None)
            if con_seed and not self.leggi(scheda):
                semi = _seed(scheda)
                if semi:
                    self.aggiungi(scheda, semi)
                    fatto.append(f"{scheda}: {len(semi)} righe dal seed")
        return fatto


class FoglioLocale(FoglioBase):
    def __init__(self, cartella: Path):
        self.cartella = Path(cartella) / "foglio"
        self.cartella.mkdir(parents=True, exist_ok=True)

    def _file(self, scheda: str) -> Path:
        return self.cartella / f"{scheda}.csv"

    def leggi(self, scheda: str) -> list[dict]:
        p = self._file(scheda)
        if not p.exists():
            return []
        with p.open(encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def _scrivi(self, scheda: str, righe: list[dict]) -> None:
        intest = COLONNE[scheda]
        with self._file(scheda).open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(intest)
            for r in righe:
                w.writerow(_riga(intest, r))

    def aggiungi(self, scheda: str, righe: list[dict]) -> None:
        if righe:
            self._scrivi(scheda, self.leggi(scheda) + righe)

    def aggiorna(self, scheda: str, chiave_col: str, modifiche: dict[str, dict]) -> None:
        righe = self.leggi(scheda)
        for r in righe:
            if r.get(chiave_col) in modifiche:
                r.update(modifiche[r[chiave_col]])
        self._scrivi(scheda, righe)

    def prepara(self, con_seed: bool = True) -> list[str]:
        fatto = []
        for scheda in COLONNE:
            if not self._file(scheda).exists():
                self._scrivi(scheda, _seed(scheda) if con_seed else [])
                fatto.append(f"creata {scheda}")
        return fatto


def apri(amb: Ambiente) -> FoglioBase:
    if amb.backend == "locale":
        return FoglioLocale(amb.cartella_dati)
    return GoogleFoglio(amb)
