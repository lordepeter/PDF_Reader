"""Camada de persistência — Repository Pattern com Postgres (SQLAlchemy).

A interface pública é IDÊNTICA à versão JSON anterior. As rotas
(`rotas/*.py`) não precisam mudar. O que muda é a implementação interna:
em vez de ler/escrever arquivos JSON, cada método abre uma sessão do
Postgres e executa queries SQLAlchemy.
"""
from __future__ import annotations

import datetime
import json
import os
import uuid
from typing import Dict, List, Optional

from sqlalchemy import select, delete, func
from sqlalchemy.orm import Session

from .models import (
    Review, Mensagem, ProgressoLeitura, Perfil, CatalogoItem,
    Usuario, Sessao, Amizade, Comentario, MensagemChat,
)
from .database import SessionLocal
from .tabelas import (
    UsuarioDB, SessaoDB, PerfilDB, ReviewDB,
    AmizadeDB, ComentarioDB, MensagemChatDB,
)


# ============================================================
# ERRO CONTROLADO (mantido pra compatibilidade)
# ============================================================
class ErroPersistencia(Exception):
    """Erro controlado para a UI avisar o usuário sem quebrar o app."""


# ============================================================
# HELPERS — conversão entre linha DB e dataclass de domínio
# ============================================================
def _favs_to_json(favs: list) -> str:
    return json.dumps(list(favs), ensure_ascii=False)


def _favs_from_json(raw: str | None) -> list:
    if not raw:
        return []
    try:
        dados = json.loads(raw)
        return [str(x) for x in dados] if isinstance(dados, list) else []
    except (ValueError, TypeError):
        return []


def _row_perfil(row: PerfilDB) -> Perfil:
    return Perfil(
        id=row.id,
        nome=row.nome,
        bio=row.bio or "",
        foto_path=row.foto_path or "",
        favoritos=_favs_from_json(row.favoritos_json),
        criado_em=row.criado_em or "",
    )


def _row_review(row: ReviewDB) -> Review:
    return Review(
        id=row.id,
        perfil=row.perfil,
        obra=row.obra,
        nota=row.nota,
        texto=row.texto or "",
        data=row.data,
        editada_em=row.editada_em,
        obra_id=row.obra_id,
    )


def _row_usuario(row: UsuarioDB) -> Usuario:
    return Usuario(
        id=row.id,
        nome=row.nome,
        senha_hash=row.senha_hash,
        criado_em=row.criado_em,
    )


def _row_sessao(row: SessaoDB) -> Sessao:
    return Sessao(
        token=row.token,
        usuario_id=row.usuario_id,
        criado_em=row.criado_em,
    )


def _row_amizade(row: AmizadeDB) -> Amizade:
    return Amizade(
        id=row.id,
        solicitante_id=row.solicitante_id,
        destinatario_id=row.destinatario_id,
        status=row.status,
        criado_em=row.criado_em,
        respondido_em=row.respondido_em,
    )


def _row_comentario(row: ComentarioDB) -> Comentario:
    return Comentario(
        id=row.id,
        autor_id=row.autor_id,
        autor_nome=row.autor_nome,
        alvo_id=row.alvo_id,
        texto=row.texto,
        criado_em=row.criado_em,
    )


def _row_msg_chat(row: MensagemChatDB) -> MensagemChat:
    return MensagemChat(
        id=row.id,
        remetente_id=row.remetente_id,
        remetente_nome=row.remetente_nome,
        destinatario_id=row.destinatario_id,
        destinatario_nome=row.destinatario_nome,
        texto=row.texto,
        enviado_em=row.enviado_em,
        lida=bool(row.lida),
    )


