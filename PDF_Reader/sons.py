"""Gerenciador de sons do app.

Usa `winsound` (nativo do Windows) para tocar arquivos .wav de forma
assíncrona (não trava a UI).

Recursos:
- Toca sons da pasta `assets/audio/`
- Fallback silencioso se arquivo não existir
- Easter egg: ocasionalmente toca "moo" em vez de "newmail"
- Toggle global on/off
"""
from __future__ import annotations

import os
import random

# winsound só existe no Windows
try:
    import winsound
    _TEM_WINSOUND = True
except ImportError:
    _TEM_WINSOUND = False


class GerenciadorSons:
    """Toca sons de UI de forma assíncrona."""

    # Chance do easter egg (0.0 a 1.0)
    CHANCE_EASTER_EGG = 0.15  # 15%

    def __init__(self, pasta_sons: str, ativo: bool = True):
        self.pasta = pasta_sons
        self.ativo = ativo
        self._cache_existe: dict[str, bool] = {}

        # Mapeamento "apelido" → nome do arquivo (sem extensão)
        # Permite trocar de arquivo depois sem mudar o código
        self._mapa = {
            "enviar": "imsend",
            "receber": "imrcv",
            "notificacao": "newmail",
            "notificacao_easter": "moo",
            "download": "im",  
        }

    # ---------- API pública ----------
    def tocar(self, apelido: str):
        """Toca o som do apelido. Silencioso se não existir/der erro."""
        if not self.ativo or not _TEM_WINSOUND:
            return

        nome_arquivo = self._mapa.get(apelido, apelido)

        # Easter egg: se for notificação, sorteia entre newmail e moo
        if apelido == "notificacao":
            if random.random() < self.CHANCE_EASTER_EGG:
                nome_arquivo = self._mapa["notificacao_easter"]

        caminho = os.path.join(self.pasta, f"{nome_arquivo}.wav")

        if not self._arquivo_existe(caminho):
            return

        try:
            # SND_ASYNC = não bloqueia a UI
            # SND_FILENAME = interpreta como caminho de arquivo
            winsound.PlaySound(
                caminho,
                winsound.SND_FILENAME | winsound.SND_ASYNC,
            )
        except Exception as e:
            print(f"[sons] erro ao tocar '{nome_arquivo}': {e}")

    def alternar_ativo(self) -> bool:
        """Liga/desliga. Retorna o novo estado."""
        self.ativo = not self.ativo
        return self.ativo

    # ---------- Utilitários ----------
    def _arquivo_existe(self, caminho: str) -> bool:
        """Cache para não bater no disco toda hora."""
        if caminho not in self._cache_existe:
            self._cache_existe[caminho] = os.path.exists(caminho)
        return self._cache_existe[caminho]

    def limpar_cache(self):
        """Se o usuário adicionar/trocar arquivos em runtime."""
        self._cache_existe.clear()