"""Il giro completo: leggi le fonti → estrai → deduplica → punteggio → scrivi → registra.

Le notifiche (digest, avvisi, promemoria) partono dalla web app Apps Script,
che legge il foglio: così tutte le email arrivano da un solo posto.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import timedelta

from . import dedup, ricerca_ai
from .archivio import Archivio, hash_testo
from .config import Ambiente, Profilo, iso, oggi
from .connettori import CONNETTORI, Pagina, da_link
from .estrazione import DaEstrarre, Estrattore, SchedaVerificata, verifica_tutte
from .foglio import FoglioBase, apri
from .punteggio import valuta
from .rete import AccessoNegato, Rete

log = logging.getLogger(__name__)

STATI_CHIUSI = {"Scartato", "Archiviato", "Vinto", "Non selezionato"}


@dataclass
class Resoconto:
    tipo: str
    fonti_lette: int = 0
    fonti_errore: list[str] = field(default_factory=list)
    pagine: int = 0
    schede: int = 0
    nuovi: int = 0
    aggiornati: int = 0
    in_coda: int = 0
    domini: list[str] = field(default_factory=list)
    note: list[str] = field(default_factory=list)
    errori: list[str] = field(default_factory=list)

    def riga_log(self, durata: float) -> dict:
        return {
            "Data": iso(oggi()), "Tipo giro": self.tipo, "Fonti lette": self.fonti_lette,
            "Fonti in errore": ", ".join(self.fonti_errore), "Pagine nuove": self.pagine,
            "Schede estratte": self.schede, "Bandi nuovi": self.nuovi, "Bandi aggiornati": self.aggiornati,
            "In coda": self.in_coda, "Domini suggeriti": ", ".join(self.domini), "Note": " | ".join(self.note), "Errori": " | ".join(self.errori)[:2000],
            "Durata (s)": round(durata),
        }


def da_leggere(fonte: dict, tipo: str) -> bool:
    if str(fonte.get("Attiva", "")).strip().lower() not in ("sì", "si", "x", "true", "1"):
        return False
    if fonte.get("Connettore") == "ai_search" or fonte.get("Connettore") not in CONNETTORI:
        return False
    freq = str(fonte.get("Frequenza", "giornaliera")).lower()
    if tipo == "settimanale":
        return True
    if freq.startswith("sett"):
        return oggi().weekday() == 0
    if freq.startswith("mens"):
        return oggi().weekday() == 0 and oggi().day <= 7
    return True


def prossimo_id(righe: list[dict]) -> int:
    numeri = [int(m.group(1)) for r in righe if (m := re.match(r"B(\d+)", str(r.get("ID", ""))))]
    return max(numeri, default=0) + 1


def riga_da_scheda(v: SchedaVerificata, pagina: Pagina) -> dict:
    s = v.scheda
    anno = v.scadenza.year if v.scadenza else oggi().year
    return {
        "Impronta": dedup.impronta(s.ente, s.titolo, anno),
        "Titolo": s.titolo, "Ente": s.ente, "Tipo": s.tipo, "Disciplina": s.disciplina,
        "Temi": ", ".join(s.temi), "Paese": s.paese, "Regione": s.regione,
        "Città": s.citta or ("online" if s.online else ""),
        "Scadenza": iso(v.scadenza), "Scadenza confermata": "sicura" if v.confermata else "da verificare",
        "Fuso scadenza": s.fuso_scadenza, "Apertura": s.apertura, "Date attività": s.date_attivita,
        "Quota iscrizione": "" if s.quota_iscrizione_eur is None else (
            int(s.quota_iscrizione_eur) if float(s.quota_iscrizione_eur).is_integer() else s.quota_iscrizione_eur),
        "Valore": s.valore, "Eleggibilità": s.eleggibilita,
        "Materiali richiesti": "; ".join(s.materiali_richiesti),
        "Lingua candidatura": ", ".join(s.lingue_candidatura),
        "Link bando": pagina.url, "Link candidatura": s.link_candidatura, "Fonte": pagina.fonte, "N. fonti": 1,
        "Estratto": v.estratto[:1500], "Ricorrente": s.ricorrente, "Edizione": s.edizione or "",
    }


def _applica_esito(riga: dict, v: SchedaVerificata, profilo: Profilo, enti: list[dict]) -> None:
    esito = valuta(v, profilo, enti, int(riga.get("N. fonti") or 1))
    riga.update({
        "Punteggio": esito.punteggio, "Dettaglio punteggio": esito.dettaglio,
        "Motivazione": esito.motivazione, "Rischi": esito.rischi, "Esclusione": esito.esclusione,
    })


def geocodifica(rete: Rete, arch: Archivio, citta: str, paese: str) -> tuple[float, float] | None:
    luogo = ", ".join(x for x in (citta, paese) if x and x != "online")
    if not luogo:
        return None
    nota = arch.geo(luogo)
    if nota is not False:
        return nota  # già cercato (anche senza esito)
    coord = None
    try:
        r = rete.get("https://nominatim.openstreetmap.org/search",
                     params={"q": luogo, "format": "json", "limit": 1, "accept-language": "it"})
        dati = r.json()
        if dati:
            coord = (float(dati[0]["lat"]), float(dati[0]["lon"]))
    except Exception as e:  # la mappa è un di più: un errore qui non ferma il giro
        log.info("Geocodifica fallita per %s: %s", luogo, e)
    arch.salva_geo(luogo, coord)
    return coord


class Giro:
    def __init__(self, tipo: str, amb: Ambiente | None = None, foglio: FoglioBase | None = None):
        self.tipo = tipo
        self.amb = amb or Ambiente()
        self.foglio = foglio or apri(self.amb)
        self.profilo = Profilo(self.foglio.leggi("PROFILO"))
        self.enti = self.foglio.leggi("ENTI")
        self.bandi = self.foglio.leggi("BANDI")
        self.arch = Archivio(self.amb.cartella_dati / "archivio.sqlite")
        self.rete = Rete()
        self.estrattore = Estrattore(self.amb, self.profilo)
        self.res = Resoconto(tipo)
        self.nuove: list[dict] = []
        self.modifiche: dict[str, dict] = {}
        self._id = prossimo_id(self.bandi)
        self._fonti_bandi: dict[str, int] = {}
        self.solo: set[str] | None = None  # ID di FONTI da leggere (giro mirato), ignorando la frequenza

    # --- singola pagina ---
    def elabora(self, pagina: Pagina) -> int:
        try:
            verificate = self.estrattore.estrai(pagina)
        except DaEstrarre:
            self.arch.accoda(pagina)
            self.arch.segna(pagina.url, pagina.fonte, pagina.strutturato.get("hash") or hash_testo(pagina.testo))
            self.res.in_coda += 1
            return 0
        except Exception as e:
            self.res.errori.append(f"estrazione {pagina.url}: {e}")
            return 0
        self.res.pagine += 1
        self.arch.segna(pagina.url, pagina.fonte, pagina.strutturato.get("hash") or hash_testo(pagina.testo))
        return self.registra_verificate(pagina, verificate)

    def registra_verificate(self, pagina: Pagina, verificate: list[SchedaVerificata]) -> int:
        self.res.schede += len(verificate)
        portati = 0
        for v in verificate:
            riga = riga_da_scheda(v, pagina)
            self.arch.conserva(pagina.fonte, pagina.url, riga["Impronta"], v.scheda.model_dump())
            if self._registra(riga, v):
                portati += 1
        self._fonti_bandi[pagina.fonte] = self._fonti_bandi.get(pagina.fonte, 0) + portati
        return portati

    def _registra(self, riga: dict, v: SchedaVerificata) -> bool:
        """True se è un bando nuovo."""
        doppio = dedup.trova(riga, self.bandi + self.nuove)
        adesso = iso(oggi())
        if doppio is None:
            riga.update({
                "ID": f"B{self._id:04d}", "Stato": "Nuovo", "Prossima azione": "Valutare",
                "Data prossima azione": iso(oggi() + timedelta(days=3)),
                "Trovato il": adesso, "Aggiornato il": adesso, "Storico": f"{adesso} trovato ({riga['Fonte']})",
            })
            coord = geocodifica(self.rete, self.arch, riga["Città"], riga["Paese"])
            if coord:
                riga["Lat"], riga["Lon"] = round(coord[0], 5), round(coord[1], 5)
            self._id += 1
            _applica_esito(riga, v, self.profilo, self.enti)
            self.nuove.append(riga)
            self.res.nuovi += 1
            return True

        # già noto: unisci fonti e link; nuova edizione se la scadenza è di un anno dopo
        mod = {
            "Fonte": dedup.unisci_fonti(doppio.get("Fonte", ""), riga["Fonte"]),
            "Link bando": dedup.link_migliore(doppio.get("Link bando", ""), riga["Link bando"]),
            "Aggiornato il": adesso,
        }
        mod["N. fonti"] = len([x for x in mod["Fonte"].split(",") if x.strip()])
        vecchia = str(doppio.get("Scadenza", ""))
        if riga["Scadenza"] and (not vecchia or riga["Scadenza"][:4] > vecchia[:4]):
            nuova_edizione = bool(vecchia)
            for col in ("Scadenza", "Scadenza confermata", "Apertura", "Date attività", "Quota iscrizione",
                        "Valore", "Eleggibilità", "Materiali richiesti", "Estratto", "Impronta"):
                if riga.get(col) not in ("", None):
                    mod[col] = riga[col]
            if nuova_edizione:
                mod["Ricorrente"] = "sì"
                mod["Edizione"] = (int(doppio["Edizione"]) + 1) if str(doppio.get("Edizione", "")).isdigit() else ""
                if doppio.get("Stato") in STATI_CHIUSI | {"In attesa edizione"}:
                    mod.update({"Stato": "Nuovo", "Prossima azione": "Valutare la nuova edizione",
                                "Data prossima azione": iso(oggi() + timedelta(days=3))})
                mod["Storico"] = (doppio.get("Storico", "") + f"\n{adesso} nuova edizione").strip()
        elif doppio.get("Scadenza confermata") != "sicura" and riga["Scadenza confermata"] == "sicura":
            mod.update({"Scadenza": riga["Scadenza"], "Scadenza confermata": "sicura", "Estratto": riga["Estratto"]})
        doppio.update(mod)
        _applica_esito(doppio, v, self.profilo, self.enti)
        for col in ("Punteggio", "Dettaglio punteggio", "Motivazione", "Rischi", "Esclusione"):
            mod[col] = doppio[col]
        if any(doppio is r for r in self.nuove):
            return False
        self.modifiche.setdefault(doppio["ID"], {}).update(mod)
        self.res.aggiornati += 1
        return False

    # --- fonti fisse ---
    def leggi_fonti(self) -> None:
        mod_fonti: dict[str, dict] = {}
        for fonte in self.foglio.leggi("FONTI"):
            if self.solo is not None:
                if fonte.get("ID") not in self.solo or fonte.get("Connettore") not in CONNETTORI:
                    continue
            elif not da_leggere(fonte, self.tipo):
                continue
            conn = CONNETTORI[fonte["Connettore"]]
            self.res.fonti_lette += 1
            prima = self.res.nuovi
            try:
                pagine = conn(fonte, self.rete, self.arch, self.profilo)
                for p in pagine:
                    self.elabora(p)
                esito, errori = f"ok · {len(pagine)} pagine, {self.res.nuovi - prima} nuovi", 0
            except AccessoNegato as e:
                esito, errori = f"accesso negato: {e}", int(fonte.get("Errori consecutivi") or 0) + 1
            except Exception as e:
                log.exception("Fonte %s", fonte.get("Nome"))
                esito, errori = f"errore: {type(e).__name__}: {e}"[:300], int(fonte.get("Errori consecutivi") or 0) + 1
            if errori:
                self.res.fonti_errore.append(fonte.get("Nome", fonte["ID"]))
            m = {"Ultima lettura": iso(oggi()), "Ultimo esito": esito, "Errori consecutivi": errori}
            portati = self._fonti_bandi.get(fonte["ID"], 0)
            if portati:
                m["Bandi portati"] = int(fonte.get("Bandi portati") or 0) + portati
                m["Ultimo bando"] = iso(oggi())
            mod_fonti[fonte["ID"]] = m
            self.arch.db.commit()
        self.foglio.aggiorna("FONTI", "ID", mod_fonti)

    # --- ricerca AI ---
    def ricerca(self) -> None:
        if self.profilo.testo("Motore ricerca", "agente").lower() == "agente":
            self.res.note.append("ricerca web affidata a Claude Code (skill elbandito-ricerca)")
            return
        noti = [f"{b.get('Titolo')} — {b.get('Ente')}" for b in self.bandi if b.get("Stato") != "Archiviato"]
        try:
            segnalazioni = ricerca_ai.cerca(self.amb, self.profilo, noti, self.rete)
        except Exception as e:
            self.res.errori.append(f"ricerca AI: {e}")
            return
        conosciuti = {b.get("Link bando") for b in self.bandi}
        for s in segnalazioni:
            if s.url in conosciuti or not self.arch.nuovo(s.url):
                continue
            try:
                pagina = da_link(s.url, self.rete)
                pagina.fonte = "ai_search"
            except AccessoNegato:
                # sito chiuso ai robot: si tiene la segnalazione, ma resterà "da verificare"
                pagina = Pagina(url=s.url, titolo=s.titolo, fonte="ai_search",
                                testo=f"{s.titolo}\nEnte: {s.ente}\nScadenza: {s.scadenza}\n{s.nota}")
            except Exception as e:
                self.res.errori.append(f"ricerca AI {s.url}: {e}")
                continue
            prima = len(self.nuove)
            self.elabora(pagina)
            for r in self.nuove[prima:]:
                self.arch.nota_dominio(dedup.dominio(r["Link bando"]), float(r.get("Punteggio") or 0))
        noti_domini = {dedup.dominio(f.get("URL", "")) for f in self.foglio.leggi("FONTI")}
        self.res.domini = self.arch.domini_promettenti(noti_domini)

    # --- chiusura ---
    def scrivi(self, inizio: float) -> None:
        self.foglio.aggiungi("BANDI", self.nuove)
        self.foglio.aggiorna("BANDI", "ID", self.modifiche)
        self.foglio.aggiungi("LOG", [self.res.riga_log(time.monotonic() - inizio)])
        self.arch.chiudi()

    def elabora_coda(self, limite: int = 40) -> int:
        """Riprova le pagine in coda con il motore API (se ora c'è una chiave). Restano in coda se no."""
        if self.estrattore.motore == "agente" or not (self.amb.gemini_key or self.amb.anthropic_key):
            return 0
        fatte = 0
        for voce in self.arch.in_coda(limite):
            pagina = Pagina(url=voce["url"], titolo=voce["titolo"], testo=voce["testo"], fonte=voce["fonte"],
                            strutturato=json.loads(voce["strutturato"] or "{}"))
            try:
                verificate = self.estrattore.estrai(pagina)
            except DaEstrarre:
                break
            except Exception as e:
                self.res.errori.append(f"estrazione {pagina.url}: {e}")
                continue
            self.res.pagine += 1
            self.registra_verificate(pagina, verificate)
            self.arch.togli(pagina.url)
            fatte += 1
        if fatte:
            self.res.note.append(f"estratte {fatte} pagine rimaste in coda")
        return fatte

    def esegui(self) -> Resoconto:
        inizio = time.monotonic()
        self.elabora_coda()
        self.leggi_fonti()
        if self.tipo == "settimanale":
            self.ricerca()
        self.scrivi(inizio)
        return self.res


def aggiungi_da_link(url: str, amb: Ambiente | None = None) -> Resoconto:
    """Pulsante "aggiungi da link": un post, una pagina, un PDF incollato a mano."""
    g = Giro("link", amb)
    inizio = time.monotonic()
    try:
        pagina = da_link(url, g.rete)
    except AccessoNegato as e:
        g.res.errori.append(str(e))
    else:
        if g.elabora(pagina) == 0 and not g.modifiche:
            g.res.errori.append("Nessun bando aperto riconosciuto nella pagina")
    g.scrivi(inizio)
    return g.res


def scheda_da_riga(b: dict):
    """Ricostruzione approssimata di una scheda dalle colonne del foglio (se manca lo storico grezzo)."""
    from .modelli import TIPI, SchedaEstratta

    testo_valore = re.sub(r"(?<=\d)[.,'](?=\d{3}\b)", "", str(b.get("Valore", "")))  # 32.700 → 32700
    valore = re.findall(r"\d+(?:[.,]\d+)?", testo_valore)
    quota = str(b.get("Quota iscrizione", "")).replace(",", ".")
    return SchedaEstratta(
        titolo=b.get("Titolo", ""), ente=b.get("Ente", ""),
        tipo=b.get("Tipo") if b.get("Tipo") in TIPI else "altro", disciplina=b.get("Disciplina", ""),
        temi=[t.strip() for t in str(b.get("Temi", "")).split(",") if t.strip()],
        paese=b.get("Paese", ""), regione=b.get("Regione", ""),
        citta="" if b.get("Città") == "online" else b.get("Città", ""), online=b.get("Città") == "online",
        quota_iscrizione_eur=float(quota) if re.fullmatch(r"\d+(\.\d+)?", quota) else None,
        valore=b.get("Valore", ""), valore_eur=max((float(v.replace(",", ".")) for v in valore), default=None),
        include_mostra=bool(re.search(r"mostra|esposizion|catalogo|pubblicazion", str(b.get("Valore", "")), re.I)),
        copre_alloggio=bool(re.search(r"alloggio|accommodation", str(b.get("Valore", "")), re.I)),
        copre_viaggio=bool(re.search(r"viaggio|travel", str(b.get("Valore", "")), re.I)),
        eleggibilita=b.get("Eleggibilità", ""),
        lingue_candidatura=[x.strip() for x in str(b.get("Lingua candidatura", "")).split(",") if x.strip()],
        date_attivita=b.get("Date attività", ""),
    )


def ricalcola(amb: Ambiente | None = None) -> int:
    """Ricalcola punteggi ed esclusioni dopo un cambio di PROFILO o pesi.

    Usa la scheda completa dallo storico grezzo; se manca (archivio perso,
    righe aggiunte a mano) la ricostruisce dalle colonne e conserva le
    esclusioni che la ricostruzione non può rivedere (età, solo enti…).
    """
    from .modelli import SchedaEstratta
    from datetime import date

    g = Giro("ricalcolo", amb)
    grezzi = {imp: json.loads(s) for imp, s in g.arch.db.execute("SELECT impronta, scheda FROM grezzi ORDER BY id")}
    n = 0
    for b in g.bandi:
        if not b.get("Titolo"):
            continue
        completa = b.get("Impronta") in grezzi
        scheda = SchedaEstratta.model_validate(grezzi[b["Impronta"]]) if completa else scheda_da_riga(b)
        scad = date.fromisoformat(b["Scadenza"]) if b.get("Scadenza") else None
        v = SchedaVerificata(scheda, scad, b.get("Scadenza confermata") == "sicura", b.get("Estratto", ""))
        esclusione_prima = b.get("Esclusione", "")
        _applica_esito(b, v, g.profilo, g.enti)
        if not completa and esclusione_prima:
            nuove = [m for m in b["Esclusione"].split("; ") if m]
            vecchie = [m for m in esclusione_prima.split("; ")
                       if m and not m.startswith(("Quota", "Lingua", "Scadenza troppo"))]  # queste si rivalutano
            b["Esclusione"] = "; ".join(dict.fromkeys(vecchie + nuove))
        g.modifiche[b["ID"]] = {c: b[c] for c in ("Punteggio", "Dettaglio punteggio", "Motivazione", "Rischi", "Esclusione")}
        n += 1
    g.foglio.aggiorna("BANDI", "ID", g.modifiche)
    g.arch.chiudi()
    return n


def approfondisci(id_bando: str, amb: Ambiente | None = None) -> str:
    """"Cerca a fondo" dalla web app: scrive l'indagine nella colonna Approfondimento."""
    amb = amb or Ambiente()
    foglio = apri(amb)
    profilo = Profilo(foglio.leggi("PROFILO"))
    bando = next((b for b in foglio.leggi("BANDI") if b.get("ID") == id_bando), None)
    if bando is None:
        raise SystemExit(f"Bando {id_bando} non trovato")
    testo = ricerca_ai.approfondisci(amb, profilo, bando)
    foglio.aggiorna("BANDI", "ID", {id_bando: {"Approfondimento": testo, "Aggiornato il": iso(oggi())}})
    return testo


def salva_estratte(url: str, schede: list[dict], amb: Ambiente | None = None) -> dict:
    """Riceve le schede estratte da Claude Code per una pagina in coda.

    Le schede passano dalle stesse difese dell'estrazione via API: schema
    Pydantic, citazioni ritrovate nel testo, date con dateparser, deduplica.
    Una lista vuota significa "la pagina non contiene bandi aperti".
    """
    from .modelli import SchedaEstratta

    g = Giro("agente", amb)
    inizio = time.monotonic()
    voce = g.arch.da_coda(url)
    if voce:
        pagina = Pagina(url=voce["url"], titolo=voce["titolo"], testo=voce["testo"], fonte=voce["fonte"],
                        strutturato=json.loads(voce["strutturato"] or "{}"))
    else:
        pagina = da_link(url, g.rete)  # non era in coda: la scarico ora per poter verificare le citazioni
    errori, valide = [], []
    for i, d in enumerate(schede or []):
        try:
            valide.append(SchedaEstratta.model_validate(d))
        except Exception as e:
            errori.append(f"scheda {i + 1}: {e}".splitlines()[0][:300])
    verificate = verifica_tutte(valide, pagina)
    prima = len(g.nuove)
    g.registra_verificate(pagina, verificate)
    g.res.pagine = 1
    g.res.errori.extend(errori)
    g.arch.togli(url)
    g.scrivi(inizio)
    toccati = g.nuove[prima:] + [b for b in g.bandi if b.get("ID") in g.modifiche]
    return {
        "nuovi": g.res.nuovi, "aggiornati": g.res.aggiornati,
        "scartate": len(valide) - len(verificate),  # scadenza passata
        "errori": errori,
        "bandi": [{k: b.get(k) for k in ("ID", "Titolo", "Scadenza", "Scadenza confermata", "Punteggio",
                                         "Motivazione", "Esclusione")} for b in toccati],
    }


def accoda_link(url: str, amb: Ambiente | None = None) -> dict:
    """Scarica una pagina e la mette in coda per Claude Code; restituisce il testo da estrarre."""
    g = Giro("link", amb)
    pagina = da_link(url, g.rete)
    g.arch.accoda(pagina)
    g.arch.segna(pagina.url, "manuale", hash_testo(pagina.testo))
    g.arch.chiudi()
    return {"url": pagina.url, "titolo": pagina.titolo, "testo": pagina.testo[:20000],
            "json_ld": pagina.strutturato.get("json_ld", [])}