# ============================================================
# PERFIS
# ============================================================
class RepositorioPerfis:
    PERFIL_PADRAO = "Leitor"
    LIMITE_FAVORITOS = 5

    def __init__(self):
        """Garante que exista pelo menos o perfil padrão."""
        self._criar_perfil_inicial_se_vazio()

    def _criar_perfil_inicial_se_vazio(self) -> None:
        try:
            with SessionLocal() as session:
                total = session.scalar(select(func.count()).select_from(PerfilDB))
                if total and total > 0:
                    return
                padrao = Perfil.novo(self.PERFIL_PADRAO)
                session.add(PerfilDB(
                    id=padrao.id,
                    nome=padrao.nome,
                    bio=padrao.bio,
                    foto_path=padrao.foto_path,
                    favoritos_json=_favs_to_json(padrao.favoritos),
                    criado_em=padrao.criado_em,
                ))
                session.commit()
        except Exception as e:
            raise ErroPersistencia(f"Erro ao criar perfil padrão: {e}") from e

    @property
    def perfis(self) -> List[Perfil]:
        """Compatibilidade: alguns lugares acessam `.perfis` diretamente."""
        with SessionLocal() as session:
            rows = session.scalars(select(PerfilDB)).all()
            return [_row_perfil(r) for r in rows]

    def nomes(self) -> List[str]:
        with SessionLocal() as session:
            return list(session.scalars(select(PerfilDB.nome)).all())

    def obter(self, nome: str) -> Optional[Perfil]:
        with SessionLocal() as session:
            row = session.scalar(select(PerfilDB).where(PerfilDB.nome == nome))
            return _row_perfil(row) if row else None

    def criar(self, nome: str) -> bool:
        nome = nome.strip()
        if not nome:
            return False
        with SessionLocal() as session:
            existe = session.scalar(select(PerfilDB).where(PerfilDB.nome == nome))
            if existe:
                return False
            novo = Perfil.novo(nome)
            session.add(PerfilDB(
                id=novo.id,
                nome=novo.nome,
                bio=novo.bio,
                foto_path=novo.foto_path,
                favoritos_json=_favs_to_json(novo.favoritos),
                criado_em=novo.criado_em,
            ))
            session.commit()
            return True

    def atualizar(self, perfil: Perfil) -> None:
        with SessionLocal() as session:
            row = session.get(PerfilDB, perfil.id)
            if row is None:
                return
            row.nome = perfil.nome
            row.bio = perfil.bio
            row.foto_path = perfil.foto_path
            row.favoritos_json = _favs_to_json(perfil.favoritos)
            row.criado_em = perfil.criado_em
            session.commit()

    def _obter_por_id(self, perfil_id: str) -> Optional[Perfil]:
        with SessionLocal() as session:
            row = session.get(PerfilDB, perfil_id)
            return _row_perfil(row) if row else None

    def eh_favorito(self, perfil_id: str, obra_id: str) -> bool:
        perfil = self._obter_por_id(perfil_id)
        if perfil is None:
            return False
        return obra_id in perfil.favoritos

    def alternar_favorito(self, perfil_id: str, obra_id: str) -> tuple[bool, str]:
        perfil = self._obter_por_id(perfil_id)
        if perfil is None:
            return (False, "Perfil não encontrado.")

        if obra_id in perfil.favoritos:
            perfil.favoritos.remove(obra_id)
            self.atualizar(perfil)
            return (True, "Removido dos favoritos.")

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
        perfil = self._obter_por_id(perfil_id)
        if perfil is None:
            return
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
        with SessionLocal() as session:
            total = session.scalar(select(func.count()).select_from(PerfilDB))
            if not total or total <= 1:
                return False
            row = session.scalar(select(PerfilDB).where(PerfilDB.nome == nome))
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True


