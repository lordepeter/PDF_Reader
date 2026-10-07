"""adicionar_mangas.py

Lê a lista do R2 (rclone ls) e adiciona os mangás ao catalogo.json.
Cada mangá recebe:
- id (mng-XXX)
- nome, autor, ano, tema="mangas", categoria, descricao
- volumes: 1 entrada por PDF do R2, com url apontando pro bucket público

Uso:
    rclone ls r2:mangareader-pdfs/ > lista_r2.txt
    python adicionar_mangas.py
"""
import json
import os
import re
from urllib.parse import quote


# ============================================================
# CONFIGURAÇÃO
# ============================================================
CATALOGO_PATH = os.path.join("catalogo", "catalogo.json")
LISTA_R2_PATH = "lista_r2.txt"
R2_BASE_URL = "https://pub-76e89d327c504ed1affa4e389a63a702.r2.dev"
CODIGO_ACESSO_MANGAS = "MANGA2026"   # ← troca pro código que quiser


# ============================================================
# METADADOS DOS MANGÁS
# ============================================================
METADADOS = {
    "Berserk": {
        "autor": "Kentaro Miura",
        "ano": 1989,
        "categoria": "Seinen",
        "descricao": (
            "Guts, um mercenário marcado por um destino cruel, caça demônios "
            "com uma espada gigantesca enquanto busca vingança contra seu "
            "antigo amigo Griffith."
        ),
    },
    "Blade - A lâmina imortal": {
        "autor": "Hiroaki Samura",
        "ano": 1993,
        "categoria": "Seinen",
        "descricao": (
            "Manji, um samurai amaldiçoado com imortalidade, precisa matar "
            "1000 homens maus para recuperar sua mortalidade."
        ),
    },
    "Bleach": {
        "autor": "Tite Kubo",
        "ano": 2001,
        "categoria": "Shounen",
        "descricao": (
            "Ichigo Kurosaki, um adolescente que ganha poderes de Ceifador "
            "de Almas, protege os vivos dos Hollows e guia as almas para o "
            "outro lado."
        ),
    },
    "Dorohedoro": {
        "autor": "Q Hayashida",
        "ano": 2000,
        "categoria": "Seinen",
        "descricao": (
            "Caiman, um homem com cabeça de réptil, caça feiticeiros para "
            "descobrir quem o transformou e por quê."
        ),
    },
    "Fairy Tail": {
        "autor": "Hiro Mashima",
        "ano": 2006,
        "categoria": "Shounen",
        "descricao": (
            "Lucy Heartfilia se junta à guilda de magos Fairy Tail e vive "
            "aventuras ao lado de Natsu, Happy e companheiros."
        ),
    },
    "Fullmetal Alchemist": {
        "autor": "Hiromu Arakawa",
        "ano": 2001,
        "categoria": "Shounen",
        "descricao": (
            "Os irmãos Edward e Alphonse Elric buscam a Pedra Filosofal para "
            "recuperar seus corpos após uma transmutação fracassada."
        ),
    },
    "Hunter x Hunter": {
        "autor": "Yoshihiro Togashi",
        "ano": 1998,
        "categoria": "Shounen",
        "descricao": (
            "Gon Freecss se torna Hunter para encontrar seu pai e se envolve "
            "em desafios e descobertas perigosas."
        ),
    },
    "Naruto": {
        "autor": "Masashi Kishimoto",
        "ano": 1999,
        "categoria": "Shounen",
        "descricao": (
            "Naruto Uzumaki, um jovem ninja com o espírito de uma raposa de "
            "nove caudas selada, busca reconhecimento e sonha em se tornar "
            "Hokage."
        ),
    },
    "Neon Genesis Evangelion": {
        "autor": "Yoshiyuki Sadamoto",
        "ano": 1994,
        "categoria": "Seinen",
        "descricao": (
            "Shinji Ikari é recrutado para pilotar um mecha Evangelion e "
            "defender a humanidade de criaturas chamadas Anjos."
        ),
    },
    "Vagabond": {
        "autor": "Takehiko Inoue",
        "ano": 1998,
        "categoria": "Seinen",
        "descricao": (
            "A jornada de Miyamoto Musashi, o lendário espadachim japonês, "
            "em busca da iluminação através do caminho da espada."
        ),
    },
}


