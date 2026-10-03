"""Rotas de perfis da API.

Perfis são identificados por `nome` (não por ID) para ficar legível na URL.
Favoritos são gerenciados como sub-recurso: /perfis/{nome}/favoritos.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List

from dominio.models import Perfil

from dominio.repositories import ErroPersistencia
from dominio.state import repo_perfis as repo


router = APIRouter(prefix="/perfis", tags=["Perfis"])


# ---------- Esquemas Pydantic ----------
class PerfilEntrada(BaseModel):
    nome: str = Field(..., min_length=1, max_length=40)


class PerfilAtualizacao(BaseModel):
    bio: str = Field(default="", max_length=500)
    foto_path: str = Field(default="")


class FavoritosEntrada(BaseModel):
    favoritos: List[str] = Field(default_factory=list)


# ---------- READ (lista) ----------
@router.get("")
def listar_perfis():
    return [p.to_dict() for p in repo.perfis]


# ---------- READ (um) ----------
@router.get("/{nome}")
def obter_perfil(nome: str):
    perfil = repo.obter(nome)
    if perfil is None:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")
    return perfil.to_dict()


# ---------- CREATE ----------
@router.post("", status_code=201)
def criar_perfil(dados: PerfilEntrada):
    try:
        criado = repo.criar(dados.nome)
    except ErroPersistencia as e:
        raise HTTPException(status_code=500, detail=f"Erro ao criar: {e}")

    if not criado:
        raise HTTPException(
            status_code=409,
            detail=f"Já existe um perfil com o nome '{dados.nome}'",
        )

    # Devolve o perfil recém-criado
    perfil = repo.obter(dados.nome.strip())
    return perfil.to_dict()


# ---------- UPDATE ----------
@router.put("/{nome}")
def atualizar_perfil(nome: str, dados: PerfilAtualizacao):
    perfil = repo.obter(nome)
    if perfil is None:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    perfil.bio = dados.bio
    perfil.foto_path = dados.foto_path

    try:
        repo.atualizar(perfil)
    except ErroPersistencia as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar: {e}")

    return perfil.to_dict()


# ---------- FAVORITOS (sub-recurso) ----------
@router.get("/{nome}/favoritos")
def listar_favoritos(nome: str):
    perfil = repo.obter(nome)
    if perfil is None:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")
    return {"favoritos": perfil.favoritos}


@router.put("/{nome}/favoritos")
def definir_favoritos(nome: str, dados: FavoritosEntrada):
    perfil = repo.obter(nome)
    if perfil is None:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    if len(dados.favoritos) > repo.LIMITE_FAVORITOS:
        raise HTTPException(
            status_code=400,
            detail=f"Máximo de {repo.LIMITE_FAVORITOS} favoritos por perfil",
        )

    try:
        repo.definir_favoritos(perfil.id, dados.favoritos)
    except ErroPersistencia as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar: {e}")

    # Recarrega para pegar a lista normalizada (sem duplicatas, truncada)
    perfil_atualizado = repo.obter(nome)
    return {"favoritos": perfil_atualizado.favoritos}

# ---------- DELETE (com cascata) ----------
@router.delete("/{nome}", status_code=204)
def deletar_perfil(nome: str):
    """Remove um perfil E todas as suas reviews (cascade delete)."""
    from dominio.state import repo_reviews   # import tardio evita ciclo

    perfil = repo.obter(nome)
    if perfil is None:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    # Proteção: não permite remover o último perfil
    if len(repo.perfis) <= 1:
        raise HTTPException(
            status_code=400,
            detail="Não é possível remover o último perfil da lista",
        )

    try:
        # Cascata: remove as reviews do perfil PRIMEIRO
        # (se falhar, o perfil continua — estado consistente)
        repo_reviews.remover_por_perfil(perfil.nome)
        # Depois remove o perfil
        repo.remover(perfil.nome)
    except ErroPersistencia as e:
        raise HTTPException(status_code=500, detail=f"Erro ao remover: {e}")

    return None