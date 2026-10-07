"""Cliente HTTP para a rota /usuarios/buscar."""
from __future__ import annotations

import requests
from dataclasses import dataclass


class ErroBusca(Exception):
    """Erro controlado na busca de usuários."""


@dataclass
class UsuarioBusca:
    id: str
    nome: str
    criado_em: str
    eu_mesmo: bool


class RepositorioBuscaAPI:
    TIMEOUT = 5

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def buscar(self, termo: str) -> list[UsuarioBusca]:
        termo = termo.strip()
        if not termo:
            return []

        try:
            r = requests.get(
                f"{self.base_url}/usuarios/buscar",
                params={"q": termo},
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=self.TIMEOUT,
            )
        except requests.ConnectionError as e:
            raise ErroBusca(f"API offline: {e}") from e
        except requests.Timeout:
            raise ErroBusca("API demorou demais para responder")

        if r.status_code == 401:
            raise ErroBusca("Sessão expirada")
        if r.status_code == 422:
            raise ErroBusca("Termo inválido (mínimo 1 caractere)")
        if r.status_code != 200:
            raise ErroBusca(f"Erro na busca: {r.status_code}")

        return [
            UsuarioBusca(
                id=d["id"],
                nome=d["nome"],
                criado_em=d["criado_em"],
                eu_mesmo=bool(d.get("eu_mesmo", False)),
            )
            for d in r.json()
        ]
    def listar_todos(self) -> list[UsuarioBusca]:
        """Lista todos os usuários cadastrados (exceto o próprio usuário)."""
        try:
            r = requests.get(
                f"{self.base_url}/usuarios",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=self.TIMEOUT,
            )
        except requests.ConnectionError as e:
            raise ErroBusca(f"API offline: {e}") from e
        except requests.Timeout:
            raise ErroBusca("API demorou demais para responder")

        if r.status_code == 401:
            raise ErroBusca("Sessão expirada")
        if r.status_code != 200:
            raise ErroBusca(f"Erro ao listar usuários: {r.status_code}")

        return [
            UsuarioBusca(
                id=d["id"],
                nome=d["nome"],
                criado_em=d["criado_em"],
                eu_mesmo=bool(d.get("eu_mesmo", False)),
            )
            for d in r.json()
        ]