# ============================================================
# REVIEWS
# ============================================================
class RepositorioReviews:
    def __init__(self):
        pass

    @property
    def reviews(self) -> List[Review]:
        with SessionLocal() as session:
            rows = session.scalars(select(ReviewDB)).all()
            return [_row_review(r) for r in rows]

    def listar_por_perfil(self, perfil: str) -> List[Review]:
        with SessionLocal() as session:
            rows = session.scalars(
                select(ReviewDB).where(ReviewDB.perfil == perfil)
            ).all()
            return [_row_review(r) for r in rows]

    def obter(self, review_id: str) -> Optional[Review]:
        with SessionLocal() as session:
            row = session.get(ReviewDB, review_id)
            return _row_review(row) if row else None

    def adicionar(self, review: Review) -> None:
        with SessionLocal() as session:
            session.add(ReviewDB(
                id=review.id,
                perfil=review.perfil,
                obra=review.obra,
                obra_id=review.obra_id,
                nota=review.nota,
                texto=review.texto,
                data=review.data,
                editada_em=review.editada_em,
            ))
            session.commit()

    def atualizar(self, review: Review) -> None:
        with SessionLocal() as session:
            row = session.get(ReviewDB, review.id)
            if row is None:
                return
            row.perfil = review.perfil
            row.obra = review.obra
            row.obra_id = review.obra_id
            row.nota = review.nota
            row.texto = review.texto
            row.data = review.data
            row.editada_em = review.editada_em
            session.commit()

    def remover(self, review_id: str) -> None:
        with SessionLocal() as session:
            row = session.get(ReviewDB, review_id)
            if row:
                session.delete(row)
                session.commit()

    def remover_por_perfil(self, perfil: str) -> int:
        with SessionLocal() as session:
            result = session.execute(
                delete(ReviewDB).where(ReviewDB.perfil == perfil)
            )
            session.commit()
            return result.rowcount or 0

    def _review_pertence_a_obra(self, review: Review, obra: str,
                                 obra_id: Optional[str]) -> bool:
        if obra_id and review.obra_id:
            return review.obra_id == obra_id
        if not review.obra_id:
            return review.obra.casefold() == obra.casefold()
        return False

    def listar_por_obra(self, obra: str,
                        obra_id: Optional[str] = None) -> List[Review]:
        todas = self.reviews
        return [
            r for r in todas
            if self._review_pertence_a_obra(r, obra, obra_id)
        ]

    def media_da_obra(self, obra: str,
                      obra_id: Optional[str] = None) -> tuple[float, int]:
        notas = [
            r.nota for r in self.reviews
            if self._review_pertence_a_obra(r, obra, obra_id)
        ]
        if not notas:
            return (0.0, 0)
        return (round(sum(notas) / len(notas), 2), len(notas))


# ============================================================
# USUÁRIOS
# ============================================================
class RepositorioUsuarios:
    def __init__(self):
        pass

    @property
    def usuarios(self) -> List[Usuario]:
        with SessionLocal() as session:
            rows = session.scalars(select(UsuarioDB)).all()
            return [_row_usuario(r) for r in rows]

    def obter_por_nome(self, nome: str) -> Optional[Usuario]:
        alvo = nome.strip().casefold()
        with SessionLocal() as session:
            rows = session.scalars(select(UsuarioDB)).all()
            for row in rows:
                if row.nome.casefold() == alvo:
                    return _row_usuario(row)
            return None

    def obter_por_id(self, usuario_id: str) -> Optional[Usuario]:
        with SessionLocal() as session:
            row = session.get(UsuarioDB, usuario_id)
            return _row_usuario(row) if row else None

    def criar(self, nome: str, senha: str) -> Optional[Usuario]:
        nome = nome.strip()
        if not nome:
            return None
        if self.obter_por_nome(nome) is not None:
            return None
        usuario = Usuario.novo(nome, senha)
        with SessionLocal() as session:
            session.add(UsuarioDB(
                id=usuario.id,
                nome=usuario.nome,
                senha_hash=usuario.senha_hash,
                criado_em=usuario.criado_em,
            ))
            session.commit()
        return usuario


# ============================================================
# SESSÕES
# ============================================================
class RepositorioSessoes:
    def __init__(self):
        pass

    @property
    def sessoes(self) -> List[Sessao]:
        with SessionLocal() as session:
            rows = session.scalars(select(SessaoDB)).all()
            return [_row_sessao(r) for r in rows]

    def criar(self, usuario_id: str) -> Sessao:
        sessao = Sessao.nova(usuario_id)
        with SessionLocal() as db:
            db.add(SessaoDB(
                token=sessao.token,
                usuario_id=sessao.usuario_id,
                criado_em=sessao.criado_em,
            ))
            db.commit()
        return sessao

    def obter(self, token: str) -> Optional[Sessao]:
        with SessionLocal() as session:
            row = session.get(SessaoDB, token)
            return _row_sessao(row) if row else None

    def remover(self, token: str) -> bool:
        with SessionLocal() as session:
            row = session.get(SessaoDB, token)
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True

    def remover_por_usuario(self, usuario_id: str) -> int:
        with SessionLocal() as session:
            result = session.execute(
                delete(SessaoDB).where(SessaoDB.usuario_id == usuario_id)
            )
            session.commit()
            return result.rowcount or 0


