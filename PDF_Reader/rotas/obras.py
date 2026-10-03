"""Rotas do catálogo de obras.

O catálogo é praticamente read-only — o conteúdo vive em `catalogo.json`
e a API apenas serve os dados para o cliente.

Rotas extras (/reviews e /media) agregam informação de reviews, poupando
o cliente de fazer múltiplas requisições.
"""
from fastapi import APIRouter, HTTPException

from dominio.state import repo_catalogo
from dominio.state import repo_reviews   # import tardio não é preciso aqui

router = APIRouter(prefix="/catalogo", tags=["Catálogo"])


# ---------- READ (lista) ----------
@router.get("")
def listar_catalogo():
    return [item.to_dict() for item in repo_catalogo.listar()]


# ---------- READ (um) ----------
@router.get("/{item_id}")
def obter_item(item_id: str):
    item = repo_catalogo.obter(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Obra não encontrada")
    return item.to_dict()


# ---------- READ (reviews de uma obra) ----------
@router.get("/{item_id}/reviews")
def listar_reviews_da_obra(item_id: str):
    item = repo_catalogo.obter(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Obra não encontrada")

    # Busca as reviews casando por nome OU id
    reviews = repo_reviews.listar_por_obra(item.nome, item.id)
    return [r.to_dict() for r in reviews]


# ---------- READ (média de uma obra) ----------
@router.get("/{item_id}/media")
def media_da_obra(item_id: str):
    item = repo_catalogo.obter(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Obra não encontrada")

    media, total = repo_reviews.media_da_obra(item.nome, item.id)
    return {
        "item_id": item.id,
        "obra": item.nome,
        "media": media,
        "total_reviews": total,
    }