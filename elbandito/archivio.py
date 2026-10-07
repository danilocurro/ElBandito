"""Archivio interno SQLite: cosa è già stato letto, storico grezzo, cache geografica.

Su GitHub Actions il file sta in cache tra un giro e l'altro. Se la cache
si perde non succede nulla di grave: la deduplica sul foglio (impronta)
impedisce i doppioni, si rilegge solo qualche pagina in più.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from .config import iso, oggi

SCHEMA = """
CREATE TABLE IF NOT EXISTS visti (
  url TEXT PRIMARY KEY, fonte TEXT, hash TEXT, primo TEXT, ultimo TEXT
);
CREATE TABLE IF NOT EXISTS grezzi (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, fonte TEXT, url TEXT, impronta TEXT, scheda TEXT
);
CREATE TABLE IF NOT EXISTS geo (luogo TEXT PRIMARY KEY, lat REAL, lon REAL);
CREATE TABLE IF NOT EXISTS domini (dominio TEXT, data TEXT, punteggio REAL);
CREATE TABLE IF NOT EXISTS coda (
  url TEXT PRIMARY KEY, fonte TEXT, titolo TEXT, testo TEXT, strutturato TEXT, data TEXT
);
"""


def hash_testo(testo: str) -> str:
    return hashlib.sha256(" ".join(testo.split()).encode("utf-8")).hexdigest()[:16]


class Archivio:
    def __init__(self, percorso: Path):
        percorso.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(percorso)
        self.db.executescript(SCHEMA)

    def chiudi(self) -> None:
        self.db.commit()
        self.db.close()

    # --- pagine già viste ---
    def nuovo(self, url: str) -> bool:
        return self.db.execute("SELECT 1 FROM visti WHERE url=?", (url,)).fetchone() is None

    def cambiato(self, url: str, h: str) -> bool:
        r = self.db.execute("SELECT hash FROM visti WHERE url=?", (url,)).fetchone()
        return r is None or r[0] != h

    def segna(self, url: str, fonte: str, h: str = "") -> None:
        d = iso(oggi())
        self.db.execute(
            "INSERT INTO visti(url,fonte,hash,primo,ultimo) VALUES(?,?,?,?,?) "
            "ON CONFLICT(url) DO UPDATE SET hash=excluded.hash, ultimo=excluded.ultimo",
            (url, fonte, h, d, d),
        )

    # --- storico grezzo ---
    def conserva(self, fonte: str, url: str, impronta: str, scheda: dict) -> None:
        self.db.execute(
            "INSERT INTO grezzi(data,fonte,url,impronta,scheda) VALUES(?,?,?,?,?)",
            (iso(oggi()), fonte, url, impronta, json.dumps(scheda, ensure_ascii=False)),
        )

    # --- geocodifica ---
    def geo(self, luogo: str) -> tuple[float, float] | None | bool:
        r = self.db.execute("SELECT lat, lon FROM geo WHERE luogo=?", (luogo,)).fetchone()
        if r is None:
            return False  # mai cercato
        return None if r[0] is None else (r[0], r[1])

    def salva_geo(self, luogo: str, coord: tuple[float, float] | None) -> None:
        lat, lon = coord if coord else (None, None)
        self.db.execute("INSERT OR REPLACE INTO geo VALUES(?,?,?)", (luogo, lat, lon))

    # --- domini scoperti dalla ricerca AI ---
    def nota_dominio(self, dominio: str, punteggio: float) -> None:
        self.db.execute("INSERT INTO domini VALUES(?,?,?)", (dominio, iso(oggi()), punteggio))

    def domini_promettenti(self, noti: set[str], minimo: int = 3) -> list[str]:
        righe = self.db.execute(
            "SELECT dominio, COUNT(*), AVG(punteggio) FROM domini GROUP BY dominio "
            "HAVING COUNT(*) >= ? AND AVG(punteggio) >= 50 ORDER BY COUNT(*) DESC",
            (minimo,),
        ).fetchall()
        return [d for d, _, _ in righe if d not in noti]

    # --- coda per l'estrazione fatta da Claude Code ---
    def accoda(self, pagina) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO coda VALUES(?,?,?,?,?,?)",
            (pagina.url, pagina.fonte, pagina.titolo, pagina.testo,
             json.dumps(pagina.strutturato, ensure_ascii=False), iso(oggi())),
        )

    def in_coda(self, limite: int = 5) -> list[dict]:
        righe = self.db.execute(
            "SELECT url, fonte, titolo, testo, strutturato, data FROM coda ORDER BY data, rowid LIMIT ?", (limite,)
        ).fetchall()
        return [dict(zip(("url", "fonte", "titolo", "testo", "strutturato", "data"), r)) for r in righe]

    def quanti_in_coda(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM coda").fetchone()[0]

    def da_coda(self, url: str) -> dict | None:
        r = self.db.execute("SELECT url, fonte, titolo, testo, strutturato FROM coda WHERE url=?", (url,)).fetchone()
        return dict(zip(("url", "fonte", "titolo", "testo", "strutturato"), r)) if r else None

    def togli(self, url: str) -> None:
        self.db.execute("DELETE FROM coda WHERE url=?", (url,))
