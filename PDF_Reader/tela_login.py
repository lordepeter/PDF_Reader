"""Tela de login e criação de conta.

Aparece antes da tela principal quando o app está em modo API e não há
sessão válida salva localmente.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

import requests

from auth_api import (
    RepositorioAuthAPI,
    GerenciadorSessao,
    SessaoLocal,
    ErroAuth,
)


class TelaLogin:
    def __init__(
        self,
        root: tk.Tk,
        auth_api: RepositorioAuthAPI,
        sessao_mgr: GerenciadorSessao,
        on_sucesso: Callable[[SessaoLocal], None],
    ):
        self.root = root
        self.auth_api = auth_api
        self.sessao_mgr = sessao_mgr
        self.on_sucesso = on_sucesso

        self.frame = ttk.Frame(root)
        self.frame.pack(expand=True, fill="both")

        self._montar_ui()
        self._verificar_api()

    # ==========================================================
    # UI
    # ==========================================================
    def _montar_ui(self):
        # ----- Cabeçalho -----
        cabecalho = ttk.Frame(self.frame, padding=20)
        cabecalho.pack(fill="x")

        ttk.Label(
            cabecalho,
            text="📖 MangaReader 2000",
            font=("Segoe UI", 20, "bold"),
            foreground="#003366",
        ).pack()
        ttk.Label(
            cabecalho,
            text="Entre ou crie sua conta para continuar",
            font=("Segoe UI", 10, "italic"),
            foreground="#666666",
        ).pack(pady=(4, 0))

        # ----- Corpo central (card) -----
        corpo = ttk.Frame(self.frame, padding=20)
        corpo.pack(expand=True)

        card = ttk.Frame(corpo, relief="solid", padding=20)
        card.pack()

        self.notebook = ttk.Notebook(card)
        self.notebook.pack(expand=True, fill="both")

        self.aba_login = ttk.Frame(self.notebook, padding=20)
        self.aba_registro = ttk.Frame(self.notebook, padding=20)

        self.notebook.add(self.aba_login, text="   Entrar   ")
        self.notebook.add(self.aba_registro, text="   Criar conta   ")

        self._montar_aba_login()
        self._montar_aba_registro()

        # ----- Rodapé com status -----
        rodape = ttk.Frame(self.frame, padding=(20, 10))
        rodape.pack(fill="x", side="bottom")

        self.lbl_status = ttk.Label(
            rodape, text="●  Verificando servidor...",
            font=("Segoe UI", 9), foreground="#666666",
        )
        self.lbl_status.pack(side="left")

    def _montar_aba_login(self):
        # Nome
        ttk.Label(self.aba_login, text="Nome:", font=("Segoe UI", 10)).pack(anchor="w")
        self.var_login_nome = tk.StringVar()
        entrada_nome = ttk.Entry(self.aba_login, textvariable=self.var_login_nome,
                                  font=("Segoe UI", 11), width=32)
        entrada_nome.pack(fill="x", pady=(4, 12))
        entrada_nome.focus_set()

        # Senha
        ttk.Label(self.aba_login, text="Senha:", font=("Segoe UI", 10)).pack(anchor="w")
        self.var_login_senha = tk.StringVar()
        entrada_senha = ttk.Entry(self.aba_login, textvariable=self.var_login_senha,
                                   font=("Segoe UI", 11), width=32, show="●")
        entrada_senha.pack(fill="x", pady=(4, 12))

        # Enter dispara login
        entrada_nome.bind("<Return>", lambda e: self._fazer_login())
        entrada_senha.bind("<Return>", lambda e: self._fazer_login())

        # Lembrar
        self.var_lembrar_login = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.aba_login, text="Lembrar neste dispositivo",
                        variable=self.var_lembrar_login).pack(anchor="w", pady=(0, 16))

        # Botão
        ttk.Button(self.aba_login, text="Entrar",
                   command=self._fazer_login).pack(fill="x")

        # Erro (oculto)
        self.lbl_erro_login = ttk.Label(self.aba_login, text="",
                                         foreground="#C2185B",
                                         font=("Segoe UI", 9))
        self.lbl_erro_login.pack(pady=(12, 0))

    def _montar_aba_registro(self):
        # Nome
        ttk.Label(self.aba_registro, text="Nome:", font=("Segoe UI", 10)).pack(anchor="w")
        self.var_reg_nome = tk.StringVar()
        ttk.Entry(self.aba_registro, textvariable=self.var_reg_nome,
                  font=("Segoe UI", 11), width=32).pack(fill="x", pady=(4, 2))
        ttk.Label(self.aba_registro, text="mínimo 3 caracteres",
                  font=("Segoe UI", 8, "italic"),
                  foreground="#888888").pack(anchor="w", pady=(0, 10))

        # Senha
        ttk.Label(self.aba_registro, text="Senha:", font=("Segoe UI", 10)).pack(anchor="w")
        self.var_reg_senha = tk.StringVar()
        ttk.Entry(self.aba_registro, textvariable=self.var_reg_senha,
                  font=("Segoe UI", 11), width=32, show="●").pack(fill="x", pady=(4, 2))
        ttk.Label(self.aba_registro, text="mínimo 4 caracteres",
                  font=("Segoe UI", 8, "italic"),
                  foreground="#888888").pack(anchor="w", pady=(0, 10))

        # Confirmar
        ttk.Label(self.aba_registro, text="Confirmar senha:",
                  font=("Segoe UI", 10)).pack(anchor="w")
        self.var_reg_senha2 = tk.StringVar()
        ttk.Entry(self.aba_registro, textvariable=self.var_reg_senha2,
                  font=("Segoe UI", 11), width=32, show="●").pack(fill="x", pady=(4, 16))

        # Lembrar
        self.var_lembrar_reg = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.aba_registro, text="Lembrar neste dispositivo",
                        variable=self.var_lembrar_reg).pack(anchor="w", pady=(0, 16))

        # Botão
        ttk.Button(self.aba_registro, text="Criar conta",
                   command=self._fazer_registro).pack(fill="x")

        # Erro (oculto)
        self.lbl_erro_reg = ttk.Label(self.aba_registro, text="",
                                       foreground="#C2185B",
                                       font=("Segoe UI", 9))
        self.lbl_erro_reg.pack(pady=(12, 0))

    # ==========================================================
    # Verificação do servidor
    # ==========================================================
    def _verificar_api(self):
        try:
            r = requests.get(f"{self.auth_api.base_url}/", timeout=2)
            if r.status_code == 200:
                self.lbl_status.config(
                    text="●  Conectado ao servidor",
                    foreground="#008000",
                )
            else:
                self.lbl_status.config(
                    text=f"●  Servidor respondeu {r.status_code}",
                    foreground="#B77900",
                )
        except Exception:
            self.lbl_status.config(
                text="●  Servidor offline",
                foreground="#C2185B",
            )

    # ==========================================================
    # Ações
    # ==========================================================
    def _fazer_login(self):
        nome = self.var_login_nome.get().strip()
        senha = self.var_login_senha.get()

        if not nome or not senha:
            self.lbl_erro_login.config(text="Preencha nome e senha.")
            return

        self.lbl_erro_login.config(text="")
        self.lbl_status.config(text="●  Entrando...", foreground="#666666")
        self.root.update_idletasks()

        try:
            sessao = self.auth_api.login(nome, senha)
        except ErroAuth as e:
            self.lbl_erro_login.config(text=str(e))
            self._verificar_api()
            return

        self._pos_login(sessao, self.var_lembrar_login.get())

    def _fazer_registro(self):
        nome = self.var_reg_nome.get().strip()
        senha = self.var_reg_senha.get()
        senha2 = self.var_reg_senha2.get()

        if not nome or not senha or not senha2:
            self.lbl_erro_reg.config(text="Preencha todos os campos.")
            return
        if len(nome) < 3:
            self.lbl_erro_reg.config(text="O nome precisa ter pelo menos 3 caracteres.")
            return
        if len(senha) < 4:
            self.lbl_erro_reg.config(text="A senha precisa ter pelo menos 4 caracteres.")
            return
        if senha != senha2:
            self.lbl_erro_reg.config(text="As senhas não coincidem.")
            return

        self.lbl_erro_reg.config(text="")
        self.lbl_status.config(text="●  Criando conta...", foreground="#666666")
        self.root.update_idletasks()

        try:
            sessao = self.auth_api.registrar(nome, senha)
        except ErroAuth as e:
            self.lbl_erro_reg.config(text=str(e))
            self._verificar_api()
            return

        self._pos_login(sessao, self.var_lembrar_reg.get())

    def _pos_login(self, sessao: SessaoLocal, lembrar: bool):
        if lembrar:
            try:
                self.sessao_mgr.salvar(sessao)
            except ErroAuth:
                pass  # salvar sessão não é crítico

        self.on_sucesso(sessao)

    def destruir(self):
        self.frame.destroy()