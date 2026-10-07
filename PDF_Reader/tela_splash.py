"""tela_splash.py — Tela de loading com retry para servidor com cold start.

Uso típico no main.py:

    root = tk.Tk()
    root.withdraw()  # esconde a janela principal

    splash = SplashScreen(root, api_url="https://sua-api.onrender.com")
    resultado = splash.executar()

    if resultado == "online":
        root.deiconify()
        iniciar_app()

    elif resultado == "offline":
        # usuário escolheu modo offline
        root.deiconify()
        iniciar_app(modo_offline=True)

    else:  # "cancelado"
        root.destroy()
"""
from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import ttk

import requests


# ============================================================
# CONFIGURAÇÃO
# ============================================================
TIMEOUT_POR_TENTATIVA = 8       # segundos por tentativa individual
TIMEOUT_TOTAL = 120             # teto máximo (2 min) pra esperar servidor acordar
BACKOFF_BASE = 1.5              # multiplicador de espera entre tentativas


class SplashScreen:
    """Mostra a tela de loading, tenta conectar ao servidor e retorna o resultado."""

    def __init__(self, root: tk.Tk, api_url: str):
        self.root = root
        self.api_url = api_url.rstrip("/")
        self.health_url = f"{self.api_url}/"

        self.resultado: str | None = None
        self._cancelar = False
        self._thread: threading.Thread | None = None

        # ---------- Janela ----------
        self.janela = tk.Toplevel(root)
        self.janela.overrideredirect(True)  # sem barra de título
        self.janela.configure(bg="#003366")

        largura, altura = 480, 320
        x = (self.janela.winfo_screenwidth() - largura) // 2
        y = (self.janela.winfo_screenheight() - altura) // 2
        self.janela.geometry(f"{largura}x{altura}+{x}+{y}")

        # Fica por cima de tudo enquanto carrega
        self.janela.attributes("-topmost", True)
        self.janela.lift()

        self._montar_ui()

    # ==========================================================
    # UI
    # ==========================================================
    def _montar_ui(self):
        # ---------- Logo / Título ----------
        frame_topo = tk.Frame(self.janela, bg="#003366")
        frame_topo.pack(fill="x", pady=(35, 5))

        tk.Label(frame_topo, text="📖",
                 font=("Segoe UI", 44), bg="#003366", fg="#FFFFFF").pack()

        tk.Label(frame_topo, text="Sophia",
                 font=("Segoe UI", 26, "bold"),
                 bg="#003366", fg="#FFFFFF").pack(pady=(2, 0))

        tk.Label(frame_topo, text="Leitura e Comunidade",
                 font=("Segoe UI", 10, "italic"),
                 bg="#003366", fg="#D0E3F7").pack(pady=(0, 15))

        # ---------- Status ----------
        self.lbl_status = tk.Label(
            self.janela,
            text="Iniciando...",
            font=("Segoe UI", 11),
            bg="#003366", fg="#FFFFFF",
        )
        self.lbl_status.pack(pady=(8, 4))

        # ---------- Barra de progresso ----------
        self.prog = ttk.Progressbar(
            self.janela,
            mode="indeterminate",
            length=320,
        )
        self.prog.pack(pady=(5, 5))
        self.prog.start(12)  # animação contínua

        # ---------- Contador ----------
        self.lbl_detalhe = tk.Label(
            self.janela,
            text="",
            font=("Segoe UI", 8),
            bg="#003366", fg="#A8C6E0",
        )
        self.lbl_detalhe.pack(pady=(2, 0))

        # ---------- Área de botões (escondida até falhar) ----------
        self.frame_botoes = tk.Frame(self.janela, bg="#003366")
        self.frame_botoes.pack(pady=(15, 0))

        self.btn_tentar = tk.Button(
            self.frame_botoes, text="🔄  Tentar novamente",
            font=("Segoe UI", 10, "bold"),
            bg="#DCEBFA", fg="#003366",
            relief="raised", padx=14, pady=6,
            cursor="hand2",
            command=self._tentar_novamente,
        )

        self.btn_offline = tk.Button(
            self.frame_botoes, text="📴  Modo offline",
            font=("Segoe UI", 10),
            bg="#F0F4F8", fg="#555555",
            relief="raised", padx=14, pady=6,
            cursor="hand2",
            command=self._escolher_offline,
        )

        self.btn_fechar = tk.Button(
            self.frame_botoes, text="✖  Fechar",
            font=("Segoe UI", 10),
            bg="#F0F4F8", fg="#C2185B",
            relief="raised", padx=14, pady=6,
            cursor="hand2",
            command=self._escolher_fechar,
        )

    # ==========================================================
    # ANIMAÇÃO
    # ==========================================================
    def _atualizar_status(self, texto: str, detalhe: str = ""):
        """Thread-safe: agenda na thread da UI."""
        def aplicar():
            if self._cancelar:
                return
            try:
                self.lbl_status.config(text=texto)
                if detalhe:
                    self.lbl_detalhe.config(text=detalhe)
            except tk.TclError:
                pass
        self.root.after(0, aplicar)

    # ==========================================================
    # LÓGICA DE CONEXÃO (thread separada)
    # ==========================================================
    def _worker_ping(self):
        """Tenta conectar ao servidor com retry exponencial."""
        inicio = time.monotonic()
        tentativa = 0
        espera = 1.0

        while not self._cancelar:
            tentativa += 1
            decorrido = time.monotonic() - inicio

            if decorrido > TIMEOUT_TOTAL:
                self._atualizar_status(
                    "❌  Não foi possível conectar",
                    f"Tempo esgotado após {int(decorrido)}s"
                )
                self.root.after(0, self._mostrar_botoes)
                return

            self._atualizar_status(
                "🔄  Conectando ao servidor...",
                f"Tentativa {tentativa} • {int(decorrido)}s decorridos"
            )

            try:
                r = requests.get(self.health_url, timeout=TIMEOUT_POR_TENTATIVA)
                if r.status_code == 200:
                    self._atualizar_status(
                        "✅  Servidor conectado!",
                        "Preparando interface..."
                    )
                    time.sleep(0.4)
                    self.root.after(0, self._sucesso)
                    return
                else:
                    self._atualizar_status(
                        f"⚠️  Servidor respondeu {r.status_code}",
                        "Aguardando resposta correta..."
                    )
            except requests.ConnectionError:
                # Servidor dormindo — é o caso mais comum
                if tentativa == 1:
                    self._atualizar_status(
                        "☕  Acordando o servidor...",
                        "Isso pode levar até 1 minuto na primeira vez do dia"
                    )
                else:
                    self._atualizar_status(
                        "🔄  Ainda acordando o servidor...",
                        f"Tentativa {tentativa} • {int(decorrido)}s decorridos"
                    )
            except requests.Timeout:
                self._atualizar_status(
                    "⏳  Servidor demorando para responder...",
                    f"Tentativa {tentativa} • {int(decorrido)}s decorridos"
                )
            except Exception as e:
                self._atualizar_status(
                    "⚠️  Erro inesperado",
                    f"{type(e).__name__}: {str(e)[:60]}"
                )

            # Espera com backoff
            if self._cancelar:
                return
            time.sleep(espera)
            espera = min(espera * BACKOFF_BASE, 5.0)

    # ==========================================================
    # RESULTADOS
    # ==========================================================
    def _sucesso(self):
        self.resultado = "online"
        self._fechar()

    def _mostrar_botoes(self):
        """Mostra os botões de recuperação após falha."""
        try:
            self.prog.stop()
            self.prog.pack_forget()  # esconde a barra
            self.btn_tentar.pack(side="left", padx=5)
            self.btn_offline.pack(side="left", padx=5)
            self.btn_fechar.pack(side="left", padx=5)
        except tk.TclError:
            pass

    def _tentar_novamente(self):
        # Esconde botões, volta a barra
        for btn in (self.btn_tentar, self.btn_offline, self.btn_fechar):
            btn.pack_forget()
        self.prog.pack(pady=(5, 5))
        self.prog.start(12)

        self._cancelar = False
        self._thread = threading.Thread(target=self._worker_ping, daemon=True)
        self._thread.start()

    def _escolher_offline(self):
        self.resultado = "offline"
        self._fechar()

    def _escolher_fechar(self):
        self.resultado = "cancelado"
        self._fechar()

    def _fechar(self):
        self._cancelar = True
        try:
            self.prog.stop()
        except tk.TclError:
            pass
        try:
            self.janela.destroy()
        except tk.TclError:
            pass

    # ==========================================================
    # ENTRADA PRINCIPAL
    # ==========================================================
    def executar(self) -> str:
        """Roda o splash e bloqueia até o usuário decidir ou conectar.

        Retorna:
            "online"    → servidor respondeu
            "offline"   → usuário escolheu seguir sem servidor
            "cancelado" → usuário fechou
        """
        # X da janela = cancelar
        self.janela.protocol("WM_DELETE_WINDOW", self._escolher_fechar)

        self._thread = threading.Thread(target=self._worker_ping, daemon=True)
        self._thread.start()

        # Bloqueia essa chamada até o splash ser destruído
        self.root.wait_window(self.janela)
        return self.resultado or "cancelado"