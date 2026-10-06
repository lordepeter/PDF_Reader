"""Camada de persistência — Repository Pattern.

A UI fala apenas com esses objetos. Hoje eles gravam em JSON local.
Amanhã, ao plugar uma API REST, basta criar as versões *API* dessas classes
com os mesmos métodos (ver Protocols abaixo) e injetar no composition root.
Nenhuma tela precisa mudar.
"""
from __future__ import annotations

import datetime
import json
import os
from typing import Dict, List, Optional, Protocol, runtime_checkable

from .models import (
    Review, Mensagem, ProgressoLeitura, Perfil, CatalogoItem,
    Usuario, Sessao, Amizade, Comentario, MensagemChat,
)

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
    def eh_favorito(self, perfil_id: str, obra_id: str) -> bool: ...
    def alternar_favorito(self, perfil_id: str, obra_id: str) -> tuple[bool, str]: ...
    def definir_favoritos(self, perfil_id: str, obra_ids: List[str]) -> None: ...


@runtime_checkable
class ReviewsRepositoryProtocol(Protocol):
    def listar_por_perfil(self, perfil: str) -> List[Review]: ...
    def listar_por_obra(self, obra: str, obra_id: Optional[str] = None) -> List[Review]: ...
    def media_da_obra(self, obra: str, obra_id: Optional[str] = None) -> tuple[float, int]: ...
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
    def obter_por_nome(self, nome: str) -> Optional[CatalogoItem]: ...

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
    LIMITE_FAVORITOS = 5 

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
    
    def _obter_por_id(self, perfil_id: str) -> Optional[Perfil]:
        return next((p for p in self.perfis if p.id == perfil_id), None)

    def eh_favorito(self, perfil_id: str, obra_id: str) -> bool:
        perfil = self._obter_por_id(perfil_id)
        if perfil is None:
            return False
        return obra_id in perfil.favoritos

    def alternar_favorito(self, perfil_id: str, obra_id: str) -> tuple[bool, str]:
        """Adiciona/remove dos favoritos. Retorna (sucesso, mensagem)."""
        perfil = self._obter_por_id(perfil_id)
        if perfil is None:
            return (False, "Perfil não encontrado.")

        # Já é favorito → remove
        if obra_id in perfil.favoritos:
            perfil.favoritos.remove(obra_id)
            self.atualizar(perfil)
            return (True, "Removido dos favoritos.")

        # Vai adicionar → checa o limite
        if len(perfil.favoritos) >= self.LIMITE_FAVORITOS:
            return (
                False,
                f"Você já tem {self.LIMITE_FAVORITOS} favoritos. "
                f"Desmarque um antes de adicionar outro.",
            )

        perfil.favoritos.append(obra_id)
        self.atualizar(perfil)
        return (True, "Adicionado aos favoritos.")

    def definir_favoritos(self, perfil_id: str, obra_ids: List[str]) -> None:
        """Substitui a lista inteira de favoritos (usado pelo seletor)."""
        perfil = self._obter_por_id(perfil_id)
        if perfil is None:
            return

        # Remove duplicatas mantendo ordem, e trunca no limite
        vistos = set()
        limpos: List[str] = []
        for oid in obra_ids:
            if oid in vistos:
                continue
            vistos.add(oid)
            limpos.append(oid)
            if len(limpos) >= self.LIMITE_FAVORITOS:
                break

        perfil.favoritos = limpos
        self.atualizar(perfil)


    def remover(self, nome: str) -> bool:
        """Remove um perfil pelo nome.

        Retorna False se:
        - O perfil não existe
        - É o último perfil (não deixa a lista vazia)

        Se o perfil removido era o ativo, muda o ativo para o primeiro restante.
        """
        perfil = self.obter(nome)
        if perfil is None:
            return False

        if len(self.perfis) <= 1:
            return False

        self.perfis = [p for p in self.perfis if p.nome != nome]

        if self.perfil_ativo == nome:
            self.perfil_ativo = self.perfis[0].nome

        self.salvar()
        return True


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

        # ---------- agregação por obra ----------


    def remover_por_perfil(self, perfil: str) -> int:
        """Remove todas as reviews de um perfil. Retorna quantas removeu."""
        antes = len(self.reviews)
        self.reviews = [r for r in self.reviews if r.perfil != perfil]
        removidas = antes - len(self.reviews)
        if removidas > 0:
            self.salvar()
        return removidas

    def _review_pertence_a_obra(self, review: Review, obra: str,
                                 obra_id: Optional[str]) -> bool:
        """Regra de match:
        - Se obra_id foi passado e a review tem obra_id → compara por id
        - Se a review NÃO tem obra_id → compara por nome (retrocompatibilidade)
        """
        if obra_id and review.obra_id:
            return review.obra_id == obra_id
        if not review.obra_id:
            return review.obra.casefold() == obra.casefold()
        return False

    def listar_por_obra(self, obra: str,
                        obra_id: Optional[str] = None) -> List[Review]:
        return [
            r for r in self.reviews
            if self._review_pertence_a_obra(r, obra, obra_id)
        ]

    def media_da_obra(self, obra: str,
                      obra_id: Optional[str] = None) -> tuple[float, int]:
        """Retorna (média arredondada a 2 casas, quantidade).
        Se não há reviews, retorna (0.0, 0)."""
        notas = [
            r.nota for r in self.reviews
            if self._review_pertence_a_obra(r, obra, obra_id)
        ]
        if not notas:
            return (0.0, 0)
        return (round(sum(notas) / len(notas), 2), len(notas))


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

    def obter_por_nome(self, nome: str) -> Optional[CatalogoItem]:
        alvo = nome.strip().casefold()
        return next(
            (i for i in self.itens if i.nome.strip().casefold() == alvo),
            None,
        )

