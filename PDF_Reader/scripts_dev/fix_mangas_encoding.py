"""fix_mangas_encoding.py

Corrige mojibake nos nomes de mangás (UTF-8 lido como CP437).
Aplica em obra.nome, volumes[].titulo e regenera as URLs.
"""
import json
import os
from urllib.parse import quote, unquote

CATALOGO = os.path.join("catalogo", "catalogo.json")
R2_BASE = "https://pub-76e89d327c504ed1affa4e389a63a702.r2.dev"


def fix_mojibake(s: str) -> str:
    """Reverte mojibake UTF-8 → CP437. Retorna o original se falhar."""
    try:
        return s.encode("cp437").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


with open(CATALOGO, "r", encoding="utf-8") as f:
    d = json.load(f)

corrigidos = 0
for obra in d["obras"]:
    if not obra["id"].startswith("mng-"):
        continue

    nome_antigo = obra["nome"]
    nome_novo = fix_mojibake(nome_antigo)

    if nome_novo == nome_antigo:
        continue

    print(f"🔧 {nome_antigo!r}")
    print(f"   → {nome_novo!r}")

    obra["nome"] = nome_novo

    for vol in obra.get("volumes", []):
        # Reconstrói a URL a partir do path corrigido
        if vol.get("url", "").startswith(R2_BASE + "/"):
            path_encoded = vol["url"][len(R2_BASE) + 1:]
            path_antigo = unquote(path_encoded)
            path_novo = fix_mojibake(path_antigo)
            vol["url"] = f"{R2_BASE}/{quote(path_novo, safe='/')}"

        # Corrige título
        titulo_antigo = vol.get("titulo", "")
        titulo_novo = fix_mojibake(titulo_antigo)
        if titulo_novo != titulo_antigo:
            vol["titulo"] = titulo_novo

    corrigidos += 1

if corrigidos:
    with open(CATALOGO + ".bak6", "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    with open(CATALOGO, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    print(f"\n✅ {corrigidos} mangá(s) corrigido(s)")
else:
    print("✅ Nada para corrigir")