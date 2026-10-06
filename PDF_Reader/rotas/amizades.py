"""Rotas de amizades.

Todas exigem autenticação (Bearer Token) — você só pode enviar/aceitar
pedidos como VOCÊ mesmo.
"""
from fastapi import APIRouter, HTTPException, Depends

from dominio.repositories import ErroPersistencia
from dominio.state import repo_amizades, repo_usuarios
from rotas.auth import usuario_atual

router = APIRouter(prefix="/amizades", tags=["Amizades"])


# ============================================================
# ENVIAR PEDIDO
# ============================================================
@router.post("/pedido/{nome_destino}", status_code=201)
def enviar_pedido(nome_destino: str, usuario=Depends(usuario_atual)):
    destino = repo_usuarios.obter_por_nome(nome_destino)
    if destino is None:
        raise HTTPException(
            status_code=404,
            detail=f"Usuário '{nome_destino}' não existe",
        )

    try:
        amizade = repo_amizades.enviar_pedido(usuario.id, destino.id)
    except ErroPersistencia as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar: {e}")

    if amizade is None:
        raise HTTPException(
            status_code=409,
            detail="Já existe amizade ou pedido pendente com esse usuário",
        )

    return {
        "id": amizade.id,
        "status": amizade.status,
        "destinatario": destino.nome,
        "criado_em": amizade.criado_em,
    }


# ============================================================
# LISTAR AMIGOS
# ============================================================
@router.get("")
def listar_amigos(usuario=Depends(usuario_atual)):
    amizades = repo_amizades.listar_amigos(usuario.id)
    resultado = []
    for a in amizades:
        outro_id = (a.destinatario_id if a.solicitante_id == usuario.id
                    else a.solicitante_id)
        outro = repo_usuarios.obter_por_id(outro_id)
        if outro is not None:
            resultado.append({
                "amizade_id": a.id,
                "usuario_id": outro.id,
                "nome": outro.nome,
                "desde": a.respondido_em or a.criado_em,
            })
    return resultado


# ============================================================
# LISTAR PEDIDOS PENDENTES RECEBIDOS
# ============================================================
@router.get("/pendentes")
def listar_pendentes(usuario=Depends(usuario_atual)):
    pendentes = repo_amizades.listar_pendentes_recebidos(usuario.id)
    resultado = []
    for a in pendentes:
        solicitante = repo_usuarios.obter_por_id(a.solicitante_id)
        if solicitante is not None:
            resultado.append({
                "amizade_id": a.id,
                "solicitante_id": solicitante.id,
                "nome": solicitante.nome,
                "criado_em": a.criado_em,
            })
    return resultado


# ============================================================
# PEDIDOS ENVIADOS (aguardando resposta)
# ============================================================
@router.get("/enviados")
def listar_enviados(usuario=Depends(usuario_atual)):
    pendentes = repo_amizades.listar_pendentes_enviados(usuario.id)
    resultado = []
    for a in pendentes:
        destinatario = repo_usuarios.obter_por_id(a.destinatario_id)
        if destinatario is not None:
            resultado.append({
                "amizade_id": a.id,
                "destinatario_id": destinatario.id,
                "nome": destinatario.nome,
                "criado_em": a.criado_em,
            })
    return resultado


# ============================================================
# ACEITAR
# ============================================================
@router.post("/{amizade_id}/aceitar")
def aceitar(amizade_id: str, usuario=Depends(usuario_atual)):
    try:
        amizade = repo_amizades.aceitar(amizade_id, usuario.id)
    except ErroPersistencia as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar: {e}")

    if amizade is None:
        raise HTTPException(
            status_code=404,
            detail="Pedido não encontrado ou você não pode aceitá-lo",
        )
    return {"status": amizade.status, "respondido_em": amizade.respondido_em}


# ============================================================
# RECUSAR
# ============================================================
@router.delete("/{amizade_id}/recusar", status_code=204)
def recusar(amizade_id: str, usuario=Depends(usuario_atual)):
    try:
        ok = repo_amizades.recusar(amizade_id, usuario.id)
    except ErroPersistencia as e:
        raise HTTPException(status_code=500, detail=f"Erro ao remover: {e}")

    if not ok:
        raise HTTPException(
            status_code=404,
            detail="Pedido não encontrado ou você não pode recusá-lo",
        )
    return None


# ============================================================
# DESFAZER AMIZADE
# ============================================================
@router.delete("/{amizade_id}", status_code=204)
def desfazer(amizade_id: str, usuario=Depends(usuario_atual)):
    try:
        ok = repo_amizades.desfazer(amizade_id, usuario.id)
    except ErroPersistencia as e:
        raise HTTPException(status_code=500, detail=f"Erro ao remover: {e}")

    if not ok:
        raise HTTPException(
            status_code=404,
            detail="Amizade não encontrada ou você não participa dela",
        )
    return None