# ============================================================
# AMIZADES
# ============================================================
class RepositorioAmizades:
    def __init__(self):
        pass

    @property
    def amizades(self) -> List[Amizade]:
        with SessionLocal() as session:
            rows = session.scalars(select(AmizadeDB)).all()
            return [_row_amizade(r) for r in rows]

    def obter(self, amizade_id: str) -> Optional[Amizade]:
        with SessionLocal() as session:
            row = session.get(AmizadeDB, amizade_id)
            return _row_amizade(row) if row else None

    def _existe_entre(self, u1: str, u2: str) -> Optional[Amizade]:
        with SessionLocal() as session:
            rows = session.scalars(select(AmizadeDB)).all()
            for row in rows:
                par = {row.solicitante_id, row.destinatario_id}
                if par == {u1, u2}:
                    return _row_amizade(row)
            return None

    def enviar_pedido(self, solicitante_id: str,
                      destinatario_id: str) -> Optional[Amizade]:
        if solicitante_id == destinatario_id:
            return None
        if self._existe_entre(solicitante_id, destinatario_id) is not None:
            return None
        nova = Amizade.nova(solicitante_id, destinatario_id)
        with SessionLocal() as session:
            session.add(AmizadeDB(
                id=nova.id,
                solicitante_id=nova.solicitante_id,
                destinatario_id=nova.destinatario_id,
                status=nova.status,
                criado_em=nova.criado_em,
                respondido_em=nova.respondido_em,
            ))
            session.commit()
        return nova

    def aceitar(self, amizade_id: str, usuario_id: str) -> Optional[Amizade]:
        with SessionLocal() as session:
            row = session.get(AmizadeDB, amizade_id)
            if row is None or row.status != "pendente":
                return None
            if row.destinatario_id != usuario_id:
                return None
            row.status = "aceita"
            row.respondido_em = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
            session.commit()
            return _row_amizade(row)

    def recusar(self, amizade_id: str, usuario_id: str) -> bool:
        with SessionLocal() as session:
            row = session.get(AmizadeDB, amizade_id)
            if row is None or row.status != "pendente":
                return False
            if row.destinatario_id != usuario_id:
                return False
            session.delete(row)
            session.commit()
            return True

    def desfazer(self, amizade_id: str, usuario_id: str) -> bool:
        with SessionLocal() as session:
            row = session.get(AmizadeDB, amizade_id)
            if row is None:
                return False
            if usuario_id not in (row.solicitante_id, row.destinatario_id):
                return False
            session.delete(row)
            session.commit()
            return True

    def listar_amigos(self, usuario_id: str) -> List[Amizade]:
        with SessionLocal() as session:
            rows = session.scalars(
                select(AmizadeDB).where(
                    AmizadeDB.status == "aceita",
                    (AmizadeDB.solicitante_id == usuario_id)
                    | (AmizadeDB.destinatario_id == usuario_id),
                )
            ).all()
            return [_row_amizade(r) for r in rows]

    def listar_pendentes_recebidos(self, usuario_id: str) -> List[Amizade]:
        with SessionLocal() as session:
            rows = session.scalars(
                select(AmizadeDB).where(
                    AmizadeDB.status == "pendente",
                    AmizadeDB.destinatario_id == usuario_id,
                )
            ).all()
            return [_row_amizade(r) for r in rows]

    def listar_pendentes_enviados(self, usuario_id: str) -> List[Amizade]:
        with SessionLocal() as session:
            rows = session.scalars(
                select(AmizadeDB).where(
                    AmizadeDB.status == "pendente",
                    AmizadeDB.solicitante_id == usuario_id,
                )
            ).all()
            return [_row_amizade(r) for r in rows]

    def sao_amigos(self, u1: str, u2: str) -> bool:
        a = self._existe_entre(u1, u2)
        return a is not None and a.status == "aceita"

    def remover_por_usuario(self, usuario_id: str) -> int:
        with SessionLocal() as session:
            result = session.execute(
                delete(AmizadeDB).where(
                    (AmizadeDB.solicitante_id == usuario_id)
                    | (AmizadeDB.destinatario_id == usuario_id)
                )
            )
            session.commit()
            return result.rowcount or 0


