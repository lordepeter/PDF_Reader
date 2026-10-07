"""Modelos SQLAlchemy — representação das tabelas no Postgres.

Cada classe mapeia uma tabela. Os campos são propositalmente simples (String,
Integer, Boolean, Text) pra facilitar migração futura via Alembic.

Datas são armazenadas como String no formato "dd/mm/YYYY HH:MM" — mesmo
formato que já existe nos JSONs, pra não quebrar dados antigos.
"""
from __future__ import annotations

from sqlalchemy import Boolean, Column, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class UsuarioDB(Base):
    __tablename__ = "usuarios"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    nome: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    senha_hash: Mapped[str] = mapped_column(String, nullable=False)
    criado_em: Mapped[str] = mapped_column(String, nullable=False)


class SessaoDB(Base):
    __tablename__ = "sessoes"

    token: Mapped[str] = mapped_column(String, primary_key=True)
    usuario_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    criado_em: Mapped[str] = mapped_column(String, nullable=False)


class PerfilDB(Base):
    __tablename__ = "perfis"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    nome: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    bio: Mapped[str] = mapped_column(Text, default="")
    foto_path: Mapped[str] = mapped_column(String, default="")
    # Lista de IDs de obras favoritas serializada como JSON string.
    # Ex: '["liv-001", "mng-003"]'
    favoritos_json: Mapped[str] = mapped_column(Text, default="[]")
    criado_em: Mapped[str] = mapped_column(String, nullable=False)


class ReviewDB(Base):
    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    perfil: Mapped[str] = mapped_column(String, nullable=False, index=True)
    obra: Mapped[str] = mapped_column(String, nullable=False)
    obra_id: Mapped[str | None] = mapped_column(String, nullable=True)
    nota: Mapped[int] = mapped_column(Integer, nullable=False)
    texto: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[str] = mapped_column(String, nullable=False)
    editada_em: Mapped[str | None] = mapped_column(String, nullable=True)


class AmizadeDB(Base):
    __tablename__ = "amizades"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    solicitante_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    destinatario_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False)  # pendente | aceita
    criado_em: Mapped[str] = mapped_column(String, nullable=False)
    respondido_em: Mapped[str | None] = mapped_column(String, nullable=True)


class ComentarioDB(Base):
    __tablename__ = "comentarios"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    autor_id: Mapped[str] = mapped_column(String, nullable=False)
    autor_nome: Mapped[str] = mapped_column(String, nullable=False)
    alvo_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    criado_em: Mapped[str] = mapped_column(String, nullable=False)


class MensagemChatDB(Base):
    __tablename__ = "mensagens_chat"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    remetente_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    remetente_nome: Mapped[str] = mapped_column(String, nullable=False)
    destinatario_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    destinatario_nome: Mapped[str] = mapped_column(String, nullable=False)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    enviado_em: Mapped[str] = mapped_column(String, nullable=False, index=True)
    lida: Mapped[bool] = mapped_column(Boolean, default=False)