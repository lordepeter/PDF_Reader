"""atualizar_berserk.py — Regenera volumes do Berserk a partir do R2."""
import json
import os
import re
import subprocess
from urllib.parse import quote

CATALOGO = os.path.join("catalogo", "catalogo.json")
R2_BASE = "https://pub-76e89d327c504ed1affa4e389a63a702.r2.dev"

result = subprocess.run(
    ["rclone", "ls", "r2:mangareader-pdfs/Berserk/"],
    capture_output=True, text=True, check=True,
)

volumes = []
for linha in result.stdout.strip().split("\n"):
    if not linha:
        continue
    partes = linha.split(" ", 1)
    if len(partes) != 2:
        continue
    tam, nome = partes
    if not nome.lower().endswith(".pdf"):
        continue
    if nome.startswith("_cover"):
        continue

    m = re.search(r"Volume\s*(\d+)", nome)
    numero = int(m.group(1)) if m else 0

    volumes.append({
        "numero": numero,
        "titulo": os.path.splitext(nome)[0],
        "url": f"{R2_BASE}/Berserk/{quote(nome, safe='/')}",
        "tamanho_mb": round(int(tam) / (1024 * 1024), 2),
        "fonte": "r2",
        "licenca": "Verificar",
    })

volumes.sort(key=lambda v: v["numero"])

with open(CATALOGO, "r", encoding="utf-8") as f:
    dados = json.load(f)

for obra in dados["obras"]:
    if obra.get("id") == "mng-001":
        obra["volumes"] = volumes
        print(f"✅ Berserk atualizado: {len(volumes)} volumes")
        break

with open(CATALOGO, "w", encoding="utf-8") as f:
    json.dump(dados, f, ensure_ascii=False, indent=2)