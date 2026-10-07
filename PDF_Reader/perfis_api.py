"""perfis_api.py — Cliente HTTP do recurso /perfis da API Sophia."""
from __future__ import annotations
import requests


class ErroPerfil(Exception):
    """Erro controlado de operacao com perfil."""


class PerfilRemoto:
    def __init__(self, d: dict):
        self.id = d.get("id", "")
        self.nome = d.get("nome", "")
        self.bio = d.get("bio", "")
        self.foto_path = d.get("foto_path", "")
        self.favoritos = list(d.get("favoritos", []))
        self.criado_em = d.get("criado_em", "")


class RepositorioPerfisAPI:
    def __init__(self, base_url: str, token: str | None = None, timeout: int = 8):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def obter(self, nome: str) -> PerfilRemoto | None:
        try:
            r = requests.get(
                f"{self.base_url}/perfis/{nome}",
                headers=self._headers(),
                timeout=self.timeout,
            )
            if r.status_code == 404:
                return None
            if r.status_code != 200:
                raise ErroPerfil(f"HTTP {r.status_code}")
            return PerfilRemoto(r.json())
        except requests.RequestException as e:
            raise ErroPerfil(f"Erro de rede: {e}") from e

    def criar(self, nome: str) -> PerfilRemoto:
        try:
            r = requests.post(
                f"{self.base_url}/perfis",
                json={"nome": nome},
                headers=self._headers(),
                timeout=self.timeout,
            )
            if r.status_code == 409:
                p = self.obter(nome)
                if p is None:
                    raise ErroPerfil("409 mas nao achou")
                return p
            if r.status_code not in (200, 201):
                raise ErroPerfil(f"HTTP {r.status_code}")
            return PerfilRemoto(r.json())
        except requests.RequestException as e:
            raise ErroPerfil(f"Erro de rede: {e}") from e

    def atualizar(self, nome: str, bio: str, foto_path: str) -> PerfilRemoto:
        try:
            r = requests.put(
                f"{self.base_url}/perfis/{nome}",
                json={"bio": bio, "foto_path": foto_path},
                headers=self._headers(),
                timeout=self.timeout,
            )
            if r.status_code != 200:
                raise ErroPerfil(f"HTTP {r.status_code}")
            return PerfilRemoto(r.json())
        except requests.RequestException as e:
            raise ErroPerfil(f"Erro de rede: {e}") from e

    def definir_favoritos(self, nome: str, favoritos: list) -> list:
        try:
            r = requests.put(
                f"{self.base_url}/perfis/{nome}/favoritos",
                json={"favoritos": favoritos},
                headers=self._headers(),
                timeout=self.timeout,
            )
            if r.status_code != 200:
                raise ErroPerfil(f"HTTP {r.status_code}")
            return list(r.json().get("favoritos", []))
        except requests.RequestException as e:
            raise ErroPerfil(f"Erro de rede: {e}") from e
