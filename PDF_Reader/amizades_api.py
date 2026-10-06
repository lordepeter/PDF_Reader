"""Cliente HTTP para as rotas /amizades da API."""
from __future__ import annotations

import requests
from dataclasses import dataclass


class ErroAmizade(Exception):
    """Erro controlado nas operações de amizade."""


@dataclass
class Amigo:
    amizade_id: str
    usuario_id: str
    nome: str
    desde: str


@dataclass
class PedidoPendente:
    amizade_id: str
    usuario_id: str       # solicitante
    nome: str
    criado_em: str


class RepositorioAmizadesAPI:
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
            raise ErroAmizade(f"API offline: {e}") from e
        except requests.Timeout:
            raise ErroAmizade("API demorou demais para responder")

    def _post(self, caminho: str):
        try:
            return requests.post(
                f"{self.base_url}{caminho}",
                headers=self._headers(), timeout=self.TIMEOUT,
            )
        except requests.ConnectionError as e:
            raise ErroAmizade(f"API offline: {e}") from e
        except requests.Timeout:
            raise ErroAmizade("API demorou demais para responder")

    def _delete(self, caminho: str):
        try:
            return requests.delete(
                f"{self.base_url}{caminho}",
                headers=self._headers(), timeout=self.TIMEOUT,
            )
        except requests.ConnectionError as e:
            raise ErroAmizade(f"API offline: {e}") from e
        except requests.Timeout:
            raise ErroAmizade("API demorou demais para responder")

    # ---------- API pública ----------
    def listar(self) -> list[Amigo]:
        r = self._get("/amizades")
        if r.status_code == 401:
            raise ErroAmizade("Sessão expirada — faça login de novo")
        if r.status_code != 200:
            raise ErroAmizade(f"Erro ao listar amigos: {r.status_code}")
        return [
            Amigo(
                amizade_id=d["amizade_id"],
                usuario_id=d["usuario_id"],
                nome=d["nome"],
                desde=d["desde"],
            )
            for d in r.json()
        ]

    def listar_pendentes(self) -> list[PedidoPendente]:
        r = self._get("/amizades/pendentes")
        if r.status_code != 200:
            raise ErroAmizade(f"Erro ao listar pedidos: {r.status_code}")
        return [
            PedidoPendente(
                amizade_id=d["amizade_id"],
                usuario_id=d["solicitante_id"],
                nome=d["nome"],
                criado_em=d["criado_em"],
            )
            for d in r.json()
        ]

    def enviar_pedido(self, nome_destino: str) -> None:
        r = self._post(f"/amizades/pedido/{nome_destino}")
        if r.status_code == 404:
            raise ErroAmizade(f"Usuário '{nome_destino}' não existe")
        if r.status_code == 409:
            raise ErroAmizade("Já existe amizade ou pedido pendente com essa pessoa")
        if r.status_code != 201:
            raise ErroAmizade(f"Erro ao enviar pedido: {r.status_code}")

    def aceitar(self, amizade_id: str) -> None:
        r = self._post(f"/amizades/{amizade_id}/aceitar")
        if r.status_code != 200:
            raise ErroAmizade(f"Erro ao aceitar: {r.status_code}")

    def recusar(self, amizade_id: str) -> None:
        r = self._delete(f"/amizades/{amizade_id}/recusar")
        if r.status_code not in (200, 204):
            raise ErroAmizade(f"Erro ao recusar: {r.status_code}")

    def desfazer(self, amizade_id: str) -> None:
        r = self._delete(f"/amizades/{amizade_id}")
        if r.status_code not in (200, 204):
            raise ErroAmizade(f"Erro ao desfazer: {r.status_code}")