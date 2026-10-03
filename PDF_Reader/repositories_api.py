"""Repositórios que falam com a API REST via HTTP.

Implementam os MESMOS Protocols dos repositórios JSON — a UI não sabe
(ou se importa) com quem está falando. Trocar JSON por API é trocar
uma linha no composition root.
"""
from __future__ import annotations

import requests
from typing import List, Optional

from models import Review
from repositories import ErroPersistencia


class RepositorioReviewsAPI:
    """Fala com a API REST do MangaReader para gerenciar reviews.

    Cumpre o mesmo Protocol do RepositorioReviews (JSON local).
    """

    TIMEOUT = 5  # segundos

    def __init__(self, base_url: str):
        # Remove barra final para não duplicar em URLs
        self.base_url = base_url.rstrip("/")

    # ---------- HTTP helpers ----------
    def _get(self, caminho: str):
        try:
            r = requests.get(f"{self.base_url}{caminho}", timeout=self.TIMEOUT)
        except requests.ConnectionError as e:
            raise ErroPersistencia(f"API offline: {e}") from e
        except requests.Timeout:
            raise ErroPersistencia("API demorou demais para responder")
        return r

    def _post(self, caminho: str, dados: dict):
        try:
            r = requests.post(
                f"{self.base_url}{caminho}",
                json=dados,
                timeout=self.TIMEOUT,
            )
        except requests.ConnectionError as e:
            raise ErroPersistencia(f"API offline: {e}") from e
        except requests.Timeout:
            raise ErroPersistencia("API demorou demais para responder")
        return r

    def _put(self, caminho: str, dados: dict):
        try:
            r = requests.put(
                f"{self.base_url}{caminho}",
                json=dados,
                timeout=self.TIMEOUT,
            )
        except requests.ConnectionError as e:
            raise ErroPersistencia(f"API offline: {e}") from e
        except requests.Timeout:
            raise ErroPersistencia("API demorou demais para responder")
        return r

    def _delete(self, caminho: str):
        try:
            r = requests.delete(f"{self.base_url}{caminho}", timeout=self.TIMEOUT)
        except requests.ConnectionError as e:
            raise ErroPersistencia(f"API offline: {e}") from e
        except requests.Timeout:
            raise ErroPersistencia("API demorou demais para responder")
        return r

    # ---------- API pública (mesma do RepositorioReviews JSON) ----------
    @property
    def reviews(self) -> List[Review]:
        """Retorna todas as reviews. Necessário para compatibilidade."""
        r = self._get("/reviews")
        if r.status_code != 200:
            raise ErroPersistencia(f"Erro ao listar: {r.status_code}")
        return [Review.from_dict(item) for item in r.json()]

    def listar_por_perfil(self, perfil: str) -> List[Review]:
        return [rev for rev in self.reviews if rev.perfil == perfil]

    def obter(self, review_id: str) -> Optional[Review]:
        r = self._get(f"/reviews/{review_id}")
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise ErroPersistencia(f"Erro ao obter: {r.status_code}")
        return Review.from_dict(r.json())

    def adicionar(self, review: Review) -> None:
        r = self._post("/reviews", review.to_dict())
        if r.status_code != 201:
            raise ErroPersistencia(f"Erro ao criar: {r.status_code}")

    def atualizar(self, review: Review) -> None:
        r = self._put(f"/reviews/{review.id}", review.to_dict())
        if r.status_code != 200:
            raise ErroPersistencia(f"Erro ao atualizar: {r.status_code}")

    def remover(self, review_id: str) -> None:
        r = self._delete(f"/reviews/{review_id}")
        if r.status_code not in (200, 204):
            raise ErroPersistencia(f"Erro ao remover: {r.status_code}")

    def listar_por_obra(self, obra: str, obra_id: Optional[str] = None) -> List[Review]:
        # A API expõe isso via /catalogo/{id}/reviews, mas para simplificar
        # aqui filtramos localmente.
        return [r for r in self.reviews if r.obra.casefold() == obra.casefold()]

    def media_da_obra(self, obra: str, obra_id: Optional[str] = None) -> tuple[float, int]:
        reviews_obra = self.listar_por_obra(obra, obra_id)
        if not reviews_obra:
            return (0.0, 0)
        notas = [r.nota for r in reviews_obra]
        return (round(sum(notas) / len(notas), 2), len(notas))