# ============================================================
# USUÁRIOS (autenticação)
# ============================================================
class RepositorioUsuarios:
    def __init__(self, caminho_arquivo: str):
        self.caminho = caminho_arquivo
        self.usuarios: List[Usuario] = []
        self.carregar()

    def carregar(self) -> None:
        d = _ler_json(self.caminho)
        if not isinstance(d, dict):
            return
        brutos = d.get("usuarios", [])
        if isinstance(brutos, list):
            self.usuarios = [
                Usuario.from_dict(u) for u in brutos if isinstance(u, dict)
            ]

    def salvar(self) -> None:
        _salvar_json_atomico(self.caminho, {
            "usuarios": [u.to_dict() for u in self.usuarios],
        })

    def obter_por_nome(self, nome: str) -> Optional[Usuario]:
        """Busca case-insensitive (João = joão)."""
        alvo = nome.strip().casefold()
        return next(
            (u for u in self.usuarios if u.nome.casefold() == alvo),
            None,
        )

    def obter_por_id(self, usuario_id: str) -> Optional[Usuario]:
        return next((u for u in self.usuarios if u.id == usuario_id), None)

    def criar(self, nome: str, senha: str) -> Optional[Usuario]:
        """Cria um usuário. Retorna None se o nome já existe."""
        nome = nome.strip()
        if not nome:
            return None
        if self.obter_por_nome(nome) is not None:
            return None

        usuario = Usuario.novo(nome, senha)
        self.usuarios.append(usuario)
        self.salvar()
        return usuario

# ============================================================
# SESSÕES (autenticação via token)
# ============================================================
class RepositorioSessoes:
    def __init__(self, caminho_arquivo: str):
        self.caminho = caminho_arquivo
        self.sessoes: List[Sessao] = []
        self.carregar()

    def carregar(self) -> None:
        d = _ler_json(self.caminho)
        if not isinstance(d, dict):
            return
        brutos = d.get("sessoes", [])
        if isinstance(brutos, list):
            self.sessoes = [
                Sessao.from_dict(s) for s in brutos if isinstance(s, dict)
            ]

    def salvar(self) -> None:
        _salvar_json_atomico(self.caminho, {
            "sessoes": [s.to_dict() for s in self.sessoes],
        })

    def criar(self, usuario_id: str) -> Sessao:
        sessao = Sessao.nova(usuario_id)
        self.sessoes.append(sessao)
        self.salvar()
        return sessao

    def obter(self, token: str) -> Optional[Sessao]:
        return next((s for s in self.sessoes if s.token == token), None)

    def remover(self, token: str) -> bool:
        antes = len(self.sessoes)
        self.sessoes = [s for s in self.sessoes if s.token != token]
        if len(self.sessoes) < antes:
            self.salvar()
            return True
        return False

    def remover_por_usuario(self, usuario_id: str) -> int:
        """Remove todas as sessões de um usuário (útil no cascade delete)."""
        antes = len(self.sessoes)
        self.sessoes = [s for s in self.sessoes if s.usuario_id != usuario_id]
        removidas = antes - len(self.sessoes)
        if removidas > 0:
            self.salvar()
        return removidas

