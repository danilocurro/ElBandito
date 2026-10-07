import json

from conftest import leggi, rete_finta

from elbandito import connettori
from elbandito.archivio import Archivio
from elbandito.config import Profilo

BANDO = "https://rivista.example/2026/10/premio-portici/"


def archivio(tmp_path):
    return Archivio(tmp_path / "a.sqlite")


def test_rss_filtra_e_apre_le_voci_brevi(tmp_path):
    rete = rete_finta({
        "https://rivista.example/feed/": (200, "application/rss+xml", leggi("feed.xml")),
        BANDO: (200, "text/html", leggi("bando.html")),
    })
    fonte = {"ID": "F02", "URL": "https://rivista.example/feed/", "Parametri": "filtro=open call|bando|premio"}
    pagine = connettori.rss(fonte, rete, archivio(tmp_path), Profilo())
    assert [p.url for p in pagine] == [BANDO]  # la recensione non passa il filtro
    assert "15 gennaio 2027" in pagine[0].testo  # riassunto corto: pagina aperta e ripulita
    assert "Home · Bandi" not in pagine[0].testo  # menu tolto da trafilatura


def test_rss_non_rilegge_le_voci_gia_viste(tmp_path):
    rete = rete_finta({
        "https://rivista.example/feed/": (200, "application/rss+xml", leggi("feed.xml")),
        BANDO: (200, "text/html", leggi("bando.html")),
    })
    arch = archivio(tmp_path)
    arch.segna(BANDO, "F02")
    fonte = {"ID": "F02", "URL": "https://rivista.example/feed/", "Parametri": "filtro=premio"}
    assert connettori.rss(fonte, rete, arch, Profilo()) == []


def test_listing_trova_solo_i_link_interni_nuovi(tmp_path):
    base = "https://residenze.example"
    rete = rete_finta({
        f"{base}/open-calls/": (200, "text/html", leggi("elenco.html")),
        f"{base}/open-calls/residenza-isole-2027/": (200, "text/html", leggi("bando.html")),
        f"{base}/open-calls/photo-grant-north/": (200, "text/html", leggi("bando.html")),
    })
    arch = archivio(tmp_path)
    arch.segna(f"{base}/open-calls/photo-grant-north/", "F09")
    fonte = {"ID": "F09", "URL": f"{base}/open-calls/", "Parametri": "pattern=/open-calls/.+"}
    pagine = connettori.listing(fonte, rete, arch, Profilo())
    assert [p.url for p in pagine] == [f"{base}/open-calls/residenza-isole-2027/"]


def test_wordpress_usa_le_parole_chiave(tmp_path):
    post = [{"id": 1, "link": BANDO, "modified": "2026-10-05T10:00:00",
             "title": {"rendered": "Premio Portici"}, "content": {"rendered": leggi("bando.html")}}]
    rete = rete_finta({"https://rivista.example/wp-json/wp/v2/posts": (200, "application/json", json.dumps(post))})
    fonte = {"ID": "F03", "URL": "https://rivista.example", "Parametri": "cerca=fotografia|residenza"}
    pagine = connettori.wordpress(fonte, rete, archivio(tmp_path), Profilo())
    assert len(pagine) == 1  # stesso post da due ricerche: una sola pagina
    assert pagine[0].titolo == "Premio Portici"


def test_watch_passa_solo_se_la_pagina_cambia(tmp_path):
    url = "https://festival.example/open-call"
    risposte = {url: (200, "text/html", leggi("bando.html"))}
    arch = archivio(tmp_path)
    fonte = {"ID": "F20", "URL": url}
    prima = connettori.watch(fonte, rete_finta(risposte), arch, Profilo())
    assert len(prima) == 1
    arch.segna(url, "F20", prima[0].strutturato["hash"])
    assert connettori.watch(fonte, rete_finta(risposte), arch, Profilo()) == []
    risposte[url] = (200, "text/html", leggi("bando.html").replace("15 gennaio", "31 gennaio"))
    assert len(connettori.watch(fonte, rete_finta(risposte), arch, Profilo())) == 1


def test_accesso_negato_su_403(tmp_path):
    import pytest

    from elbandito.rete import AccessoNegato

    rete = rete_finta({"https://chiuso.example/": (403, "text/html", "no")})
    with pytest.raises(AccessoNegato):
        connettori.watch({"ID": "F30", "URL": "https://chiuso.example/"}, rete, archivio(tmp_path), Profilo())


def test_parametri():
    assert connettori.parametri({"Parametri": "filtro=a|b; max=10"}) == {"filtro": "a|b", "max": "10"}
    assert connettori.parametri({}) == {}
