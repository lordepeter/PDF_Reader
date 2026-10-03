from fastapi import FastAPI
from rotas import obras, reviews, perfis

app = FastAPI(title="MangaReader API")

@app.get("/")
def raiz():
    return {"mensagem": "Bem-vindo à API do MangaReader 2000"}

app.include_router(obras.router)
app.include_router(reviews.router)
app.include_router(perfis.router)