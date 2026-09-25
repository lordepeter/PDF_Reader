"""Gerenciador de downloads em background.

Roda downloads em threads separadas e reporta progresso para a UI via
queue.Queue — o único mecanismo thread-safe para conversar com o Tkinter.

A UI nunca é tocada de dentro das threads de trabalho.
"""
from __future__ import annotations

import os
import queue
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional


# ============================================================
# EVENTO — o "recado" que a thread manda para a UI
# ============================================================
@dataclass
class EventoDownload:
    tipo: str            # "progresso" | "concluido" | "erro" | "cancelado"
    chave: str           # id único do download (ex: "ob-001:vol1")
    baixado: int = 0     # bytes já baixados
    total: int = 0       # bytes totais (0 se desconhecido)
    mensagem: str = ""   # texto de erro, se houver


# ============================================================
# CALLBACKS — o que a UI quer que aconteça a cada evento
# ============================================================
@dataclass
class Callbacks:
    on_progresso: Callable[[int, int], None]
    on_concluido: Callable[[], None]
    on_erro: Callable[[str], None]
    on_cancelado: Callable[[], None] = field(default=lambda: None)


# ============================================================
# GERENCIADOR
# ============================================================
class GerenciadorDownloads:
    """Gerencia downloads assíncronos com progresso.

    Uso típico:
        gerenciador.baixar(
            chave="ob-001:vol1",
            url="https://.../vol1.pdf",
            destino="C:/.../pdf_padrao/Obra/vol1.pdf",
            callbacks=Callbacks(on_progresso=..., on_concluido=..., on_erro=...),
        )
    """

    TAMANHO_CHUNK = 64 * 1024  # 64 KB por chunk — bom equilíbrio
    INTERVALO_POLL_MS = 100     # UI checa a fila 10x por segundo
    TIMEOUT_SEGUNDOS = 60       # se travar por 60s, aborta

    def __init__(self, root, pasta_destino_base: str):
        self.root = root
        self.pasta_destino_base = pasta_destino_base
        self._fila: "queue.Queue[EventoDownload]" = queue.Queue()
        self._callbacks: Dict[str, Callbacks] = {}
        self._threads_ativas: Dict[str, threading.Thread] = {}
        self._para_cancelar: set[str] = set()
        self._iniciar_poll()

    # ---------- API pública ----------
    def baixar(
        self,
        chave: str,
        url: str,
        destino: str,
        callbacks: Callbacks,
    ) -> bool:
        """Inicia um download. Retorna False se já houver um com a mesma chave."""
        if chave in self._threads_ativas:
            return False

        self._callbacks[chave] = callbacks
        thread = threading.Thread(
            target=self._worker,
            args=(chave, url, destino),
            daemon=True,  # morre quando o app fechar
            name=f"download-{chave}",
        )
        self._threads_ativas[chave] = thread
        thread.start()
        return True

    def cancelar(self, chave: str) -> None:
        """Pede o cancelamento (a thread verifica antes de cada chunk)."""
        self._para_cancelar.add(chave)

    def ativo(self, chave: str) -> bool:
        return chave in self._threads_ativas

    # ---------- Thread de trabalho ----------
    def _worker(self, chave: str, url: str, destino: str) -> None:
        """Roda em thread separada. NUNCA toca em widgets."""
        parcial = destino + ".parcial"
        try:
            os.makedirs(os.path.dirname(destino), exist_ok=True)

            # User-Agent evita bloqueio de alguns servidores
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "MangaReader2000/1.0 (+python-urllib)"},
            )

            with urllib.request.urlopen(req, timeout=self.TIMEOUT_SEGUNDOS) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                baixado = 0

                with open(parcial, "wb") as f:
                    while True:
                        if chave in self._para_cancelar:
                            f.close()
                            self._remover_silencioso(parcial)
                            self._fila.put(EventoDownload("cancelado", chave))
                            return

                        chunk = resp.read(self.TAMANHO_CHUNK)
                        if not chunk:
                            break

                        f.write(chunk)
                        baixado += len(chunk)
                        self._fila.put(
                            EventoDownload("progresso", chave, baixado, total)
                        )

            # Arquivo 100% baixado — agora sim vira o definitivo
            os.replace(parcial, destino)
            self._fila.put(EventoDownload("concluido", chave))

        except urllib.error.HTTPError as e:
            self._remover_silencioso(parcial)
            self._fila.put(EventoDownload(
                "erro", chave, mensagem=f"Servidor respondeu {e.code}: {e.reason}"
            ))
        except urllib.error.URLError as e:
            self._remover_silencioso(parcial)
            self._fila.put(EventoDownload(
                "erro", chave, mensagem=f"Erro de conexão: {e.reason}"
            ))
        except Exception as e:
            self._remover_silencioso(parcial)
            self._fila.put(EventoDownload(
                "erro", chave, mensagem=f"{type(e).__name__}: {e}"
            ))
        finally:
            self._threads_ativas.pop(chave, None)
            self._para_cancelar.discard(chave)

    # ---------- Loop na thread principal ----------
    def _iniciar_poll(self) -> None:
        """Roda na thread do Tkinter. Lê a fila e dispara callbacks."""
        self._processar_fila()
        # Reagenda a si mesmo (padrão de loop com root.after)
        self.root.after(self.INTERVALO_POLL_MS, self._iniciar_poll)

    def _processar_fila(self) -> None:
        """Roda na thread do Tkinter. Aqui SIM pode tocar em widgets."""
        while True:
            try:
                evento = self._fila.get_nowait()
            except queue.Empty:
                return

            cb = self._callbacks.get(evento.chave)
            if cb is None:
                continue

            try:
                if evento.tipo == "progresso":
                    cb.on_progresso(evento.baixado, evento.total)
                elif evento.tipo == "concluido":
                    cb.on_concluido()
                    self._callbacks.pop(evento.chave, None)
                elif evento.tipo == "erro":
                    cb.on_erro(evento.mensagem)
                    self._callbacks.pop(evento.chave, None)
                elif evento.tipo == "cancelado":
                    cb.on_cancelado()
                    self._callbacks.pop(evento.chave, None)
            except Exception as e:
                # Se a UI falhar, não deixa o loop morrer
                print(f"[download] erro em callback: {e}")

    # ---------- Utilitário ----------
    @staticmethod
    def _remover_silencioso(caminho: str) -> None:
        try:
            os.remove(caminho)
        except OSError:
            pass