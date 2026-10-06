"""Rotas de autenticação.

Registro, login, logout e um endpoint para verificar quem está logado.
Usa Bearer Token — o cliente envia `Authorization: Bearer <token>` em
toda requisição que exige autenticação.
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import Optional

from dominio.repositories import ErroPersistencia
from dominio.state import repo_usuarios, repo_sessoes

router = APIRouter(prefix="/auth", tags=["Autenticação"])


# ============================================================
# Esquemas Pydantic
# ============================================================
class RegistroEntrada(BaseModel):
    nome: str = Field(..., min_length=3, max_length=30)
    senha: str = Field(..., min_length=4, max_length=72)


class LoginEntrada(BaseModel):
    nome: str = Field(..., min_length=1)
    senha: str = Field(..., min_length=1)

# Esquema de segurança (aparece como cadeado no /docs)
security = HTTPBearer()

# ============================================================
# Dependency: extrai o usuário atual do header Authorization
# ============================================================
def usuario_atual(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Extrai o usuário autenticado do token Bearer.

    O FastAPI+Swagger cuida de pedir o token no /docs. Aqui só validamos
    que ele existe no repositório de sessões.
    """
    token = credentials.credentials
    sessao = repo_sessoes.obter(token)
    if sessao is None:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")

    usuario = repo_usuarios.obter_por_id(sessao.usuario_id)
    if usuario is None:
        # Sessão órfã (usuário foi removido, mas a sessão ficou)
        repo_sessoes.remover(token)
        raise HTTPException(status_code=401, detail="Usuário da sessão não existe")

    return usuario


# ============================================================
# REGISTRAR
# ============================================================
@router.post("/registrar", status_code=201)
def registrar(dados: RegistroEntrada):
    try:
        usuario = repo_usuarios.criar(dados.nome, dados.senha)
    except ErroPersistencia as e:
        raise HTTPException(status_code=500, detail=f"Erro ao registrar: {e}")

    if usuario is None:
        raise HTTPException(
            status_code=409,
            detail=f"Já existe um usuário com o nome '{dados.nome}'",
        )

    return {
        "id": usuario.id,
        "nome": usuario.nome,
        "criado_em": usuario.criado_em,
    }


# ============================================================
# LOGIN — agora retorna token também
# ============================================================
@router.post("/login")
def login(dados: LoginEntrada):
    usuario = repo_usuarios.obter_por_nome(dados.nome)

    if usuario is None or not usuario.verificar_senha(dados.senha):
        raise HTTPException(
            status_code=401,
            detail="Nome ou senha inválidos",
        )

    try:
        sessao = repo_sessoes.criar(usuario.id)
    except ErroPersistencia as e:
        raise HTTPException(status_code=500, detail=f"Erro ao criar sessão: {e}")

    return {
        "id": usuario.id,
        "nome": usuario.nome,
        "criado_em": usuario.criado_em,
        "token": sessao.token,
    }


# ============================================================
# LOGOUT — invalida a sessão
# ============================================================
@router.post("/logout", status_code=204)
def logout(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        repo_sessoes.remover(token)
    except ErroPersistencia as e:
        raise HTTPException(status_code=500, detail=f"Erro ao remover sessão: {e}")
    return None


# ============================================================
# EU — verifica quem está logado (rota protegida de teste)
# ============================================================
@router.get("/eu")
def eu(usuario=Depends(usuario_atual)):
    return {
        "id": usuario.id,
        "nome": usuario.nome,
        "criado_em": usuario.criado_em,
    }