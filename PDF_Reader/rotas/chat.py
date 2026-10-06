"""Rotas de chat privado entre dois usuários.

Todas exigem autenticação. Só é possível conversar com amigos aceitos.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from dominio.repositories import ErroPersistencia
from dominio.state import (
    repo_chat as repo_mensagens,
    repo_usuarios,
    repo_amizades,
)
from rotas.auth import usuario_atual

router = APIRouter(prefix="/chat", tags=["Chat"])


# ============================================================
# Esquemas Pydantic
# ============================================================
class MensagemEntrada(BaseModel):
    texto: str = Field(..., min_length=1, max_length=1000)


# ============================================================
# LISTAR CONVERSAS RECENTES (sidebar)
# ============================================================
@router.get("")
def listar_conversas(usuario=Depends(usuario_atual)):
    """Lista todos os amigos com a última mensagem trocada, ordenado
    por mensagens mais recentes primeiro."""
    amizades = repo_amizades.listar_amigos(usuario.id)

    conversas = []
    for a in amizades:
        outro_id = (a.destinatario_id if a.solicitante_id == usuario.id
                    else a.solicitante_id)
        outro = repo_usuarios.obter_por_id(outro_id)
        if outro is None:
            continue

        ultima = repo_mensagens.ultima_mensagem(usuario.id, outro.id)
        nao_lidas = repo_mensagens.nao_lidas_de(usuario.id, outro.id)

        conversas.append({
            "amigo_id": outro.id,
            "amigo_nome": outro.nome,
            "ultima_mensagem": ultima.texto if ultima else None,
            "ultima_em": ultima.enviado_em if ultima else None,
            "nao_lidas": nao_lidas,
        })

    # Ordena: quem tem mensagem mais recente primeiro; quem não tem vai pro fim
    conversas.sort(
        key=lambda c: c["ultima_em"] or "",
        reverse=True,
    )
    return conversas


# ============================================================
# LISTAR MENSAGENS entre mim e um amigo
# ============================================================
@router.get("/{nome_amigo}")
def listar_mensagens(nome_amigo: str, usuario=Depends(usuario_atual)):
    amigo = repo_usuarios.obter_por_nome(nome_amigo)
    if amigo is None:
        raise HTTPException(status_code=404, detail=f"Usuário '{nome_amigo}' não existe")

    if not repo_amizades.sao_amigos(usuario.id, amigo.id):
        raise HTTPException(
            status_code=403,
            detail="Vocês não são amigos — só é possível conversar com amigos",
        )

    mensagens = repo_mensagens.conversa_entre(usuario.id, amigo.id)

    # Marca como lidas as que eu recebi
    repo_mensagens.marcar_lidas(usuario.id, amigo.id)

    return [m.to_dict() for m in mensagens]


# ============================================================
# ENVIAR mensagem
# ============================================================
@router.post("/{nome_amigo}", status_code=201)
def enviar_mensagem(nome_amigo: str, dados: MensagemEntrada,
                     usuario=Depends(usuario_atual)):
    amigo = repo_usuarios.obter_por_nome(nome_amigo)
    if amigo is None:
        raise HTTPException(status_code=404, detail=f"Usuário '{nome_amigo}' não existe")

    if not repo_amizades.sao_amigos(usuario.id, amigo.id):
        raise HTTPException(
            status_code=403,
            detail="Vocês não são amigos — só é possível conversar com amigos",
        )

    try:
        msg = repo_mensagens.enviar(
            remetente_id=usuario.id,
            remetente_nome=usuario.nome,
            destinatario_id=amigo.id,
            destinatario_nome=amigo.nome,
            texto=dados.texto,
        )
    except ErroPersistencia as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar: {e}")

    return msg.to_dict()


# ============================================================
# POLLING — mensagens novas desde um timestamp
# ============================================================
@router.get("/{nome_amigo}/novas")
def novas_mensagens(nome_amigo: str, desde: str = "",
                     usuario=Depends(usuario_atual)):
    """Retorna só as mensagens enviadas depois de `desde` (formato
    'dd/mm/aaaa hh:mm'). Usado pelo polling do app."""
    amigo = repo_usuarios.obter_por_nome(nome_amigo)
    if amigo is None:
        raise HTTPException(status_code=404, detail=f"Usuário '{nome_amigo}' não existe")

    if not repo_amizades.sao_amigos(usuario.id, amigo.id):
        raise HTTPException(status_code=403, detail="Vocês não são amigos")

    if not desde:
        mensagens = repo_mensagens.conversa_entre(usuario.id, amigo.id)
    else:
        mensagens = repo_mensagens.novas_desde(usuario.id, amigo.id, desde)

    # Marca como lidas
    repo_mensagens.marcar_lidas(usuario.id, amigo.id)

    return [m.to_dict() for m in mensagens]


# ============================================================
# TOTAL DE NÃO LIDAS (badge)
# ============================================================
@router.get("/nao-lidas/total")
def total_nao_lidas(usuario=Depends(usuario_atual)):
    return {"total": repo_mensagens.total_nao_lidas(usuario.id)}