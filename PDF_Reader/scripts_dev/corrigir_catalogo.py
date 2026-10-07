"""gerenciador_downloads.py

Baixa arquivos em background (thread), com:
- User-Agent (o IA bloqueia sem)
- Redirect follow automático
- Validação de content-type (evita salvar HTML como PDF)
- Cancelamento real (fecha socket)
- Progresso em bytes
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Callable

import requests


USER_AGENT = "MangaReader2000/1.0 (leitor-de-mangas; +https://github.com/)"


@dataclass
class Callbacks:
    on_progresso: Callable[[int, int], None]   # (bytes_baixados, bytes_total)
    on_concluido: Callable[[], None]
    on_erro: Callable[[str], None]
    on_cancelado: Callable[[], None]


class GerenciadorDownloads:
    def __init__(self, root, pasta_base: str):
        self.root = root
        self.pasta_base = pasta_base
        self._ativos: dict[str, dict] = {}

    def baixar(self, chave: str, url: str, destino: str,
               callbacks: Callbacks) -> None:
        ref = {"cancelar": False, "sessao": None}
        self._ativos[chave] = ref
        threading.Thread(
            target=self._worker,
            args=(chave, url, destino, callbacks, ref),
            daemon=True,
        ).start()

    def cancelar(self, chave: str) -> None:
        ref = self._ativos.get(chave)
        if ref is None:
            return
        ref["cancelar"] = True
        sessao = ref.get("sessao")
        if sessao is not None:
            try:
                sessao.close()
            except Exception:
                pass

    def _worker(self, chave, url, destino, callbacks: Callbacks, ref) -> None:
        tmp = destino + ".part"
        sessao = None
        try:
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            sessao = requests.Session()
            ref["sessao"] = sessao

            with sessao.get(
                url,
                headers={"User-Agent": USER_AGENT},
                stream=True,
                timeout=30,
                allow_redirects=True,
            ) as r:
                if r.status_code != 200:
                    self._erro(callbacks,
                               f"HTTP {r.status_code} ao acessar {url}")
                    return

                ct = r.headers.get("content-type", "").lower()
                if "pdf" not in ct and "octet-stream" not in ct:
                    self._erro(
                        callbacks,
                        f"O link não é um PDF (content-type: {ct}).\n"
                        f"Provavelmente a obra só existe como empréstimo "
                        f"controlado no Internet Archive."
                    )
                    return

                try:
                    total = int(r.headers.get("content-length", 0))
                except (TypeError, ValueError):
                    total = 0

                baixado = 0
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=64 * 1024):
                        if ref["cancelar"]:
                            f.close()
                            try:
                                os.remove(tmp)
                            except OSError:
                                pass
                            self._cancelado(callbacks)
                            return
                        if chunk:
                            f.write(chunk)
                            baixado += len(chunk)
                            self._progresso(callbacks, baixado, total)

            if os.path.exists(destino):
                os.remove(destino)
            os.replace(tmp, destino)
            self._concluido(callbacks)

        except requests.exceptions.RequestException as e:
            self._erro(callbacks, f"Erro de rede: {e}")
        except OSError as e:
            self._erro(callbacks, f"Erro de disco: {e}")
        except Exception as e:
            self._erro(callbacks, f"Erro inesperado: {e}")
        finally:
            self._ativos.pop(chave, None)

    # ---- helpers: sempre voltam pro thread da UI ----
    def _progresso(self, cb, b, t):
        self.root.after(0, lambda: cb.on_progresso(b, t))

    def _concluido(self, cb):
        self.root.after(0, cb.on_concluido)

    def _erro(self, cb, msg):
        self.root.after(0, lambda: cb.on_erro(msg))

    def _cancelado(self, cb):
        self.root.after(0, cb.on_cancelado)