# ============================================================
# COMENTÁRIOS
# ============================================================
class RepositorioComentarios:
    def __init__(self):
        pass

    @property
    def comentarios(self) -> List[Comentario]:
        with SessionLocal() as session:
            rows = session.scalars(select(ComentarioDB)).all()
            return [_row_comentario(r) for r in rows]

    def obter(self, comentario_id: str) -> Optional[Comentario]:
        with SessionLocal() as session:
            row = session.get(ComentarioDB, comentario_id)
            return _row_comentario(row) if row else None

    def criar(self, autor_id: str, autor_nome: str,
              alvo_id: str, texto: str) -> Comentario:
        c = Comentario.novo(autor_id, autor_nome, alvo_id, texto)
        with SessionLocal() as session:
            session.add(ComentarioDB(
                id=c.id,
                autor_id=c.autor_id,
                autor_nome=c.autor_nome,
                alvo_id=c.alvo_id,
                texto=c.texto,
                criado_em=c.criado_em,
            ))
            session.commit()
        return c

    def listar_do_mural(self, alvo_id: str) -> List[Comentario]:
        with SessionLocal() as session:
            rows = session.scalars(
                select(ComentarioDB).where(ComentarioDB.alvo_id == alvo_id)
            ).all()
            lista = [_row_comentario(r) for r in rows]
            lista.sort(key=lambda c: c.criado_em, reverse=True)
            return lista

    def remover(self, comentario_id: str, solicitante_id: str) -> bool:
        with SessionLocal() as session:
            row = session.get(ComentarioDB, comentario_id)
            if row is None:
                return False
            if solicitante_id not in (row.autor_id, row.alvo_id):
                return False
            session.delete(row)
            session.commit()
            return True

    def remover_por_usuario(self, usuario_id: str) -> int:
        with SessionLocal() as session:
            result = session.execute(
                delete(ComentarioDB).where(
                    (ComentarioDB.autor_id == usuario_id)
                    | (ComentarioDB.alvo_id == usuario_id)
                )
            )
            session.commit()
            return result.rowcount or 0


