"""Cliente HTTP para as rotas /chat da API."""
from __future__ import annotations

import requests
from dataclasses import dataclass


class ErroChat(Exception):
    """Erro controlado nas operações de chat."""


@dataclass
class Conversa:
    amigo_id: str
    amigo_nome: str
    ultima_mensagem: str | None
    ultima_em: str | None
    nao_lidas: int


@dataclass
class MensagemChat:
    id: str
    remetente_id: str
    remetente_nome: str
    destinatario_id: str
    destinatario_nome: str
    texto: str
    enviado_em: str
    lida: bool


class RepositorioChatAPI:
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
            raise ErroChat(f"API offline: {e}") from e
        except requests.Timeout:
            raise ErroChat("API demorou demais para responder")

    def _post(self, caminho: str, dados: dict):
        try:
            return requests.post(
                f"{self.base_url}{caminho}",
                json=dados, headers=self._headers(), timeout=self.TIMEOUT,
            )
        except requests.ConnectionError as e:
            raise ErroChat(f"API offline: {e}") from e
        except requests.Timeout:
            raise ErroChat("API demorou demais para responder")

    # ---------- API pública ----------
    def listar_conversas(self) -> list[Conversa]:
        """Sidebar do chat: amigos com última mensagem + não lidas."""
        r = self._get("/chat")
        if r.status_code == 401:
            raise ErroChat("Sessão expirada")
        if r.status_code != 200:
            raise ErroChat(f"Erro ao listar conversas: {r.status_code}")
        return [
            Conversa(
                amigo_id=d["amigo_id"],
                amigo_nome=d["amigo_nome"],
                ultima_mensagem=d["ultima_mensagem"],
                ultima_em=d["ultima_em"],
                nao_lidas=d["nao_lidas"],
            )
            for d in r.json()
        ]

    def listar_mensagens(self, nome_amigo: str) -> list[MensagemChat]:
        r = self._get(f"/chat/{nome_amigo}")
        if r.status_code == 403:
            raise ErroChat("Vocês não são amigos")
        if r.status_code == 404:
            raise ErroChat(f"Usuário '{nome_amigo}' não existe")
        if r.status_code != 200:
            raise ErroChat(f"Erro ao listar mensagens: {r.status_code}")
        return [self._msg_from_dict(d) for d in r.json()]

    def novas_mensagens(self, nome_amigo: str, desde: str) -> list[MensagemChat]:
        """Polling: mensagens depois de `desde` (formato 'dd/mm/aaaa hh:mm')."""
        r = self._get(f"/chat/{nome_amigo}/novas?desde={desde}")
        if r.status_code != 200:
            raise ErroChat(f"Erro ao buscar novas: {r.status_code}")
        return [self._msg_from_dict(d) for d in r.json()]

    def enviar(self, nome_amigo: str, texto: str) -> MensagemChat:
        r = self._post(f"/chat/{nome_amigo}", {"texto": texto})
        if r.status_code == 403:
            raise ErroChat("Vocês não são amigos")
        if r.status_code == 404:
            raise ErroChat(f"Usuário '{nome_amigo}' não existe")
        if r.status_code == 422:
            raise ErroChat("Mensagem inválida (vazia ou muito longa)")
        if r.status_code != 201:
            raise ErroChat(f"Erro ao enviar: {r.status_code}")
        return self._msg_from_dict(r.json())

    # ---------- helpers ----------
    @staticmethod
    def _msg_from_dict(d: dict) -> MensagemChat:
        return MensagemChat(
            id=d["id"],
            remetente_id=d["remetente_id"],
            remetente_nome=d["remetente_nome"],
            destinatario_id=d["destinatario_id"],
            destinatario_nome=d["destinatario_nome"],
            texto=d["texto"],
            enviado_em=d["enviado_em"],
            lida=bool(d.get("lida", False)),
        )