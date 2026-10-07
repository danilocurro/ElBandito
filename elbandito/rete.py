"""Client HTTP educato: user-agent dichiarato, robots.txt, un colpo ogni 2-3 s per dominio."""

from __future__ import annotations

import random
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from .config import USER_AGENT


class AccessoNegato(Exception):
    """robots.txt vieta la pagina, o il sito risponde 401/403: si lascia fuori."""


class Rete:
    def __init__(self, pausa: tuple[float, float] = (2.0, 3.0), timeout: float = 30.0):
        self.pausa = pausa
        self.client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept-Language": "it,en;q=0.8"},
            timeout=timeout,
            follow_redirects=True,
        )
        self._ultimo: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}

    def _permesso(self, url: str) -> bool:
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        if base not in self._robots:
            rp = RobotFileParser()
            try:
                r = self.client.get(base + "/robots.txt", timeout=10)
                if r.status_code >= 400:
                    self._robots[base] = None  # niente robots.txt: tutto permesso
                else:
                    rp.parse(r.text.splitlines())
                    self._robots[base] = rp
            except httpx.HTTPError:
                self._robots[base] = None
        rp = self._robots[base]
        return rp is None or rp.can_fetch(USER_AGENT, url)

    def _attendi(self, url: str) -> None:
        dominio = urlparse(url).netloc
        trascorso = time.monotonic() - self._ultimo.get(dominio, 0)
        attesa = random.uniform(*self.pausa) - trascorso
        if attesa > 0:
            time.sleep(attesa)
        self._ultimo[dominio] = time.monotonic()

    def richiesta(self, metodo: str, url: str, **kw) -> httpx.Response:
        if not self._permesso(url):
            raise AccessoNegato(f"robots.txt non permette {url}")
        for tentativo in range(3):
            self._attendi(url)
            try:
                r = self.client.request(metodo, url, **kw)
            except httpx.TransportError:
                if tentativo == 2:
                    raise
                time.sleep(5 * (tentativo + 1))
                continue
            if r.status_code in (401, 403):
                raise AccessoNegato(f"{r.status_code} su {url}")
            if r.status_code in (429, 502, 503, 504) and tentativo < 2:
                time.sleep(10 * (tentativo + 1))
                continue
            r.raise_for_status()
            return r
        raise RuntimeError("irraggiungibile")

    def get(self, url: str, **kw) -> httpx.Response:
        return self.richiesta("GET", url, **kw)

    def post(self, url: str, **kw) -> httpx.Response:
        return self.richiesta("POST", url, **kw)
