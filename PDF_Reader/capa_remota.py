"""capa_remota.py

Baixa as capas do Internet Archive em background e cacheia em disco.
Endpoint público: https://archive.org/services/img/{identifier}
"""
from __future__ import annotations

import os
import threading
from typing import Callable, Optional

import requests


USER_AGENT = "MangaReader2000/1.0"


class GerenciadorCapas:
    """Cache de capas do IA. Baixa 1x por identifier, reusa sempre."""

    def __init__(self, pasta_cache: str):
        self.pasta_cache = pasta_cache
        os.makedirs(pasta_cache, exist_ok=True)
        self._em_andamento: set[str] = set()
        self._lock = threading.Lock()

    def caminho_cache(self, item_id: str) -> str:
        return os.path.join(self.pasta_cache, f"{item_id}.jpg")

    def obter_cache(self, item_id: str) -> Optional[str]:
        """Retorna o caminho se já está em cache. Senão None."""
        caminho = self.caminho_cache(item_id)
        return caminho if os.path.exists(caminho) else None

    def baixar_async(self, item_id: str, url: str,
                     on_pronto: Callable[[str], None],
                     on_erro: Optional[Callable[[str], None]] = None) -> None:
        caminho = self.caminho_cache(item_id)

        if os.path.exists(caminho):
            on_pronto(caminho)
            return

        with self._lock:
            if item_id in self._em_andamento:
                return
            self._em_andamento.add(item_id)

        threading.Thread(
            target=self._worker,
            args=(item_id, url, caminho, on_pronto, on_erro),
            daemon=True,
        ).start()

    def _worker(self, item_id, url, caminho, on_pronto, on_erro):
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT},
                             timeout=15, allow_redirects=True)
            if r.status_code != 200:
                if on_erro:
                    on_erro(f"HTTP {r.status_code}")
                return

            ct = r.headers.get("content-type", "").lower()
            if not any(x in ct for x in ("image/", "jpeg", "png", "jpg", "gif")):
                if on_erro:
                    on_erro(f"Content-type inesperado: {ct}")
                return

            with open(caminho, "wb") as f:
                f.write(r.content)
            on_pronto(caminho)
        except Exception as e:
            if on_erro:
                on_erro(str(e))
        finally:
            with self._lock:
                self._em_andamento.discard(item_id)