# ============================================================
# PARSER DO rclone ls
# ============================================================
def parse_lista_r2(caminho: str) -> dict[str, list[dict]]:
    """Lê o output do 'rclone ls' e agrupa por mangá.

    Detecta automaticamente o encoding (UTF-8, UTF-16 LE/BE, Latin-1).
    O PowerShell gera UTF-16 por padrão com o operador '>'.
    """
    if not os.path.exists(caminho):
        raise FileNotFoundError(f"Não encontrei {caminho}")

    # Lê os primeiros bytes pra detectar BOM
    with open(caminho, "rb") as f:
        primeiros = f.read(4)

    if primeiros.startswith(b"\xff\xfe"):
        encoding = "utf-16-le"
    elif primeiros.startswith(b"\xfe\xff"):
        encoding = "utf-16-be"
    elif primeiros.startswith(b"\xef\xbb\xbf"):
        encoding = "utf-8-sig"
    else:
        encoding = "utf-8"

    print(f"   (encoding detectado: {encoding})")

    mangas: dict[str, list[dict]] = {}

    try:
        with open(caminho, "r", encoding=encoding) as f:
            linhas = f.readlines()
    except UnicodeDecodeError:
        # Fallback: tenta latin-1 que aceita qualquer byte
        with open(caminho, "r", encoding="latin-1") as f:
            linhas = f.readlines()
        print("   (fallback para latin-1)")

    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue

        partes = linha.split(" ", 1)
        if len(partes) != 2:
            continue

        tamanho_str, caminho_arq = partes
        try:
            tamanho_bytes = int(tamanho_str)
        except ValueError:
            continue

        if "/" not in caminho_arq:
            continue

        pasta, nome_arq = caminho_arq.split("/", 1)
        if not nome_arq.lower().endswith(".pdf"):
            continue

        mangas.setdefault(pasta, []).append({
            "nome": nome_arq,
            "tamanho_mb": round(tamanho_bytes / (1024 * 1024), 2),
            "caminho": caminho_arq,
        })

    for pasta in mangas:
        mangas[pasta].sort(key=lambda v: extrair_numero_volume(v["nome"]))

    return mangas


def extrair_numero_volume(nome_arquivo: str) -> int:
    """Tenta extrair o número do volume/capítulo do nome do arquivo."""
    base = os.path.splitext(nome_arquivo)[0]
    padroes = [
        r"[Vv]olume\s*(\d+)",
        r"[Vv]ol\.?\s*(\d+)",
        r"[Cc]ap[íi]tulo\s*(\d+)",
        r"\bv(\d+)\b",
        r"(\d+)",
    ]
    for padrao in padroes:
        m = re.search(padrao, base)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                continue
    return 9999


# ============================================================
# CONSTRUÇÃO DAS ENTRADAS
# ============================================================
def construir_item_manga(indice: int, pasta: str,
                          volumes_brutos: list[dict]) -> dict:
    """Monta um CatalogoItem completo para um mangá."""
    meta = METADADOS.get(pasta, {
        "autor": "Desconhecido",
        "ano": 0,
        "categoria": "Mangá",
        "descricao": "Sem descrição.",
    })

    volumes = []
    for i, vol in enumerate(volumes_brutos, start=1):
        numero = extrair_numero_volume(vol["nome"])
        titulo = os.path.splitext(vol["nome"])[0]

        caminho_encoded = quote(vol["caminho"], safe="/")
        url = f"{R2_BASE_URL}/{caminho_encoded}"

        volumes.append({
            "numero": numero if numero != 9999 else i,
            "titulo": titulo,
            "url": url,
            "tamanho_mb": vol["tamanho_mb"],
            "fonte": "r2",
            "licenca": "Verificar",
        })

    return {
        "id": f"mng-{indice:03d}",
        "nome": pasta,
        "autor": meta["autor"],
        "ano": meta["ano"],
        "tema": "mangas",
        "categoria": meta["categoria"],
        "descricao": meta["descricao"],
        "capa_url": "",
        "volumes": volumes,
    }


# ============================================================
# MAIN
# ============================================================
def main():
    if not os.path.exists(CATALOGO_PATH):
        print(f"❌ Não encontrei {CATALOGO_PATH}")
        return

    with open(CATALOGO_PATH, "r", encoding="utf-8") as f:
        dados = json.load(f)

    obras = dados.get("obras", [])
    ids_existentes = {o.get("id") for o in obras}

    print(f"📚 Catálogo atual: {len(obras)} obras")
    print(f"📄 Lendo lista do R2: {LISTA_R2_PATH}\n")

    mangas_por_pasta = parse_lista_r2(LISTA_R2_PATH)

    if not mangas_por_pasta:
        print("⚠ Nenhum mangá encontrado no arquivo de lista.")
        return

    print(f"🔍 Encontrados {len(mangas_por_pasta)} mangás no R2:\n")

    adicionados = 0
    for i, (pasta, volumes) in enumerate(sorted(mangas_por_pasta.items()), start=1):
        manga_id = f"mng-{i:03d}"

        if manga_id in ids_existentes:
            print(f"   [já existe] {pasta} ({len(volumes)} vol)")
            continue

        item = construir_item_manga(i, pasta, volumes)
        obras.append(item)
        adicionados += 1
        print(f"   ✓ {item['id']}  {pasta} — {len(volumes)} volumes")

    dados["obras"] = obras
    dados["codigo_acesso_mangas"] = CODIGO_ACESSO_MANGAS

    with open(CATALOGO_PATH, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Concluído!")
    print(f"   Mangás adicionados: {adicionados}")
    print(f"   Total de obras: {len(obras)}")
    print(f"   Código de acesso: {CODIGO_ACESSO_MANGAS}")
    print(f"\n💾 Salvo em: {CATALOGO_PATH}")


if __name__ == "__main__":
    main()