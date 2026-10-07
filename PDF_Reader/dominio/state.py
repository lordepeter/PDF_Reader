"""Estado compartilhado da API.

Com Postgres, os repositórios são apenas wrappers finos em cima do banco.
Cada método abre sua própria sessão, então não há mais o problema de
"dois routers sobrescrevendo o mesmo arquivo".

Ainda mantemos o padrão singleton — os objetos são criados uma vez aqui
e importados pelos routers.
"""
from .database import criar_tabelas
from .repositories import (
    RepositorioPerfis,
    RepositorioReviews,
    RepositorioCatalogo,   # <- ainda é JSON! catálogo é read-only
    RepositorioUsuarios,
    RepositorioSessoes,
    RepositorioAmizades,
    RepositorioComentarios,
    RepositorioMensagensChat,
)


# ---------- Cria as tabelas na primeira execução ----------
# É idempotente: se já existirem, não faz nada.
criar_tabelas()


# ---------- Instâncias únicas (singletons) ----------
repo_perfis = RepositorioPerfis()
repo_reviews = RepositorioReviews()
repo_catalogo = RepositorioCatalogo("catalogo.json")   # mantido em JSON
repo_usuarios = RepositorioUsuarios()
repo_sessoes = RepositorioSessoes()
repo_amizades = RepositorioAmizades()
repo_comentarios = RepositorioComentarios()
repo_chat = RepositorioMensagensChat()