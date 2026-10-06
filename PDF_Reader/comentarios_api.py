"""Cliente HTTP para as rotas /comentarios da API."""
from __future__ import annotations

import requests
from dataclasses import dataclass


class ErroComentario(Exception):
    """Erro controlado nas operações de comentário."""


@dataclass
class Comentario:
    id: str
    autor_id: str
    autor_nome: str
    alvo_id: str
    texto: str
    criado_em: str


class RepositorioComentariosAPI:
    TIMEOUT = 5

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token

    # ---------- internos ----------
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def _get(self, caminho: str):
        try:
            return requests.get(
                f"{self.base_url}{caminho}",
                headers=self._headers(), timeout=self.TIMEOUT,
            )
        except requests.ConnectionError as e:
            raise ErroComentario(f"API offline: {e}") from e
        except requests.Timeout:
            raise ErroComentario("API demorou demais para responder")

    def _post(self, caminho: str, dados: dict):
        try:
            return requests.post(
                f"{self.base_url}{caminho}",
                json=dados, headers=self._headers(), timeout=self.TIMEOUT,
            )
        except requests.ConnectionError as e:
            raise ErroComentario(f"API offline: {e}") from e
        except requests.Timeout:
            raise ErroComentario("API demorou demais para responder")

    def _delete(self, caminho: str):
        try:
            return requests.delete(
                f"{self.base_url}{caminho}",
                headers=self._headers(), timeout=self.TIMEOUT,
            )
        except requests.ConnectionError as e:
            raise ErroComentario(f"API offline: {e}") from e
        except requests.Timeout:
            raise ErroComentario("API demorou demais para responder")

    # ---------- API pública ----------
    def listar(self, nome_alvo: str) -> list[Comentario]:
        r = self._get(f"/comentarios/{nome_alvo}")
        if r.status_code == 404:
            raise ErroComentario(f"Usuário '{nome_alvo}' não existe")
        if r.status_code != 200:
            raise ErroComentario(f"Erro ao listar: {r.status_code}")
        return [
            Comentario(
                id=d["id"],
                autor_id=d["autor_id"],
                autor_nome=d["autor_nome"],
                alvo_id=d["alvo_id"],
                texto=d["texto"],
                criado_em=d["criado_em"],
            )
            for d in r.json()
        ]

    def postar(self, nome_alvo: str, texto: str) -> Comentario:
        r = self._post(f"/comentarios/{nome_alvo}", {"texto": texto})
        if r.status_code == 404:
            raise ErroComentario(f"Usuário '{nome_alvo}' não existe")
        if r.status_code == 422:
            raise ErroComentario("Comentário inválido (vazio ou muito longo)")
        if r.status_code != 201:
            raise ErroComentario(f"Erro ao postar: {r.status_code}")
        d = r.json()
        return Comentario(
            id=d["id"],
            autor_id=d["autor_id"],
            autor_nome=d["autor_nome"],
            alvo_id=d["alvo_id"],
            texto=d["texto"],
            criado_em=d["criado_em"],
        )

    def deletar(self, comentario_id: str) -> None:
        r = self._delete(f"/comentarios/{comentario_id}")
        if r.status_code == 404:
            raise ErroComentario("Comentário não encontrado ou sem permissão")
        if r.status_code not in (200, 204):
            raise ErroComentario(f"Erro ao deletar: {r.status_code}")