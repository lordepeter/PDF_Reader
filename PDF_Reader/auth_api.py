"""Cliente HTTP para as rotas de autenticação da API.

Também contém o GerenciadorSessao, que guarda o token localmente em
session.json (é o que faz o "não perguntar de novo neste dispositivo").
"""
from __future__ import annotations

import json
import os
import requests
from dataclasses import dataclass
from typing import Optional


# ============================================================
# ERROS
# ============================================================
class ErroAuth(Exception):
    """Erro controlado nas operações de autenticação."""


# ============================================================
# RESULTADO DE LOGIN
# ============================================================
@dataclass
class SessaoLocal:
    """Dados do usuário logado (guardados localmente)."""
    usuario_id: str
    nome: str
    token: str


# ============================================================
# CLIENTE HTTP DE AUTENTICAÇÃO
# ============================================================
class RepositorioAuthAPI:
    """Fala com as rotas /auth/* da API REST."""

    TIMEOUT = 5

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    # ---------- internos ----------
    def _post(self, caminho: str, dados: dict, token: Optional[str] = None):
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            return requests.post(
                f"{self.base_url}{caminho}",
                json=dados,
                headers=headers,
                timeout=self.TIMEOUT,
            )
        except requests.ConnectionError as e:
            raise ErroAuth(f"API offline: {e}") from e
        except requests.Timeout:
            raise ErroAuth("API demorou demais para responder")

    # ---------- API pública ----------
    def registrar(self, nome: str, senha: str) -> SessaoLocal:
        """Registra um usuário. Não loga automaticamente — quem chamar
        deve chamar `login` depois."""
        r = self._post("/auth/registrar", {"nome": nome, "senha": senha})
        if r.status_code == 409:
            raise ErroAuth(f"Já existe um usuário com o nome '{nome}'")
        if r.status_code == 422:
            raise ErroAuth("Dados inválidos. Nome precisa ter 3+ caracteres, senha 4+.")
        if r.status_code != 201:
            raise ErroAuth(f"Erro no registro: {r.status_code}")

        dados = r.json()
        # Depois de registrar, faz login automaticamente
        return self.login(nome, senha)

    def login(self, nome: str, senha: str) -> SessaoLocal:
        """Faz login. Retorna a sessão local (com token)."""
        r = self._post("/auth/login", {"nome": nome, "senha": senha})
        if r.status_code == 401:
            raise ErroAuth("Nome ou senha inválidos")
        if r.status_code != 200:
            raise ErroAuth(f"Erro no login: {r.status_code}")

        dados = r.json()
        return SessaoLocal(
            usuario_id=dados["id"],
            nome=dados["nome"],
            token=dados["token"],
        )

    def logout(self, token: str) -> None:
        """Invalida a sessão no servidor. Falha silenciosa (o importante é
        apagar o token local mesmo se o servidor estiver offline)."""
        try:
            self._post("/auth/logout", {}, token=token)
        except ErroAuth:
            pass


# ============================================================
# GERENCIADOR DE SESSÃO LOCAL
# ============================================================
class GerenciadorSessao:
    """Guarda o token no arquivo `session.json` local.

    Isso é o que faz o app "lembrar" do usuário entre sessões — o
    famoso "não perguntar de novo neste dispositivo".
    """

    def __init__(self, caminho_arquivo: str):
        self.caminho = caminho_arquivo

    def salvar(self, sessao: SessaoLocal) -> None:
        try:
            with open(self.caminho, "w", encoding="utf-8") as f:
                json.dump({
                    "usuario_id": sessao.usuario_id,
                    "nome": sessao.nome,
                    "token": sessao.token,
                }, f, ensure_ascii=False, indent=2)
        except OSError as e:
            raise ErroAuth(f"Não foi possível salvar a sessão: {e}")

    def carregar(self) -> Optional[SessaoLocal]:
        if not os.path.exists(self.caminho):
            return None
        try:
            with open(self.caminho, "r", encoding="utf-8") as f:
                dados = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

        if not isinstance(dados, dict):
            return None

        token = dados.get("token")
        nome = dados.get("nome")
        usuario_id = dados.get("usuario_id")
        if not token or not nome or not usuario_id:
            return None

        return SessaoLocal(
            usuario_id=str(usuario_id),
            nome=str(nome),
            token=str(token),
        )

    def limpar(self) -> None:
        try:
            os.remove(self.caminho)
        except OSError:
            pass