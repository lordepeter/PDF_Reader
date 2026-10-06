"""Estado compartilhado da API.

Os repositórios são instanciados UMA VEZ aqui, e todos os routers importam
dessa mesma fonte. Isso garante que os routers compartilhem a mesma
memória — sem isso, dois routers manipulando o mesmo arquivo JSON podem
sobrescrever um ao outro.

Esse padrão se chama "singleton" (instância única).
"""
from .repositories import (
    RepositorioPerfis,
    RepositorioReviews,
    RepositorioCatalogo,
    RepositorioUsuarios,
    RepositorioSessoes,
    RepositorioAmizades,
    RepositorioComentarios, 
    RepositorioMensagensChat,
)

# ---- Instâncias únicas (singletons) ----
repo_perfis = RepositorioPerfis("perfis_api.json")
repo_reviews = RepositorioReviews("reviews_api.json")
repo_catalogo = RepositorioCatalogo("catalogo.json")
repo_usuarios = RepositorioUsuarios("usuarios.json")
repo_sessoes = RepositorioSessoes("sessoes.json")
repo_amizades = RepositorioAmizades("amizades.json")
repo_comentarios = RepositorioComentarios("comentarios.json")
repo_chat = RepositorioMensagensChat("chat.json")  