# ============================================================
# AMIZADES
# ============================================================
class RepositorioAmizades:
    def __init__(self, caminho_arquivo: str):
        self.caminho = caminho_arquivo
        self.amizades: List[Amizade] = []
        self.carregar()

    def carregar(self) -> None:
        d = _ler_json(self.caminho)
        if not isinstance(d, dict):
            return
        brutos = d.get("amizades", [])
        if isinstance(brutos, list):
            self.amizades = [
                Amizade.from_dict(a) for a in brutos if isinstance(a, dict)
            ]

    def salvar(self) -> None:
        _salvar_json_atomico(self.caminho, {
            "amizades": [a.to_dict() for a in self.amizades],
        })

    def obter(self, amizade_id: str) -> Optional[Amizade]:
        return next((a for a in self.amizades if a.id == amizade_id), None)

    def _existe_entre(self, u1: str, u2: str) -> Optional[Amizade]:
        """Retorna a amizade existente entre dois usuários, se houver."""
        for a in self.amizades:
            par = {a.solicitante_id, a.destinatario_id}
            if par == {u1, u2}:
                return a
        return None

    def enviar_pedido(self, solicitante_id: str,
                      destinatario_id: str) -> Optional[Amizade]:
        """Cria um pedido pendente. Retorna None se:
        - solicitante == destinatário (não dá pra ser amigo de si mesmo)
        - já existe amizade ou pedido entre os dois
        """
        if solicitante_id == destinatario_id:
            return None
        if self._existe_entre(solicitante_id, destinatario_id) is not None:
            return None

        nova = Amizade.nova(solicitante_id, destinatario_id)
        self.amizades.append(nova)
        self.salvar()
        return nova

    def aceitar(self, amizade_id: str, usuario_id: str) -> Optional[Amizade]:
        """Aceita um pedido. Só o destinatário pode aceitar."""
        a = self.obter(amizade_id)
        if a is None or a.status != "pendente":
            return None
        if a.destinatario_id != usuario_id:
            return None

        a.status = "aceita"
        a.respondido_em = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        self.salvar()
        return a

    def recusar(self, amizade_id: str, usuario_id: str) -> bool:
        """Recusa e apaga. Só o destinatário pode recusar."""
        a = self.obter(amizade_id)
        if a is None or a.status != "pendente":
            return False
        if a.destinatario_id != usuario_id:
            return False
        self.amizades = [x for x in self.amizades if x.id != amizade_id]
        self.salvar()
        return True

    def desfazer(self, amizade_id: str, usuario_id: str) -> bool:
        """Desfaz amizade. Qualquer um dos dois pode."""
        a = self.obter(amizade_id)
        if a is None:
            return False
        if usuario_id not in (a.solicitante_id, a.destinatario_id):
            return False
        self.amizades = [x for x in self.amizades if x.id != amizade_id]
        self.salvar()
        return True

    def listar_amigos(self, usuario_id: str) -> List[Amizade]:
        """Todas as amizades aceitas onde o usuário participa."""
        return [
            a for a in self.amizades
            if a.status == "aceita"
            and usuario_id in (a.solicitante_id, a.destinatario_id)
        ]

    def listar_pendentes_recebidos(self, usuario_id: str) -> List[Amizade]:
        """Pedidos pendentes que EU recebi (para aceitar/recusar)."""
        return [
            a for a in self.amizades
            if a.status == "pendente" and a.destinatario_id == usuario_id
        ]

    def listar_pendentes_enviados(self, usuario_id: str) -> List[Amizade]:
        """Pedidos que EU enviei e ainda não foram respondidos."""
        return [
            a for a in self.amizades
            if a.status == "pendente" and a.solicitante_id == usuario_id
        ]

    def sao_amigos(self, u1: str, u2: str) -> bool:
        a = self._existe_entre(u1, u2)
        return a is not None and a.status == "aceita"

    def remover_por_usuario(self, usuario_id: str) -> int:
        """Remove todas as amizades de um usuário (cascade delete)."""
        antes = len(self.amizades)
        self.amizades = [
            a for a in self.amizades
            if usuario_id not in (a.solicitante_id, a.destinatario_id)
        ]
        removidas = antes - len(self.amizades)
        if removidas > 0:
            self.salvar()
        return removidas

