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
)

# ---- Instâncias únicas (singletons) ----
repo_perfis = RepositorioPerfis("perfis_api.json")
repo_reviews = RepositorioReviews("reviews_api.json")
repo_catalogo = RepositorioCatalogo("catalogo.json")