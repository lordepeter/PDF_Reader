# -*- mode: python ; coding: utf-8 -*-
import os
import sys
import site
from PyInstaller.utils.hooks import collect_all

# Forca o PyInstaller a olhar no user site-packages
user_site = site.getusersitepackages()
if isinstance(user_site, str) and user_site and user_site not in sys.path:
    sys.path.insert(0, user_site)

# ---------- Dados empacotados (somente recursos do CLIENTE) ----------
# NAO inclua pastas do servidor (dominio/, rotas/) nem .env!
datas = [
    ("catalogo", "catalogo"),
    ("assets/audio", "assets/audio"),
    ("assets/icones", "assets/icones"),
]

# ---------- Imports escondidos ----------
hiddenimports = [
    "requests", "requests.adapters", "requests.packages.urllib3",
    "urllib3", "urllib3.contrib",
    "charset_normalizer", "idna", "certifi",
    "http.client", "http.cookiejar", "ssl",
    "bcrypt", "dotenv",
    "pymupdf", "fitz", "PIL", "PIL._tkinter_finder",
    "PIL.Image", "PIL.ImageTk",
    "sqlalchemy", "sqlalchemy.sql.default_comparator", "sqlalchemy.orm",
    "psycopg",
    "tkinter", "tkinter.ttk", "tkinter.filedialog",
    "tkinter.messagebox", "tkinter.simpledialog",
    # Modulos proprios do cliente
    "notificacoes", "sons",
    "auth_api", "busca_api", "chat_api",
    "amizades_api", "comentarios_api", "perfis_api",
    "tela_login", "tela_splash",
    "gerenciador_downloads", "capa_remota",
    "models", "repositories", "repositories_api",
]

binaries = []
for pacote in ["pymupdf", "PIL", "bcrypt", "requests", "urllib3",
               "certifi", "charset_normalizer", "idna", "dotenv"]:
    try:
        d, b, h = collect_all(pacote)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as e:
        print(f"[spec] falhou coletar {pacote}: {e}")

a = Analysis(
    ["main.py"],
    pathex=[user_site] if user_site else [],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib", "numpy", "scipy", "pandas",
        "pytest", "notebook", "IPython",
        # Exclui modulos do servidor pra nao vazar
        "dominio", "rotas", "api_teste",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Sophia",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icones/app.ico" if os.path.exists("assets/icones/app.ico") else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Sophia",
)