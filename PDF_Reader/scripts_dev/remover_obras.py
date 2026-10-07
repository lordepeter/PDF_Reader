"""remover_obras.py — remove obras específicas do catálogo pelo nome."""
import json
import os

CATALOGO = os.path.join("catalogo", "catalogo.json")
REMOVER = {"O Conde de Monte Cristo", "O Médico e o Monstro"}

with open(CATALOGO, "r", encoding="utf-8") as f:
    d = json.load(f)

antes = len(d["obras"])
d["obras"] = [o for o in d["obras"] if o.get("nome") not in REMOVER]
removidas = antes - len(d["obras"])

# Backup
with open(CATALOGO + ".bak3", "w", encoding="utf-8") as f:
    json.dump(d, f, ensure_ascii=False, indent=2)

with open(CATALOGO, "w", encoding="utf-8") as f:
    json.dump(d, f, ensure_ascii=False, indent=2)

print(f"✅ {antes} → {len(d['obras'])} obras (removidas {removidas})")