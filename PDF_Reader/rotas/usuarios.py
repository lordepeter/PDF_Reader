"""Rotas públicas de usuários (busca).

Permite encontrar outros usuários pelo nome (case-insensitive, substring).
Nunca retorna senha_hash — só dados públicos.
"""
from fastapi import APIRouter, HTTPException, Depends, Query

from dominio.state import repo_usuarios
from rotas.auth import usuario_atual

router = APIRouter(prefix="/usuarios", tags=["Usuários"])

# ============================================================
# LISTAR TODOS OS USUÁRIOS
# (usada pela tela de Comunidade)
# ============================================================
@router.get("")
def listar_usuarios(usuario=Depends(usuario_atual)):
    """Retorna todos os usuários cadastrados, exceto o próprio solicitante.

    Ordenados alfabeticamente. Nunca retorna senha_hash.
    """
    outros = [u for u in repo_usuarios.usuarios if u.id != usuario.id]
    outros.sort(key=lambda u: u.nome.lower())

    return [
        {
            "id": u.id,
            "nome": u.nome,
            "criado_em": u.criado_em,
            "eu_mesmo": False,
        }
        for u in outros
    ]

@router.get("/buscar")
def buscar_usuarios(
    q: str = Query(..., min_length=1, max_length=30),
    usuario=Depends(usuario_atual),
):
    """Busca usuários por nome (case-insensitive, substring).

    Exemplo: `?q=chum` encontra "Chumbinho".
    Retorna no máximo 20 resultados, ordenados alfabeticamente.
    """
    termo = q.strip().casefold()
    if not termo:
        return []

    resultados = [
        u for u in repo_usuarios.usuarios
        if termo in u.nome.casefold()
    ]

    resultados.sort(key=lambda u: u.nome.lower())
    resultados = resultados[:20]

    return [
        {
            "id": u.id,
            "nome": u.nome,
            "criado_em": u.criado_em,
            "eu_mesmo": u.id == usuario.id,
        }
        for u in resultados
    ]