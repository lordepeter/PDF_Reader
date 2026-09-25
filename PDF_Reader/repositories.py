"""Camada de persistência — Repository Pattern.

A UI fala apenas com esses objetos. Hoje eles gravam em JSON local.
Amanhã, ao plugar uma API REST, basta criar as versões *API* dessas classes
com os mesmos métodos (ver Protocols abaixo) e injetar no composition root.
Nenhuma tela precisa mudar.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Protocol, runtime_checkable

from models import Review, Mensagem, ProgressoLeitura, Perfil, CatalogoItem


# ============================================================
# ERROS CONTROLADOS
# ============================================================
class ErroPersistencia(Exception):
    """Erro controlado para a UI avisar o usuário sem quebrar o app."""


# ============================================================
# CONTRATOS (Protocol)
# ============================================================
@runtime_checkable
class ProgressoRepositoryProtocol(Protocol):
    def obter(self, chave: str) -> ProgressoLeitura: ...
    def definir(self, chave: str, progresso: ProgressoLeitura) -> None: ...
    def registrar_pagina(self, chave: str, pagina: int, total: int) -> None: ...
    def alternar_concluido(self, chave: str) -> ProgressoLeitura: ...


@runtime_checkable
class PerfisRepositoryProtocol(Protocol):
    perfis: List[Perfil]
    perfil_ativo: str

    def nomes(self) -> List[str]: ...
    def obter(self, nome: str) -> Optional[Perfil]: ...
    def criar(self, nome: str) -> bool: ...
    def atualizar(self, perfil: Perfil) -> None: ...
    def definir_ativo(self, nome: str) -> None: ...
    def ativo(self) -> Optional[Perfil]: ...


@runtime_checkable
class ReviewsRepositoryProtocol(Protocol):
    def listar_por_perfil(self, perfil: str) -> List[Review]: ...
    def obter(self, review_id: str) -> Optional[Review]: ...
    def adicionar(self, review: Review) -> None: ...
    def atualizar(self, review: Review) -> None: ...
    def remover(self, review_id: str) -> None: ...


@runtime_checkable
class ChatRepositoryProtocol(Protocol):
    amigos: List[str]

    def obter_conversa(self, amigo: str) -> List[Mensagem]: ...
    def adicionar_mensagem(self, amigo: str, mensagem: Mensagem) -> None: ...
    def adicionar_amigo(self, nome: str) -> bool: ...

@runtime_checkable
class CatalogoRepositoryProtocol(Protocol):
    def listar(self) -> List[CatalogoItem]: ...
    def obter(self, item_id: str) -> Optional[CatalogoItem]: ...

# ============================================================
# UTILITÁRIOS
# ============================================================
def _salvar_json_atomico(caminho: str, payload) -> None:
    """Escreve em arquivo temporário e renomeia — evita corrupção em crash."""
    tmp = caminho + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=4)
        os.replace(tmp, caminho)
    except OSError as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise ErroPersistencia(
            f"Falha ao salvar {os.path.basename(caminho)}: {e}"
        ) from e


def _ler_json(caminho: str):
    """Leitura defensiva: retorna None em qualquer falha em vez de estourar."""
    if not os.path.exists(caminho):
        return None
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, ValueError):
        return None


# ============================================================
# PROGRESSO DE LEITURA
# ============================================================
class RepositorioProgresso:
    def __init__(self, caminho_arquivo: str):
        self.caminho = caminho_arquivo
        self.dados: Dict[str, ProgressoLeitura] = {}
        self.carregar()

    def carregar(self) -> None:
        self.dados = {}
        bruto = _ler_json(self.caminho)
        if isinstance(bruto, dict):
            self.dados = {k: ProgressoLeitura.from_dict(v) for k, v in bruto.items()}

    def salvar(self) -> None:
        _salvar_json_atomico(
            self.caminho,
            {k: v.to_dict() for k, v in self.dados.items()},
        )

    def obter(self, chave: str) -> ProgressoLeitura:
        return self.dados.get(chave, ProgressoLeitura())

    def definir(self, chave: str, progresso: ProgressoLeitura) -> None:
        self.dados[chave] = progresso
        self.salvar()

    def registrar_pagina(self, chave: str, pagina: int, total: int) -> None:
        atual = self.obter(chave)
        atual.ultima_pagina = pagina
        # NOTA DE DESIGN: uma vez lido, permanece lido — mesmo se o usuário
        # voltar páginas depois. Para desmarcar, use `alternar_concluido`.
        if pagina >= total - 1:
            atual.concluido = True
        self.definir(chave, atual)

    def alternar_concluido(self, chave: str) -> ProgressoLeitura:
        atual = self.obter(chave)
        atual.concluido = not atual.concluido
        self.definir(chave, atual)
        return atual


# ============================================================
# PERFIS
# ============================================================
class RepositorioPerfis:
    PERFIL_PADRAO = "Leitor"

    def __init__(self, caminho_arquivo: str):
        self.caminho = caminho_arquivo
        self.perfis: List[Perfil] = []
        self.perfil_ativo: str = self.PERFIL_PADRAO
        self.carregar()
        if not self.perfis:
            self._criar_perfil_inicial()

    def _criar_perfil_inicial(self) -> None:
        padrao = Perfil.novo(self.PERFIL_PADRAO)
        self.perfis.append(padrao)
        self.perfil_ativo = padrao.nome
        self.salvar()

    def carregar(self) -> None:
        d = _ler_json(self.caminho)
        if not isinstance(d, dict):
            return
        brutos = d.get("perfis", [])
        if isinstance(brutos, list):
            self.perfis = [
                Perfil.from_dict(p) for p in brutos if isinstance(p, dict)
            ]
        ativo = d.get("perfil_ativo")
        if isinstance(ativo, str) and ativo:
            self.perfil_ativo = ativo

    def salvar(self) -> None:
        _salvar_json_atomico(self.caminho, {
            "perfis": [p.to_dict() for p in self.perfis],
            "perfil_ativo": self.perfil_ativo,
        })

    def nomes(self) -> List[str]:
        return [p.nome for p in self.perfis]

    def obter(self, nome: str) -> Optional[Perfil]:
        return next((p for p in self.perfis if p.nome == nome), None)

    def criar(self, nome: str) -> bool:
        nome = nome.strip()
        if not nome:
            return False
        if self.obter(nome) is not None:
            return False
        novo = Perfil.novo(nome)
        self.perfis.append(novo)
        self.perfil_ativo = novo.nome
        self.salvar()
        return True

    def atualizar(self, perfil: Perfil) -> None:
        for i, p in enumerate(self.perfis):
            if p.id == perfil.id:
                self.perfis[i] = perfil
                break
        self.salvar()

    def definir_ativo(self, nome: str) -> None:
        if self.obter(nome) is not None:
            self.perfil_ativo = nome
            self.salvar()

    def ativo(self) -> Optional[Perfil]:
        return self.obter(self.perfil_ativo)


# ============================================================
# REVIEWS (agora só reviews — perfil vive em RepositorioPerfis)
# ============================================================
class RepositorioReviews:
    def __init__(self, caminho_arquivo: str):
        self.caminho = caminho_arquivo
        self.reviews: List[Review] = []
        self.carregar()

    def carregar(self) -> None:
        d = _ler_json(self.caminho)
        if not isinstance(d, dict):
            return
        # Ignora "perfis"/"perfil_ativo" de arquivos antigos — migração suave.
        self.reviews = [
            Review.from_dict(r) for r in d.get("reviews", []) if isinstance(r, dict)
        ]

    def salvar(self) -> None:
        _salvar_json_atomico(self.caminho, {
            "reviews": [r.to_dict() for r in self.reviews],
        })

    def listar_por_perfil(self, perfil: str) -> List[Review]:
        return [r for r in self.reviews if r.perfil == perfil]

    def obter(self, review_id: str) -> Optional[Review]:
        return next((r for r in self.reviews if r.id == review_id), None)

    def adicionar(self, review: Review) -> None:
        self.reviews.append(review)
        self.salvar()

    def atualizar(self, review: Review) -> None:
        for i, r in enumerate(self.reviews):
            if r.id == review.id:
                self.reviews[i] = review
                break
        self.salvar()

    def remover(self, review_id: str) -> None:
        self.reviews = [r for r in self.reviews if r.id != review_id]
        self.salvar()


# ============================================================
# CHATOCHAT
# ============================================================
class RepositorioChat:
    AMIGOS_DEMO = [f"Amigo {i}" for i in range(1, 16)]

    def __init__(self, caminho_arquivo: str, modo_demo: bool = False):
        """modo_demo=True pré-popula 15 contatos fictícios quando não há arquivo.
        Use apenas para demonstração/portfólio."""
        self.caminho = caminho_arquivo
        self.modo_demo = modo_demo
        self.amigos: List[str] = []
        self.conversas: Dict[str, List[Mensagem]] = {}
        if modo_demo:
            self.amigos = list(self.AMIGOS_DEMO)
        self.carregar()

    def carregar(self) -> None:
        d = _ler_json(self.caminho)
        if not isinstance(d, dict):
            return
        amigos = d.get("amigos")
        if isinstance(amigos, list) and amigos:
            self.amigos = [str(a) for a in amigos]
        conversas = d.get("conversas", {})
        if isinstance(conversas, dict):
            self.conversas = {
                str(amigo): [Mensagem.from_dict(m) for m in msgs if isinstance(m, dict)]
                for amigo, msgs in conversas.items()
            }

    def salvar(self) -> None:
        _salvar_json_atomico(self.caminho, {
            "amigos": self.amigos,
            "conversas": {
                amigo: [m.to_dict() for m in msgs]
                for amigo, msgs in self.conversas.items()
            },
        })

    def obter_conversa(self, amigo: str) -> List[Mensagem]:
        return self.conversas.get(amigo, [])

    def adicionar_mensagem(self, amigo: str, mensagem: Mensagem) -> None:
        self.conversas.setdefault(amigo, []).append(mensagem)
        self.salvar()

    def adicionar_amigo(self, nome: str) -> bool:
        nome = nome.strip()
        if not nome:
            return False
        if any(a.casefold() == nome.casefold() for a in self.amigos):
            return False
        self.amigos.append(nome)
        self.conversas.setdefault(nome, [])
        self.salvar()
        return True

# ============================================================
# CATÁLOGO (obras disponíveis para download)
# ============================================================
class RepositorioCatalogo:
    """Lê o catálogo de um arquivo JSON local.

    Quando o backend existir, criamos `RepositorioCatalogoAPI` com os mesmos
    métodos (listar/obter) e trocamos no composition root. A UI não muda.
    """

    def __init__(self, caminho_arquivo: str):
        self.caminho = caminho_arquivo
        self.itens: List[CatalogoItem] = []
        self.carregar()

    def carregar(self) -> None:
        d = _ler_json(self.caminho)
        if not isinstance(d, dict):
            self.itens = []
            return
        brutos = d.get("obras", [])
        if isinstance(brutos, list):
            self.itens = [
                CatalogoItem.from_dict(i) for i in brutos if isinstance(i, dict)
            ]

    def salvar(self) -> None:
        _salvar_json_atomico(self.caminho, {
            "obras": [i.to_dict() for i in self.itens],
        })

    def listar(self) -> List[CatalogoItem]:
        return list(self.itens)

    def obter(self, item_id: str) -> Optional[CatalogoItem]:
        return next((i for i in self.itens if i.id == item_id), None)