# ============================================================
# MENSAGENS DE CHAT
# ============================================================
class RepositorioMensagensChat:
    def __init__(self):
        pass

    @property
    def mensagens(self) -> List[MensagemChat]:
        with SessionLocal() as session:
            rows = session.scalars(select(MensagemChatDB)).all()
            return [_row_msg_chat(r) for r in rows]

    def enviar(self, remetente_id: str, remetente_nome: str,
               destinatario_id: str, destinatario_nome: str,
               texto: str) -> MensagemChat:
        msg = MensagemChat.nova(remetente_id, remetente_nome,
                                 destinatario_id, destinatario_nome, texto)
        with SessionLocal() as session:
            session.add(MensagemChatDB(
                id=msg.id,
                remetente_id=msg.remetente_id,
                remetente_nome=msg.remetente_nome,
                destinatario_id=msg.destinatario_id,
                destinatario_nome=msg.destinatario_nome,
                texto=msg.texto,
                enviado_em=msg.enviado_em,
                lida=msg.lida,
            ))
            session.commit()
        return msg

    def conversa_entre(self, u1: str, u2: str) -> List[MensagemChat]:
        with SessionLocal() as session:
            rows = session.scalars(
                select(MensagemChatDB).where(
                    ((MensagemChatDB.remetente_id == u1)
                     & (MensagemChatDB.destinatario_id == u2))
                    | ((MensagemChatDB.remetente_id == u2)
                       & (MensagemChatDB.destinatario_id == u1))
                )
            ).all()
            lista = [_row_msg_chat(r) for r in rows]
            lista.sort(key=lambda m: m.enviado_em)
            return lista

    def novas_desde(self, u1: str, u2: str, desde: str) -> List[MensagemChat]:
        return [m for m in self.conversa_entre(u1, u2) if m.enviado_em > desde]

    def marcar_lidas(self, destinatario_id: str, remetente_id: str) -> int:
        with SessionLocal() as session:
            rows = session.scalars(
                select(MensagemChatDB).where(
                    MensagemChatDB.destinatario_id == destinatario_id,
                    MensagemChatDB.remetente_id == remetente_id,
                    MensagemChatDB.lida == False,  # noqa: E712
                )
            ).all()
            for row in rows:
                row.lida = True
            if rows:
                session.commit()
            return len(rows)

    def nao_lidas_de(self, destinatario_id: str, remetente_id: str) -> int:
        with SessionLocal() as session:
            total = session.scalar(
                select(func.count()).select_from(MensagemChatDB).where(
                    MensagemChatDB.destinatario_id == destinatario_id,
                    MensagemChatDB.remetente_id == remetente_id,
                    MensagemChatDB.lida == False,  # noqa: E712
                )
            )
            return total or 0

    def total_nao_lidas(self, usuario_id: str) -> int:
        with SessionLocal() as session:
            total = session.scalar(
                select(func.count()).select_from(MensagemChatDB).where(
                    MensagemChatDB.destinatario_id == usuario_id,
                    MensagemChatDB.lida == False,  # noqa: E712
                )
            )
            return total or 0

    def ultima_mensagem(self, u1: str, u2: str) -> Optional[MensagemChat]:
        conv = self.conversa_entre(u1, u2)
        return conv[-1] if conv else None

    def remover_por_usuario(self, usuario_id: str) -> int:
        with SessionLocal() as session:
            result = session.execute(
                delete(MensagemChatDB).where(
                    (MensagemChatDB.remetente_id == usuario_id)
                    | (MensagemChatDB.destinatario_id == usuario_id)
                )
            )
            session.commit()
            return result.rowcount or 0

# ============================================================
# CATÁLOGO — continua baseado em JSON (read-only, não muda)
# ============================================================
import os
import uuid
from .models import CatalogoItem


def _ler_json(caminho: str):
    if not os.path.exists(caminho):
        return None
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            import json as _json
            return _json.load(f)
    except (OSError, ValueError):
        return None


class RepositorioCatalogo:
    """Lê o catálogo de um arquivo JSON local.

    Não migra pro Postgres porque é dado estático, read-only,
    versionado junto com o código.
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
# PROGRESSO — continua em JSON local (só usado no desktop)
# ============================================================
class RepositorioProgresso:
    """Não migra pro Postgres — o progresso de leitura é por máquina,
    não precisa sincronizar entre dispositivos.
    """
    def __init__(self, caminho_arquivo: str):
        self.caminho = caminho_arquivo
        self.dados: Dict[str, ProgressoLeitura] = {}
        self.carregar()

    def carregar(self) -> None:
        self.dados = {}
        bruto = _ler_json(self.caminho)
        if isinstance(bruto, dict):
            self.dados = {
                k: ProgressoLeitura.from_dict(v) for k, v in bruto.items()
            }

    def obter(self, chave: str) -> ProgressoLeitura:
        return self.dados.get(chave, ProgressoLeitura())

    def registrar_pagina(self, chave: str, pagina: int, total: int) -> None:
        atual = self.obter(chave)
        atual.ultima_pagina = pagina
        if pagina >= total - 1:
            atual.concluido = True
        self.dados[chave] = atual

    def alternar_concluido(self, chave: str) -> ProgressoLeitura:
        atual = self.obter(chave)
        atual.concluido = not atual.concluido
        self.dados[chave] = atual
        return atual