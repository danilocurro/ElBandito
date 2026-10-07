"""Riga di comando: python -m elbandito <comando>.

  configura     questionario guidato per il tuo profilo (temi, luoghi, quota, pesi)
  demo          prepara il foglio locale con 9 bandi d'esempio (prova senza chiavi)
  dashboard     apre l'interfaccia nel browser (http://127.0.0.1:8787)
  mcp           server MCP per Claude Code (stdio)
  coda          quante pagine aspettano l'estrazione da parte di Claude Code
  prepara       crea le schede mancanti nel foglio e le riempie dal seed
  giornaliero   giro delle fonti (tutti i giorni)
  settimanale   tutte le fonti + ricerca AI (il lunedì)
  link URL      estrae un bando da un link incollato
  approfondisci ID   indagine "cerca a fondo" su un bando (giuria, vincitori, reputazione)
  ricalcola     ricalcola punteggi ed esclusioni dopo un cambio di PROFILO
  richiamo      misura copertura e richiamo sull'insieme d'oro
"""

from __future__ import annotations

import argparse
import logging
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="elbandito", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("comando", choices=["configura", "demo", "dashboard", "mcp", "coda", "prepara", "giornaliero", "settimanale", "link", "approfondisci", "ricalcola", "richiamo"])
    ap.add_argument("url", nargs="?", help="URL (link) o ID del bando (approfondisci)")
    ap.add_argument("-v", "--verboso", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verboso else logging.WARNING, format="%(levelname)s %(message)s")

    from .config import Ambiente
    from .foglio import apri

    amb = Ambiente()

    if a.comando == "mcp":
        from .mcp_server import main as servi

        servi()
        return 0

    if a.comando == "configura":
        from .configura import configura

        configura(amb)
        return 0

    if a.comando == "demo":
        from .demo import crea_demo

        n = crea_demo(amb)
        print(f"Dati in {amb.cartella_dati} ({amb.backend}). " +
              (f"Inseriti {n} bandi d'esempio." if n else "BANDI non era vuota: nessun esempio aggiunto."))
        print("Ora: elbandito dashboard")
        return 0

    if a.comando == "dashboard":
        from .dashboard import avvia

        apri(amb).prepara(con_seed=True)
        avvia(amb, apri_browser=True, blocca=True)
        return 0

    if a.comando == "coda":
        from .archivio import Archivio

        arch = Archivio(amb.cartella_dati / "archivio.sqlite")
        print(f"Pagine in coda per Claude Code: {arch.quanti_in_coda()}")
        return 0

    if a.comando == "prepara":
        for riga in apri(amb).prepara() or ["niente da fare: il foglio è già pronto"]:
            print(riga)
        return 0

    if a.comando in ("giornaliero", "settimanale"):
        from .pipeline import Giro

        res = Giro(a.comando, amb).esegui()
        print(f"Fonti lette: {res.fonti_lette} · pagine: {res.pagine} · schede: {res.schede} · "
              f"nuovi: {res.nuovi} · aggiornati: {res.aggiornati} · in coda per Claude Code: {res.in_coda}")
        for n in res.note:
            print("·", n)
        if res.fonti_errore:
            print("Fonti in errore:", ", ".join(res.fonti_errore))
        if res.domini:
            print("Domini da valutare come nuove fonti:", ", ".join(res.domini))
        for e in res.errori:
            print("!", e, file=sys.stderr)
        return 0

    if a.comando == "link":
        if not a.url:
            ap.error("serve l'URL")
        from .pipeline import aggiungi_da_link

        res = aggiungi_da_link(a.url, amb)
        print(f"Nuovi: {res.nuovi} · aggiornati: {res.aggiornati}")
        for e in res.errori:
            print("!", e, file=sys.stderr)
        return 0 if not res.errori else 1

    if a.comando == "approfondisci":
        if not a.url:
            ap.error("serve l'ID del bando, es. B0012")
        from .pipeline import approfondisci

        print(approfondisci(a.url, amb))
        return 0

    if a.comando == "ricalcola":
        from .pipeline import ricalcola

        print(f"Ricalcolati {ricalcola(amb)} bandi")
        return 0

    if a.comando == "richiamo":
        from .archivio import Archivio
        from .richiamo import copertura, richiamo

        foglio = apri(amb)
        cop = copertura(foglio.leggi("FONTI"))
        print("Copertura delle fonti (insieme d'oro):")
        for voce, trovate in cop:
            segno = "✓" if trovate else ("·" if voce.get("Canale") == "passaparola" else "✗")
            print(f"  {segno} {voce['Opportunità']}: {', '.join(trovate) or voce.get('Canale', '—')}")
        coperte = sum(1 for v, t in cop if t)
        attese = sum(1 for v, _ in cop if v.get("Canale") != "passaparola")
        print(f"  {coperte}/{attese} coperte dalle fonti fisse")

        arch = Archivio(amb.cartella_dati / "archivio.sqlite")
        grezzi = [s for (s,) in arch.db.execute("SELECT scheda FROM grezzi")]
        ric = richiamo(foglio.leggi("BANDI"), grezzi)
        print(f"Richiamo sui bandi trovati: {sum(1 for _, ok in ric if ok)}/{len(ric)}")
        for voce, ok in ric:
            print(f"  {'✓' if ok else '✗'} {voce['Opportunità']}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