# ============================================================
# COMENTÁRIOS (mural de recados)
# ============================================================
class RepositorioComentarios:
    def __init__(self, caminho_arquivo: str):
        self.caminho = caminho_arquivo
        self.comentarios: List[Comentario] = []
        self.carregar()

    def carregar(self) -> None:
        d = _ler_json(self.caminho)
        if not isinstance(d, dict):
            return
        brutos = d.get("comentarios", [])
        if isinstance(brutos, list):
            self.comentarios = [
                Comentario.from_dict(c) for c in brutos if isinstance(c, dict)
            ]

    def salvar(self) -> None:
        _salvar_json_atomico(self.caminho, {
            "comentarios": [c.to_dict() for c in self.comentarios],
        })

    def obter(self, comentario_id: str) -> Optional[Comentario]:
        return next((c for c in self.comentarios if c.id == comentario_id), None)

    def criar(self, autor_id: str, autor_nome: str,
              alvo_id: str, texto: str) -> Comentario:
        comentario = Comentario.novo(autor_id, autor_nome, alvo_id, texto)
        self.comentarios.append(comentario)
        self.salvar()
        return comentario

    def listar_do_mural(self, alvo_id: str) -> List[Comentario]:
        """Todos os comentários em um perfil, mais recentes primeiro."""
        filtrados = [c for c in self.comentarios if c.alvo_id == alvo_id]
        filtrados.sort(key=lambda c: c.criado_em, reverse=True)
        return filtrados

    def remover(self, comentario_id: str, solicitante_id: str) -> bool:
        """Remove se o solicitante for o autor OU o dono do mural.

        Retorna False se não encontrou ou se não tem permissão.
        """
        c = self.obter(comentario_id)
        if c is None:
            return False

        # Permissão: autor ou dono do mural
        if solicitante_id not in (c.autor_id, c.alvo_id):
            return False

        self.comentarios = [x for x in self.comentarios if x.id != comentario_id]
        self.salvar()
        return True

    def remover_por_usuario(self, usuario_id: str) -> int:
        """Remove todos os comentários onde o usuário é autor OU alvo.
        Usado no cascade delete.
        """
        antes = len(self.comentarios)
        self.comentarios = [
            c for c in self.comentarios
            if usuario_id not in (c.autor_id, c.alvo_id)
        ]
        removidos = antes - len(self.comentarios)
        if removidos > 0:
            self.salvar()
        return removidos

# ============================================================
# CHAT PRIVADO (mensagens entre dois usuários)
# ============================================================
class RepositorioMensagensChat:
    def __init__(self, caminho_arquivo: str):
        self.caminho = caminho_arquivo
        self.mensagens: List[MensagemChat] = []
        self.carregar()

    def carregar(self) -> None:
        d = _ler_json(self.caminho)
        if not isinstance(d, dict):
            return
        brutos = d.get("mensagens", [])
        if isinstance(brutos, list):
            self.mensagens = [
                MensagemChat.from_dict(m) for m in brutos if isinstance(m, dict)
            ]

    def salvar(self) -> None:
        _salvar_json_atomico(self.caminho, {
            "mensagens": [m.to_dict() for m in self.mensagens],
        })

    def enviar(self, remetente_id: str, remetente_nome: str,
               destinatario_id: str, destinatario_nome: str,
               texto: str) -> MensagemChat:
        msg = MensagemChat.nova(remetente_id, remetente_nome,
                                 destinatario_id, destinatario_nome, texto)
        self.mensagens.append(msg)
        self.salvar()
        return msg

    def conversa_entre(self, u1: str, u2: str) -> List[MensagemChat]:
        """Todas as mensagens trocadas entre dois usuários, cronológico."""
        resultado = [
            m for m in self.mensagens
            if {m.remetente_id, m.destinatario_id} == {u1, u2}
        ]
        resultado.sort(key=lambda m: m.enviado_em)
        return resultado

    def novas_desde(self, u1: str, u2: str, desde: str) -> List[MensagemChat]:
        """Mensagens da conversa enviadas depois de `desde` (para polling)."""
        resultado = [
            m for m in self.conversa_entre(u1, u2)
            if m.enviado_em > desde
        ]
        return resultado

    def marcar_lidas(self, destinatario_id: str, remetente_id: str) -> int:
        """Marca como lidas todas as mensagens que o destinatário recebeu
        do remetente. Retorna quantas foram atualizadas."""
        alteradas = 0
        for m in self.mensagens:
            if (m.destinatario_id == destinatario_id
                    and m.remetente_id == remetente_id
                    and not m.lida):
                m.lida = True
                alteradas += 1
        if alteradas > 0:
            self.salvar()
        return alteradas

    def nao_lidas_de(self, destinatario_id: str, remetente_id: str) -> int:
        """Quantas mensagens não lidas do remetente para o destinatário."""
        return sum(
            1 for m in self.mensagens
            if m.destinatario_id == destinatario_id
            and m.remetente_id == remetente_id
            and not m.lida
        )

    def total_nao_lidas(self, usuario_id: str) -> int:
        """Total de mensagens não lidas para o usuário (badge geral)."""
        return sum(
            1 for m in self.mensagens
            if m.destinatario_id == usuario_id and not m.lida
        )

    def ultima_mensagem(self, u1: str, u2: str) -> Optional[MensagemChat]:
        conversa = self.conversa_entre(u1, u2)
        return conversa[-1] if conversa else None

    def remover_por_usuario(self, usuario_id: str) -> int:
        """Remove todas as mensagens onde o usuário é remetente OU destinatário."""
        antes = len(self.mensagens)
        self.mensagens = [
            m for m in self.mensagens
            if usuario_id not in (m.remetente_id, m.destinatario_id)
        ]
        removidas = antes - len(self.mensagens)
        if removidas > 0:
            self.salvar()
        return removidas