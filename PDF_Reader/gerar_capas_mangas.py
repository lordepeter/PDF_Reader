"""gerar_capas_mangas.py

Para cada mangá:
1. Baixa o VOLUME 1 do R2 (capa oficial do mangá)
2. Extrai a 1ª página como JPEG (400x600, qualidade 85)
3. Sobe pro R2 como {manga}/_cover.jpg
4. Atualiza catalogo.json com capa_url

Uso:
    python gerar_capas_mangas.py             # retoma (pula quem já tem)
    python gerar_capas_mangas.py --refazer   # apaga e refaz todas
    python gerar_capas_mangas.py --manga "Berserk"  # só um mangá específico

Requer rclone configurado (remote 'r2') e requests/pymupdf/Pillow.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import quote

import pymupdf
import requests
from PIL import Image


CATALOGO = os.path.join("catalogo", "catalogo.json")
R2_BASE = "https://pub-76e89d327c504ed1affa4e389a63a702.r2.dev"
R2_REMOTE = "r2:mangareader-pdfs"
USER_AGENT = "MangaReader2000/1.0"
TIMEOUT = 300


def extrair_capa(caminho_pdf: str, caminho_jpg: str) -> None:
    """Extrai a primeira página do PDF como JPG."""
    doc = pymupdf.open(caminho_pdf)
    try:
        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=150)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        img.thumbnail((400, 600), Image.Resampling.LANCZOS)
        img.save(caminho_jpg, "JPEG", quality=85)
    finally:
        doc.close()


def baixar_arquivo(url: str, destino: str) -> None:
    """Baixa a URL para o arquivo local, com retry."""
    for tentativa in range(1, 4):
        try:
            with requests.get(url, headers={"User-Agent": USER_AGENT},
                              stream=True, timeout=TIMEOUT) as r:
                r.raise_for_status()
                with open(destino, "wb") as f:
                    for chunk in r.iter_content(chunk_size=64 * 1024):
                        if chunk:
                            f.write(chunk)
            return
        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError) as e:
            if tentativa == 3:
                raise
            print(f"      tentativa {tentativa} falhou ({e}), retentando...")
            # Limpa parcial antes de retentar
            if os.path.exists(destino):
                os.remove(destino)


def subir_r2(caminho_local: str, caminho_r2: str) -> tuple[bool, str]:
    """Sobe o arquivo pro R2 via rclone."""
    try:
        result = subprocess.run(
            ["rclone", "copyto", caminho_local, f"{R2_REMOTE}/{caminho_r2}"],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            return True, ""
        return False, result.stderr.strip() or "erro desconhecido"
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except FileNotFoundError:
        return False, "rclone não encontrado no PATH"


def achar_volume_1(manga: dict) -> dict | None:
    """Retorna o volume de menor número (Vol. 1 idealmente)."""
    if not manga.get("volumes"):
        return None
    # Ordena por numero, pega o primeiro
    vols = sorted(manga["volumes"], key=lambda v: v.get("numero", 9999))
    return vols[0] if vols else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refazer", action="store_true",
                        help="Refaz capas mesmo se já existirem")
    parser.add_argument("--manga", type=str, default=None,
                        help="Processa só esse mangá (pelo nome)")
    args = parser.parse_args()

    if not os.path.exists(CATALOGO):
        print(f"❌ Não encontrei {CATALOGO}")
        return

    with open(CATALOGO, "r", encoding="utf-8") as f:
        dados = json.load(f)

    mangas = [o for o in dados["obras"] if o.get("tema") == "mangas"]

    if args.manga:
        mangas = [m for m in mangas if m["nome"] == args.manga]
        if not mangas:
            print(f"❌ Mangá '{args.manga}' não encontrado no catálogo.")
            return

    print(f"📚 {len(mangas)} mangá(s) para processar")
    if args.refazer:
        print("   (modo --refazer: capas existentes serão substituídas)")
    print()

    tmp_dir = tempfile.mkdtemp(prefix="mangareader_capas_")
    processados = 0
    falhas = 0

    try:
        for manga in mangas:
            nome = manga["nome"]

            if manga.get("capa_url") and not args.refazer:
                print(f"✓ {nome} — já tem capa (use --refazer pra trocar)")
                continue

            vol = achar_volume_1(manga)
            if vol is None:
                print(f"⚠ {nome} — sem volumes, pulando\n")
                falhas += 1
                continue

            print(f"→ {nome}")
            print(f"   volume escolhido: nº {vol['numero']} — {vol['titulo']} "
                  f"({vol['tamanho_mb']:.1f} MB)")

            pdf_tmp = os.path.join(tmp_dir, "vol.pdf")
            jpg_tmp = os.path.join(tmp_dir, "cover.jpg")

            for p in (pdf_tmp, jpg_tmp):
                if os.path.exists(p):
                    os.remove(p)

            try:
                print("   baixando...", end=" ", flush=True)
                baixar_arquivo(vol["url"], pdf_tmp)
                print("ok")
            except Exception as e:
                print(f"FALHOU: {e}\n")
                falhas += 1
                continue

            try:
                print("   extraindo capa...", end=" ", flush=True)
                extrair_capa(pdf_tmp, jpg_tmp)
                print("ok")
            except Exception as e:
                print(f"FALHOU: {e}\n")
                falhas += 1
                continue

            caminho_r2 = f"{nome}/_cover.jpg"
            print("   subindo pro R2...", end=" ", flush=True)
            ok, err = subir_r2(jpg_tmp, caminho_r2)
            if not ok:
                print(f"FALHOU: {err}\n")
                falhas += 1
                continue
            print("ok")

            manga["capa_url"] = f"{R2_BASE}/{quote(caminho_r2, safe='/')}"
            print(f"   ✔ capa: {manga['capa_url']}\n")
            processados += 1

            with open(CATALOGO, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, indent=2)

    except KeyboardInterrupt:
        print("\n\n⚠  Interrompido pelo usuário (Ctrl+C).")
        print("   O progresso até agora foi salvo. Rode de novo pra continuar.")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # Backup final
    if processados > 0:
        with open(CATALOGO + ".bak_capas", "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        with open(CATALOGO, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)

    print(f"✅ Concluído!")
    print(f"   Capas geradas: {processados}")
    print(f"   Falhas: {falhas}")


if __name__ == "__main__":
    main()