"""gerenciador_downloads.py

Baixa arquivos em background (thread), com:
- User-Agent (o Internet Archive bloqueia requests sem)
- Redirect follow automático
- Validação de content-type (evita salvar HTML como PDF)
- Mensagens específicas por tipo de erro (403, 404, content-type)
- Cancelamento real (fecha socket)
- Progresso em bytes
- Limpeza garantida de arquivo .part em qualquer falha
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Callable

import requests


USER_AGENT = "MangaReader2000/1.0 (leitor-de-mangas; +https://github.com/)"

# Tempo máximo sem receber nenhum byte antes de desistir (segundos).
# Aplicado por leitura de chunk, não ao download inteiro — PDFs grandes
# continuam baixando normalmente.
TIMEOUT_LEITURA = 30

# Tamanho do chunk de download (bytes). 64 KiB é o sweet spot entre
# throughput e responsividade do progresso.
CHUNK_SIZE = 64 * 1024


@dataclass
class Callbacks:
    """Callbacks disparados no thread da UI (via root.after)."""
    on_progresso: Callable[[int, int], None]   # (bytes_baixados, bytes_total)
    on_concluido: Callable[[], None]
    on_erro: Callable[[str], None]
    on_cancelado: Callable[[], None]


class GerenciadorDownloads:
    """Gerencia downloads concorrentes, cada um em sua própria thread.

    Uso:
        gerenciador.baixar(
            chave="liv-001:vol1",
            url="https://archive.org/download/.../arquivo.pdf",
            destino="pdf_padrao/Dom Casmurro/Volume 01.pdf",
            callbacks=Callbacks(...),
        )
        gerenciador.cancelar("liv-001:vol1")
    """

    def __init__(self, root, pasta_base: str):
        self.root = root
        self.pasta_base = pasta_base
        # chave -> {"cancelar": bool, "sessao": requests.Session | None}
        self._ativos: dict[str, dict] = {}

    # ==========================================================
    # API PÚBLICA
    # ==========================================================
    def baixar(self, chave: str, url: str, destino: str,
               callbacks: Callbacks) -> None:
        if chave in self._ativos:
            # Já existe — ignora silenciosamente (evita duplicar cliques)
            return

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
        # Fechar a sessão interrompe o socket imediatamente
        sessao = ref.get("sessao")
        if sessao is not None:
            try:
                sessao.close()
            except Exception:
                pass

    def esta_ativo(self, chave: str) -> bool:
        return chave in self._ativos

    # ==========================================================
    # WORKER (roda em thread separada)
    # ==========================================================
    def _worker(self, chave, url, destino, callbacks: Callbacks, ref) -> None:
        tmp = destino + ".part"
        sessao = None

        try:
            # Garante a pasta de destino
            os.makedirs(os.path.dirname(destino), exist_ok=True)

            sessao = requests.Session()
            ref["sessao"] = sessao

            with sessao.get(
                url,
                headers={"User-Agent": USER_AGENT},
                stream=True,
                timeout=TIMEOUT_LEITURA,
                allow_redirects=True,
            ) as r:

                # ---------- TRATAMENTO POR STATUS ----------
                if r.status_code == 403:
                    self._limpar_tmp(tmp)
                    self._erro(callbacks, self._msg_403(url))
                    return

                if r.status_code == 404:
                    self._limpar_tmp(tmp)
                    self._erro(callbacks,
                               "❌ Arquivo não encontrado no servidor (404).\n\n"
                               "O Internet Archive pode ter renomeado o arquivo.\n"
                               "Tente rodar 'python corrigir_catalogo.py' de novo.")
                    return

                if r.status_code != 200:
                    self._limpar_tmp(tmp)
                    self._erro(callbacks,
                               f"❌ Servidor respondeu HTTP {r.status_code}.\n\n"
                               f"Se o erro persistir, verifique se o link ainda está "
                               f"válido:\n{url}")
                    return

                # ---------- VALIDAÇÃO DE CONTENT-TYPE ----------
                ct = r.headers.get("content-type", "").lower()

                if "html" in ct:
                    self._limpar_tmp(tmp)
                    self._erro(callbacks,
                               "❌ O link retornou uma PÁGINA HTML, não um PDF.\n\n"
                               "Isso geralmente significa que a obra só está "
                               "disponível para empréstimo no Internet Archive.\n\n"
                               "Link para ler online:\n"
                               f"{self._link_detalhes(url)}")
                    return

                if "pdf" not in ct and "octet-stream" not in ct and ct:
                    # Alguns CDNs mandam application/force-download ou vazio.
                    # Se tem um content-length grande e não é HTML, deixa passar.
                    try:
                        tamanho_prev = int(r.headers.get("content-length", 0))
                    except (TypeError, ValueError):
                        tamanho_prev = 0

                    if tamanho_prev < 100_000:
                        # Menos de 100 KB e content-type estranho = suspeito
                        self._limpar_tmp(tmp)
                        self._erro(callbacks,
                                   f"❌ O servidor retornou um arquivo suspeito "
                                   f"(content-type: {ct}).\n\n"
                                   f"Provavelmente não é o PDF esperado.")
                        return

                # ---------- TAMANHO TOTAL ----------
                try:
                    total = int(r.headers.get("content-length", 0))
                except (TypeError, ValueError):
                    total = 0

                # ---------- LOOP DE DOWNLOAD ----------
                baixado = 0
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                        if ref["cancelar"]:
                            f.close()
                            self._limpar_tmp(tmp)
                            self._cancelado(callbacks)
                            return

                        if chunk:
                            f.write(chunk)
                            baixado += len(chunk)
                            self._progresso(callbacks, baixado, total)

            # ---------- FINALIZAÇÃO ATÔMICA ----------
            if ref["cancelar"]:
                self._limpar_tmp(tmp)
                self._cancelado(callbacks)
                return

            # Substitui destino (se já existe) pelo tmp
            if os.path.exists(destino):
                try:
                    os.remove(destino)
                except OSError:
                    pass
            os.replace(tmp, destino)

            self._concluido(callbacks)

        except requests.exceptions.Timeout:
            self._limpar_tmp(tmp)
            self._erro(callbacks,
                       "❌ O servidor demorou demais para responder.\n\n"
                       "Verifique sua conexão e tente de novo.")
        except requests.exceptions.ConnectionError:
            self._limpar_tmp(tmp)
            self._erro(callbacks,
                       "❌ Não foi possível conectar ao servidor.\n\n"
                       "Verifique se você está online.")
        except requests.exceptions.RequestException as e:
            self._limpar_tmp(tmp)
            self._erro(callbacks, f"❌ Erro de rede: {e}")
        except OSError as e:
            self._limpar_tmp(tmp)
            self._erro(callbacks, f"❌ Erro de disco: {e}")
        except Exception as e:
            self._limpar_tmp(tmp)
            self._erro(callbacks, f"❌ Erro inesperado: {e}")
        finally:
            self._ativos.pop(chave, None)

    # ==========================================================
    # HELPERS
    # ==========================================================
    @staticmethod
    def _limpar_tmp(caminho: str) -> None:
        """Remove o arquivo temporário, engolindo qualquer erro."""
        try:
            if os.path.exists(caminho):
                os.remove(caminho)
        except OSError:
            pass

    @staticmethod
    def _link_detalhes(url: str) -> str:
        """Converte URL de download do IA em link da página de detalhes."""
        # https://archive.org/download/{identifier}/{arquivo}
        #   → https://archive.org/details/{identifier}
        try:
            partes = url.split("/")
            if "archive.org" in partes[2] and "download" in partes:
                idx = partes.index("download")
                if idx + 1 < len(partes):
                    return f"https://archive.org/details/{partes[idx + 1]}"
        except (IndexError, ValueError):
            pass
        return url

    @staticmethod
    def _msg_403(url: str) -> str:
        return (
            "❌ Acesso negado (HTTP 403).\n\n"
            "Esta obra está disponível apenas para EMPRÉSTIMO no Internet "
            "Archive — não é possível baixar o PDF diretamente.\n\n"
            "Você pode ler online em:\n"
            f"{GerenciadorDownloads._link_detalhes(url)}"
        )

    # ---------- callbacks no thread da UI ----------
    def _progresso(self, cb: Callbacks, b: int, t: int) -> None:
        self.root.after(0, lambda: cb.on_progresso(b, t))

    def _concluido(self, cb: Callbacks) -> None:
        self.root.after(0, cb.on_concluido)

    def _erro(self, cb: Callbacks, msg: str) -> None:
        self.root.after(0, lambda: cb.on_erro(msg))

    def _cancelado(self, cb: Callbacks) -> None:
        self.root.after(0, cb.on_cancelado)