"""tela_splash.py - Splash simples, NUNCA trava, NUNCA fica em cima do login."""
from __future__ import annotations
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk
import requests


TIMEOUT_TOTAL = 45


class SplashScreen:
    def __init__(self, root: tk.Tk, api_url: str):
        self.root = root
        self.api_url = api_url.rstrip("/")
        self.health_url = f"{self.api_url}/"

        self.resultado = None
        self._cancelar = False
        self._thread = None
        self._fila = queue.Queue()

        self.janela = tk.Toplevel(root)
        self.janela.overrideredirect(True)
        self.janela.configure(bg="#003366")

        largura, altura = 480, 360
        x = (self.janela.winfo_screenwidth() - largura) // 2
        y = (self.janela.winfo_screenheight() - altura) // 2
        self.janela.geometry(f"{largura}x{altura}+{x}+{y}")

        # Nao mostrar na taskbar (fica filha do root)
        try:
            self.janela.transient(root)
        except tk.TclError:
            pass

        # NAO usa -topmost — pra nao ficar em cima do login
        self._montar_ui()

    def _montar_ui(self):
        topo = tk.Frame(self.janela, bg="#003366")
        topo.pack(fill="x", pady=(30, 5))

        tk.Label(topo, text="\U0001F4D6", font=("Segoe UI", 44),
                 bg="#003366", fg="#FFFFFF").pack()
        tk.Label(topo, text="Sophia", font=("Segoe UI", 26, "bold"),
                 bg="#003366", fg="#FFFFFF").pack(pady=(2, 0))
        tk.Label(topo, text="Leitura e Comunidade",
                 font=("Segoe UI", 10, "italic"),
                 bg="#003366", fg="#D0E3F7").pack(pady=(0, 15))

        self.lbl_status = tk.Label(self.janela, text="Iniciando...",
                                    font=("Segoe UI", 11),
                                    bg="#003366", fg="#FFFFFF")
        self.lbl_status.pack(pady=(8, 4))

        self.prog = ttk.Progressbar(self.janela, mode="indeterminate", length=320)
        self.prog.pack(pady=(5, 5))
        self.prog.start(12)

        self.lbl_detalhe = tk.Label(self.janela, text="",
                                     font=("Segoe UI", 8),
                                     bg="#003366", fg="#A8C6E0")
        self.lbl_detalhe.pack(pady=(2, 8))

        tk.Button(self.janela,
                  text="\u23ED  Pular e usar modo offline",
                  font=("Segoe UI", 9, "bold"),
                  bg="#DCEBFA", fg="#003366",
                  relief="raised", padx=14, pady=6, cursor="hand2",
                  command=self._escolher_offline).pack(side="bottom", pady=(0, 15))

    def _worker_ping(self):
        inicio = time.monotonic()
        tentativa = 0

        while not self._cancelar:
            tentativa += 1
            decorrido = time.monotonic() - inicio

            if decorrido > TIMEOUT_TOTAL:
                self._fila.put(("offline", "tempo esgotado"))
                return

            self._fila.put(("status", ("Conectando ao servidor...",
                                        f"Tentativa {tentativa} - {int(decorrido)}s")))

            try:
                r = requests.get(self.health_url, timeout=15)
                if r.status_code == 200:
                    self._fila.put(("sucesso", None))
                    return
                else:
                    self._fila.put(("status", (f"Servidor respondeu {r.status_code}",
                                                "Tentando de novo...")))
            except requests.ConnectionError:
                self._fila.put(("status", ("Acordando o servidor...",
                                            "Pode levar ate 45s")))
            except requests.Timeout:
                self._fila.put(("status", ("Servidor demorando...",
                                            f"Tentativa {tentativa} - {int(decorrido)}s")))
            except Exception as e:
                self._fila.put(("status", ("Erro de rede",
                                            f"{type(e).__name__}: {str(e)[:60]}")))

            if self._cancelar:
                return
            time.sleep(1.5)

    def _processar_fila(self):
        try:
            while True:
                tipo, dados = self._fila.get_nowait()
                if tipo == "status":
                    self.lbl_status.config(text=dados[0])
                    self.lbl_detalhe.config(text=dados[1])
                elif tipo == "sucesso":
                    self.resultado = "online"
                    self._fechar()
                    return
                elif tipo == "offline":
                    print(f"[splash] offline: {dados}")
                    self._escolher_offline()
                    return
        except queue.Empty:
            pass

        if not self._cancelar:
            self.root.after(100, self._processar_fila)

    def _escolher_offline(self):
        if self.resultado is None:
            self.resultado = "offline"
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

    def executar(self) -> str:
        self.janela.protocol("WM_DELETE_WINDOW", self._escolher_offline)

        self._thread = threading.Thread(target=self._worker_ping, daemon=True)
        self._thread.start()
        self.root.after(100, self._processar_fila)

        # Hard timeout de 50s
        self.root.after(50_000, self._escolher_offline)

        self.root.wait_window(self.janela)
        return self.resultado or "offline"
