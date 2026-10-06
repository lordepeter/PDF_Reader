"""Rotas de comentários (mural de recados).

Todos os endpoints exigem autenticação — você precisa estar logado
para postar, ver ou deletar comentários.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from dominio.repositories import ErroPersistencia
from dominio.state import repo_comentarios, repo_usuarios
from rotas.auth import usuario_atual

router = APIRouter(prefix="/comentarios", tags=["Comentários"])


# ============================================================
# Esquemas Pydantic
# ============================================================
class ComentarioEntrada(BaseModel):
    texto: str = Field(..., min_length=1, max_length=500)


# ============================================================
# POSTAR COMENTÁRIO no mural de alguém
# ============================================================
@router.post("/{nome_alvo}", status_code=201)
def postar_comentario(
    nome_alvo: str,
    dados: ComentarioEntrada,
    usuario=Depends(usuario_atual),
):
    alvo = repo_usuarios.obter_por_nome(nome_alvo)
    if alvo is None:
        raise HTTPException(
            status_code=404,
            detail=f"Usuário '{nome_alvo}' não existe",
        )

    try:
        comentario = repo_comentarios.criar(
            autor_id=usuario.id,
            autor_nome=usuario.nome,
            alvo_id=alvo.id,
            texto=dados.texto,
        )
    except ErroPersistencia as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar: {e}")

    return comentario.to_dict()


# ============================================================
# LISTAR COMENTÁRIOS do mural de alguém
# ============================================================
@router.get("/{nome_alvo}")
def listar_comentarios(nome_alvo: str):
    alvo = repo_usuarios.obter_por_nome(nome_alvo)
    if alvo is None:
        raise HTTPException(
            status_code=404,
            detail=f"Usuário '{nome_alvo}' não existe",
        )

    comentarios = repo_comentarios.listar_do_mural(alvo.id)
    return [c.to_dict() for c in comentarios]


# ============================================================
# DELETAR COMENTÁRIO
# Permissão: autor OU dono do mural
# ============================================================
@router.delete("/{comentario_id}", status_code=204)
def deletar_comentario(
    comentario_id: str,
    usuario=Depends(usuario_atual),
):
    try:
        ok = repo_comentarios.remover(comentario_id, usuario.id)
    except ErroPersistencia as e:
        raise HTTPException(status_code=500, detail=f"Erro ao remover: {e}")

    if not ok:
        raise HTTPException(
            status_code=404,
            detail="Comentário não encontrado ou você não tem permissão",
        )
    return None