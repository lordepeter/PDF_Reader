"""Rotas de reviews da API.

As rotas só traduzem HTTP para chamadas do repositório.
A persistência fica inteiramente com o RepositorioReviews.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from dominio.models import Review
from dominio.repositories import ErroPersistencia
from dominio.state import repo_reviews as repo

router = APIRouter(prefix="/reviews", tags=["Reviews"])



# ---------- Esquemas Pydantic ----------
class ReviewEntrada(BaseModel):
    perfil: str = Field(..., min_length=1)
    obra: str = Field(..., min_length=1)
    nota: int = Field(..., ge=1, le=5)
    texto: str = Field(..., min_length=1)


# ---------- CREATE ----------
@router.post("", status_code=201)
def criar_review(dados: ReviewEntrada):
    review = Review.nova(
        perfil=dados.perfil,
        obra=dados.obra,
        nota=dados.nota,
        texto=dados.texto,
    )
    try:
        repo.adicionar(review)
    except ErroPersistencia as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar: {e}")
    return review.to_dict()


# ---------- READ (lista) ----------
@router.get("")
def listar_reviews():
    return [r.to_dict() for r in repo.reviews]


# ---------- READ (um) ----------
@router.get("/{review_id}")
def obter_review(review_id: str):
    review = repo.obter(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review não encontrada")
    return review.to_dict()


# ---------- UPDATE ----------
@router.put("/{review_id}")
def atualizar_review(review_id: str, dados: ReviewEntrada):
    review = repo.obter(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review não encontrada")

    review.perfil = dados.perfil
    review.obra = dados.obra
    review.nota = dados.nota
    review.texto = dados.texto

    try:
        repo.atualizar(review)
    except ErroPersistencia as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar: {e}")
    return review.to_dict()


# ---------- DELETE ----------
@router.delete("/{review_id}", status_code=204)
def deletar_review(review_id: str):
    review = repo.obter(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review não encontrada")

    try:
        repo.remover(review_id)
    except ErroPersistencia as e:
        raise HTTPException(status_code=500, detail=f"Erro ao remover: {e}")
    return None