"""Conexão com o banco Postgres (Neon) via SQLAlchemy.

Uso:
    from dominio.database import SessionLocal, criar_tabelas
    criar_tabelas()  # cria as tabelas se não existirem (idempotente)

Cada operação abre a própria sessão (`with SessionLocal() as s:`) para
evitar compartilhamento entre threads do uvicorn.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


# Carrega variáveis do .env (silencioso se não existir)
load_dotenv()


DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "Variável DATABASE_URL não encontrada. Crie um arquivo .env na raiz "
        "do projeto com a linha:\n"
        "DATABASE_URL=postgresql+psycopg://usuario:senha@host/dbname?sslmode=require"
    )


# ---------- Engine ----------
# pool_pre_ping evita erro "server closed the connection" depois de muito
# tempo sem uso (o Neon hiberna após 5 min de inatividade).
# pool_recycle força renovar conexões a cada 5 min.
engine = create_engine(
    DATABASE_URL,
    echo=False,          # troque para True pra ver o SQL no console
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=5,
    max_overflow=10,
)


# ---------- Session ----------
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# ---------- Base dos modelos ----------
class Base(DeclarativeBase):
    pass


# ---------- Criação de tabelas ----------
def criar_tabelas() -> None:
    """Cria todas as tabelas que ainda não existem. É seguro chamar várias vezes."""
    # Importa aqui pra registrar os modelos no metadata antes do create_all
    from . import tabelas  # noqa: F401
    Base.metadata.create_all(bind=engine)