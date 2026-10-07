"""Sophia — Leitor e Rede Social de Mangás.

Ponto de entrada da aplicação. Toda a lógica de UI e navegação vive aqui.
A persistência é delegada a repositórios recebidos por injeção de dependência
(ver composition root no final do arquivo).
"""
from __future__ import annotations

import datetime
import gc
import subprocess
import sys
import os
import shutil
import tkinter as tk
import requests
from tkinter import ttk, filedialog, messagebox, simpledialog

import pymupdf as fitz
from PIL import Image, ImageTk

from notificacoes import GerenciadorNotificacoes
from sons import GerenciadorSons
from auth_api import RepositorioAuthAPI, GerenciadorSessao, SessaoLocal, ErroAuth
from busca_api import RepositorioBuscaAPI, UsuarioBusca, ErroBusca
from chat_api import RepositorioChatAPI, MensagemChat as MensagemChatAPI, ErroChat
from amizades_api import RepositorioAmizadesAPI, Amigo, ErroAmizade
from comentarios_api import RepositorioComentariosAPI, ErroComentario
from tela_login import TelaLogin
from gerenciador_downloads import GerenciadorDownloads, Callbacks
from capa_remota import GerenciadorCapas

from models import Review, Mensagem, Perfil, CatalogoItem
from repositories import (
    CatalogoRepositoryProtocol,
    ChatRepositoryProtocol,
    ErroPersistencia,
    PerfisRepositoryProtocol,
    ProgressoRepositoryProtocol,
    ReviewsRepositoryProtocol,
)

def _pasta_dados() -> str:
    """Onde ficam arquivos que mudam: session, progresso, perfis, pdfs."""
    if getattr(sys, "frozen", False):
        # Executável: usa a pasta onde o .exe está
        return os.path.dirname(sys.executable)
    # Rodando via 'python main.py': usa a pasta do arquivo
    return os.path.dirname(os.path.abspath(__file__))


def _pasta_recursos() -> str:
    """Onde ficam assets empacotados: ícones, áudio, catálogo."""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

class SophiaApp:
    def __init__(
        self,
        root: tk.Tk,
        repo_progresso: ProgressoRepositoryProtocol,
        repo_reviews: ReviewsRepositoryProtocol,
        repo_chat: ChatRepositoryProtocol,
        repo_perfis: PerfisRepositoryProtocol,
        repo_catalogo: CatalogoRepositoryProtocol,
        modo: str = "local",
        sessao: SessaoLocal | None = None,
    ):
        self.root = root
        self.modo = modo
        self.sessao = sessao

        # ---------- Clientes HTTP (só em modo API) ----------
        if self.modo == "api" and sessao is not None:
            self.amizades_api = RepositorioAmizadesAPI(
                "https://sophia-api-lzwc.onrender.com", token=sessao.token,
            )
            self.comentarios_api = RepositorioComentariosAPI(
                "https://sophia-api-lzwc.onrender.com", token=sessao.token,
            )
            self.chat_api = RepositorioChatAPI(
                "https://sophia-api-lzwc.onrender.com", token=sessao.token,
            )
            self.busca_api = RepositorioBuscaAPI(
                "https://sophia-api-lzwc.onrender.com", token=sessao.token,
            )
        else:
            self.amizades_api = None
            self.comentarios_api = None
            self.chat_api = None
            self.busca_api = None

        self._perfil_alvo_nome: str | None = None

        self.root.title("Sophia")
        self.root.geometry("1024x768")
        self.root.configure(bg="#F0F4F8")

        self._fav_frames: dict[str, ttk.Frame] = {}
        self.icones_toolbar = {}
        from collections import deque
        self.capas_memoria = deque(maxlen=100)

        self._detalhes_item_atual: CatalogoItem | None = None
        self._detalhes_origem: str = "catalogo"

        self._downloads_cancelados: set[str] = set()
        self._downloads_ativos: dict[str, str] = {}

        self._chat_msgs_renderizadas: set[str] = set()

        self._chat_nao_lidas_por_amigo: dict[str, int] = {}
        self._amizades_notificadas: set[str] = set()
        self._comentarios_vistos: set[str] = set()
        self._polling_inicializado = False

        self._mangas_desbloqueados: bool = False
        self._manga_selecionado: CatalogoItem | None = None
        self._volumes_ui: dict[str, dict] = {}
        self._fila_download_manga: list = []

        pasta_sons = os.path.join(_pasta_recursos(), "assets", "audio")
        self.sons = GerenciadorSons(pasta_sons, ativo=True)

        self.notificacoes = GerenciadorNotificacoes(self.root)
        self.notificacoes.on_click_global = self._on_notificacao_click

        self.style = ttk.Style()
        temas = self.style.theme_names()
        if "vista" in temas:
            self.style.theme_use("vista")
        elif "xpnative" in temas:
            self.style.theme_use("xpnative")

        self.style.configure(".", font=("Segoe UI", 9), background="#F0F4F8")
        self.style.configure("TLabel", background="#F0F4F8")
        self.style.configure("TLabelframe", background="#F0F4F8")
        self.style.configure("TLabelframe.Label",
                             font=("Segoe UI", 9, "bold"), foreground="#003366")
        self.style.configure("Banner.TFrame", background="#003366")

        self.repo_progresso = repo_progresso
        self.repo_reviews = repo_reviews
        self.repo_chat = repo_chat
        self.repo_perfis = repo_perfis
        self.repo_catalogo = repo_catalogo

        pasta_dados = _pasta_dados()
        pasta_recursos = _pasta_recursos()
        self.pasta_pdf = os.path.join(pasta_dados, "pdf_padrao")
        self.gerenciador = GerenciadorDownloads(self.root, self.pasta_pdf)
        self.capas = GerenciadorCapas(
            os.path.join(pasta_dados, "assets", "cache_capas"))
        self._cards_catalogo: dict[str, dict] = {}

        self.doc = None
        self.caminho_pdf_atual: str | None = None
        self.obra_selecionada: str | None = None
        self.pagina_atual = 0
        self.total_paginas = 0
        self.amigo_chat_ativo: str | None = None
        self._resize_after_id: str | None = None
        self._chat_ultimo_id: str | None = None
        # ---------- Zoom do leitor ----------
        self.zoom_atual = 1.0
        self.zoom_min = 0.25
        self.zoom_max = 4.0
        # ---------- SCROLL ROUTER ----------
        self.root.bind_all("<MouseWheel>", self._rotear_scroll_canvas)
        self.root.bind_all("<Button-4>", self._scroll_linux_cima)
        self.root.bind_all("<Button-5>", self._scroll_linux_baixo)

        self._criar_menu()
        self.criar_toolbar_icones()

        self.container_principal = ttk.Frame(self.root)
        self.container_principal.pack(expand=True, fill="both")

        self.frame_inicio = ttk.Frame(self.container_principal)
        self.frame_obras = ttk.Frame(self.container_principal)
        self.frame_volumes = ttk.Frame(self.container_principal)
        self.frame_leitor = ttk.Frame(self.container_principal)
        self.frame_perfil = ttk.Frame(self.container_principal)
        self.frame_reviews = ttk.Frame(self.container_principal)
        self.frame_chatochat = ttk.Frame(self.container_principal)
        self.frame_catalogo = ttk.Frame(self.container_principal)
        self.frame_detalhes_obra = ttk.Frame(self.container_principal)
        self.frame_volumes_manga = ttk.Frame(self.container_principal)

        self.montar_tela_leitor()
        self.mostrar_tela_inicio()
        self._loop_verificar_conexao()
        self._loop_polling_chat()

        self.root.bind("<Left>", lambda e: self.pagina_anterior())
        self.root.bind("<Right>", lambda e: self.proxima_pagina())

    # ==========================================================
    # HELPERS
    # ==========================================================
    def _obra_tem_pdfs_local(self, nome_obra: str) -> bool:
        caminho = os.path.join(self.pasta_pdf, nome_obra)
        if not os.path.isdir(caminho):
            return False
        try:
            return any(f.lower().endswith(".pdf") for f in os.listdir(caminho))
        except OSError:
            return False

    def _carregar_capa_ajustada(self, caminho: str, max_w: int, max_h: int,
                                  chave: str):
        if not caminho or not os.path.exists(caminho):
            return None
        try:
            img = Image.open(caminho)
            img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
            tk_img = ImageTk.PhotoImage(img, master=self.root)
            self.icones_toolbar[chave] = tk_img
            return tk_img
        except Exception:
            return None

    def _carregar_foto_perfil(self, foto_path: str, tamanho: tuple):
        """Carrega foto de perfil que pode ser:
        - base64 (novo formato, sincroniza entre PCs)
        - caminho local antigo (compatibilidade)
        - vazio (usa placeholder)
        """
        if not foto_path:
            return None

        # Caso 1: base64 (novo formato)
        if foto_path.startswith("data:image/"):
            try:
                import base64
                from io import BytesIO
                _, b64 = foto_path.split(",", 1)
                dados = base64.b64decode(b64)
                img = Image.open(BytesIO(dados))
                img.thumbnail(tamanho, Image.Resampling.LANCZOS)
                tk_img = ImageTk.PhotoImage(img, master=self.root)
                self.icones_toolbar[f"foto_{id(tk_img)}"] = tk_img
                return tk_img
            except Exception as e:
                print(f"[foto] erro base64: {e}")
                return None

        # Caso 2: caminho local (formato antigo)
        return self.carregar_imagem(foto_path, tamanho)


    def _aplicar_capa(self, label: tk.Label, caminho: str, item_id: str) -> None:
        try:
            img = self._carregar_capa_ajustada(caminho, 180, 260,
                                                f"capa_{item_id}")
            if img:
                label.config(image=img, text="")
                label.image = img
        except Exception:
            pass

    def _aplicar_capa_detalhe(self, label: tk.Label, caminho: str,
                                item_id: str) -> None:
        """Aplica capa na tela de detalhes (tamanho maior)."""
        try:
            img = self._carregar_capa_ajustada(caminho, 200, 280,
                                                f"capa_det_{item_id}")
            if img:
                label.config(image=img, text="")
                label.image = img
        except Exception:
            pass

    def _contar_volumes_baixados(self, item: CatalogoItem) -> int:
        pasta = os.path.join(self.pasta_pdf, item.nome)
        if not os.path.isdir(pasta):
            return 0
        n = 0
        for vol in item.volumes:
            caminho = os.path.join(pasta, f"{vol.titulo}.pdf")
            if os.path.exists(caminho):
                n += 1
        return n

    # ==========================================================
    # CONEXÃO + POLLING
    # ==========================================================
    def _verificar_conexao(self):
        if self.modo != "api":
            self._lbl_status.config(text="●  Modo local", fg="#B77900")
            return

        try:
            r = requests.get("https://sophia-api-lzwc.onrender.com/", timeout=2)
            if r.status_code == 200:
                self._lbl_status.config(text="●  Conectado ao servidor", fg="#008000")
            else:
                self._lbl_status.config(
                    text=f"●  Servidor respondeu {r.status_code}", fg="#B77900")
        except requests.ConnectionError:
            self._lbl_status.config(text="●  Servidor offline", fg="#C2185B")
        except requests.Timeout:
            self._lbl_status.config(text="●  Servidor não respondeu", fg="#C2185B")

    def _loop_verificar_conexao(self):
        self._verificar_conexao()
        self.root.after(30_000, self._loop_verificar_conexao)

    def _loop_polling_chat(self):
        try:
            if not self._polling_inicializado:
                self._inicializar_estado_polling()
                self._polling_inicializado = True
            else:
                self._atualizar_chat_se_aberto()
                self._verificar_notificacoes_globais()
        except Exception as e:
            print(f"[chat] erro no polling: {e}")
        self.root.after(5_000, self._loop_polling_chat)

    def _atualizar_chat_se_aberto(self):
        if self.chat_api is None:
            return
        if not self.frame_chatochat.winfo_ismapped():
            return
        if not self.amigo_chat_ativo:
            return

        try:
            mensagens = self.chat_api.listar_mensagens(self.amigo_chat_ativo)
        except ErroChat:
            return

        if not mensagens:
            return

        if not self.chat_mensagens_frame.winfo_children():
            self._chat_msgs_renderizadas.clear()
            for m in mensagens:
                self._render_mensagem(m)
                self._chat_msgs_renderizadas.add(m.id)
            self._chat_ultimo_id = mensagens[-1].id
            self.chat_mensagens_canvas.update_idletasks()
            self.chat_mensagens_canvas.yview_moveto(1.0)
            return

        novas = [m for m in mensagens if m.id not in self._chat_msgs_renderizadas]
        if not novas:
            return

        try:
            pos = self.chat_mensagens_canvas.yview()
            estava_no_fim = pos[1] >= 0.98
        except Exception:
            estava_no_fim = True

        meu_nome = self.sessao.nome if self.sessao else ""
        novas_recebidas = [m for m in novas if m.remetente_nome != meu_nome]
        if novas_recebidas:
            self.sons.tocar("receber")

        for m in novas:
            self._render_mensagem(m)
            self._chat_msgs_renderizadas.add(m.id)

        self._chat_ultimo_id = mensagens[-1].id

        if estava_no_fim:
            self.chat_mensagens_canvas.update_idletasks()
            self.chat_mensagens_canvas.yview_moveto(1.0)

    def _inicializar_estado_polling(self):
        if self.chat_api is None or self.sessao is None:
            return

        try:
            conversas = self.chat_api.listar_conversas()
            for c in conversas:
                self._chat_nao_lidas_por_amigo[c.amigo_nome] = c.nao_lidas
        except ErroChat:
            pass

        try:
            pendentes = self.amizades_api.listar_pendentes()
            for p in pendentes:
                self._amizades_notificadas.add(p.amizade_id)
        except ErroAmizade:
            pass

        try:
            comentarios = self.comentarios_api.listar(self.sessao.nome)
            for c in comentarios:
                self._comentarios_vistos.add(c.id)
        except ErroComentario:
            pass

    def _verificar_notificacoes_globais(self):
        if self.chat_api is None or self.sessao is None:
            return

        try:
            conversas = self.chat_api.listar_conversas()
        except ErroChat:
            conversas = []

        for c in conversas:
            anterior = self._chat_nao_lidas_por_amigo.get(c.amigo_nome, 0)
            if c.nao_lidas > anterior:
                estou_nessa_conversa = (
                    self.frame_chatochat.winfo_ismapped()
                    and self.amigo_chat_ativo == c.amigo_nome
                )
                if not estou_nessa_conversa:
                    preview = c.ultima_mensagem or "(sem texto)"
                    if len(preview) > 60:
                        preview = preview[:57] + "..."
                    self._notificar(
                        titulo=f"Nova mensagem de {c.amigo_nome}",
                        mensagem=preview,
                        icone="💬",
                        tipo="chat",
                        dado={"amigo": c.amigo_nome},
                    )
            self._chat_nao_lidas_por_amigo[c.amigo_nome] = c.nao_lidas

        try:
            pendentes = self.amizades_api.listar_pendentes()
        except ErroAmizade:
            pendentes = []

        for p in pendentes:
            if p.amizade_id not in self._amizades_notificadas:
                self._amizades_notificadas.add(p.amizade_id)
                self._notificar(
                    titulo="Novo pedido de amizade",
                    mensagem=f"{p.nome} quer ser seu amigo",
                    icone="👤",
                    tipo="amizade",
                    dado={"amizade_id": p.amizade_id, "nome": p.nome},
                )

        try:
            comentarios = self.comentarios_api.listar(self.sessao.nome)
        except ErroComentario:
            comentarios = []

        for c in comentarios:
            if c.id not in self._comentarios_vistos:
                self._comentarios_vistos.add(c.id)
                if c.autor_nome != self.sessao.nome:
                    texto = c.texto
                    if len(texto) > 60:
                        texto = texto[:57] + "..."
                    self._notificar(
                        titulo=f"Novo comentário de {c.autor_nome}",
                        mensagem=texto,
                        icone="💬",
                        tipo="comentario",
                        dado={"alvo": self.sessao.nome},
                    )

    # ==========================================================
    # NOTIFICAÇÕES
    # ==========================================================
    def _notificar(self, titulo: str, mensagem: str,
                    icone: str = "💬", tipo: str = "geral",
                    dado: dict | None = None, som: str = "notificacao"):
        self.sons.tocar(som)
        self.notificacoes.notificar(
            titulo=titulo,
            mensagem=mensagem,
            icone=icone,
            tipo=tipo,
            dado=dado or {},
        )

    def _on_notificacao_click(self, tipo: str, dado: dict):
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except tk.TclError:
            pass

        if tipo == "chat":
            self._esconder_todas(self.frame_chatochat)
            self.frame_chatochat.pack(expand=True, fill="both")
            self.montar_tela_chatochat()
            amigo = dado.get("amigo")
            if amigo:
                self.abrir_conversa_chat(amigo)
        elif tipo == "amizade":
            self.abrir_tela_amigos()
        elif tipo == "comentario":
            alvo = dado.get("alvo")
            if alvo:
                self._abrir_perfil_de(alvo)
        elif tipo == "download":
            nome = dado.get("nome")
            if nome:
                self.mostrar_tela_volumes(nome)

    # ==========================================================
    # PERSISTÊNCIA
    # ==========================================================
    def _executar_persistencia(self, acao, mensagem_erro: str) -> bool:
        try:
            acao()
            return True
        except ErroPersistencia as e:
            messagebox.showerror(mensagem_erro, str(e))
            return False

    # ==========================================================
    # MENU
    # ==========================================================
    def _criar_menu(self):
        barra = tk.Menu(self.root, bg="#F0F4F8", fg="#000000")

        m_arquivo = tk.Menu(barra, tearoff=0)
        m_arquivo.add_command(label="Importar pasta de obra...",
                              command=self.importar_pasta_de_obra)
        m_arquivo.add_command(label="Abrir PDF Externo...",
                              command=self.abrir_pdf_externo)
        m_arquivo.add_separator()
        m_arquivo.add_command(label="Sair", command=self.root.quit)
        barra.add_cascade(label="Arquivo", menu=m_arquivo)

        m_biblioteca = tk.Menu(barra, tearoff=0)
        m_biblioteca.add_command(label="Ver Obras", command=self.mostrar_tela_obras)
        m_biblioteca.add_command(label="Abrir pasta da biblioteca",
                                 command=self.abrir_pasta_biblioteca)
        m_biblioteca.add_separator()
        m_biblioteca.add_command(label="Atualizar lista",
                                 command=self.mostrar_tela_obras)
        barra.add_cascade(label="Biblioteca", menu=m_biblioteca)

        m_sobre = tk.Menu(barra, tearoff=0)
        m_sobre.add_command(label="Sobre a Sophia",
                            command=self.abrir_janela_sobre)
        m_sobre.add_command(label="Comunidade",
                            command=self.abrir_tela_comunidade)
        barra.add_cascade(label="Ajuda", menu=m_sobre)

        m_exibir = tk.Menu(barra, tearoff=0)
        m_exibir.add_command(label="Página Inicial", command=self.mostrar_tela_inicio)
        barra.add_cascade(label="Exibir", menu=m_exibir)

        self.root.config(menu=barra)

    # ==========================================================
    # SCROLL ROUTER
    # ==========================================================
    def _canvas_sob_mouse(self, event) -> tk.Canvas | None:
        try:
            widget = self.root.winfo_containing(event.x_root, event.y_root)
            while widget is not None:
                if isinstance(widget, tk.Canvas):
                    return widget
                widget = getattr(widget, "master", None)
        except tk.TclError:
            pass
        return None

    def _rotear_scroll_canvas(self, event):
        # Otimização: evita winfo_containing pra widgets que não são Canvas
        try:
            widget = event.widget
        except AttributeError:
            widget = None

        # Se o widget sob o mouse for um Canvas, usa direto (evita lookup caro)
        canvas = None
        if isinstance(widget, tk.Canvas):
            canvas = widget
        else:
            # Fallback: sobe a árvore até achar um Canvas
            w = widget
            while w is not None:
                if isinstance(w, tk.Canvas):
                    canvas = w
                    break
                w = getattr(w, "master", None)

        if canvas is None:
            return

        delta = getattr(event, "delta", 0)
        if not delta:
            return

        unidades = int(-delta / 120)
        if unidades == 0:
            unidades = -1 if delta > 0 else 1

        try:
            if getattr(canvas, "_scroll_horizontal", False):
                canvas.xview_scroll(unidades, "units")
            else:
                canvas.yview_scroll(unidades, "units")
            return "break"
        except tk.TclError:
            return
        
    def _scroll_linux_cima(self, event):
        canvas = self._canvas_sob_mouse(event)
        if canvas is not None:
            canvas.yview_scroll(-1, "units")
            return "break"

    def _scroll_linux_baixo(self, event):
        canvas = self._canvas_sob_mouse(event)
        if canvas is not None:
            canvas.yview_scroll(1, "units")
            return "break"

    # ==========================================================
    # TOOLBAR / IMAGENS
    # ==========================================================
    def carregar_icone(self, nome_arquivo: str, tamanho=(20, 20)):
        caminho = os.path.join(_pasta_recursos(), "assets", "icones", nome_arquivo)
        return self.carregar_imagem(caminho, tamanho, chave_cache=nome_arquivo)

    def carregar_imagem(self, caminho: str, tamanho: tuple, chave_cache: str | None = None):
        if not caminho or not os.path.exists(caminho):
            return None
        try:
            img = Image.open(caminho).resize(tamanho, Image.Resampling.LANCZOS)
            tk_img = ImageTk.PhotoImage(img, master=self.root)
            if chave_cache:
                self.icones_toolbar[chave_cache] = tk_img
            return tk_img
        except Exception:
            return None

    def criar_toolbar_icones(self):
        frame = ttk.Frame(self.root, padding=(5, 3), relief="groove")
        frame.pack(side="top", fill="x")

        def _btn(icone, texto, comando):
            return tk.Button(
                frame, image=icone, text=texto, compound="left", command=comando,
                relief="flat", bd=1, padx=4, pady=2,
                bg="#F0F4F8", activebackground="#D0E3F7",
            )

        _btn(self.carregar_icone("home.png"), " Início",
             self.mostrar_tela_inicio).pack(side="left", padx=2)
        ttk.Separator(frame, orient="vertical").pack(side="left", fill="y", padx=5)
        _btn(self.carregar_icone("profile.png"), " Perfil",
             self.abrir_tela_perfil).pack(side="left", padx=2)
        _btn(self.carregar_icone("reviews.png"), " Minhas Reviews",
             self.abrir_tela_reviews).pack(side="left", padx=2)
        _btn(self.carregar_icone("friendlist.png"), " Amigos",
             self.abrir_tela_amigos).pack(side="left", padx=2)
        _btn(self.carregar_icone("catalog.png"), " Catálogo",
             self.abrir_tela_catalogo).pack(side="left", padx=2)

        self._lbl_status = tk.Label(
            frame, text="●  Modo local",
            font=("Segoe UI", 9, "bold"), fg="#B77900", bg="#F0F4F8",
        )
        self._lbl_status.pack(side="right", padx=12)

        if self.modo == "api":
            busca_frame = ttk.Frame(frame)
            busca_frame.pack(side="right", padx=(0, 8))

            tk.Label(busca_frame, text="🔍 Busque um usuário:",
                     bg="#F0F4F8", fg="#003366",
                     font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 4))

            self.var_busca = tk.StringVar()
            self.entrada_busca = ttk.Entry(busca_frame, textvariable=self.var_busca,
                                            width=22, font=("Segoe UI", 9))
            self.entrada_busca.pack(side="left", padx=4)
            self.entrada_busca.bind("<Return>", lambda e: self._buscar_usuario())

    # ==========================================================
    # NAVEGAÇÃO
    # ==========================================================
    def _esconder_todas(self, manter: tk.Frame | None = None):
        for tela in (self.frame_inicio, self.frame_obras, self.frame_volumes,
                     self.frame_leitor, self.frame_perfil, self.frame_reviews,
                     self.frame_chatochat, self.frame_catalogo,
                     self.frame_detalhes_obra, self.frame_volumes_manga):
            if tela is not manter:
                tela.pack_forget()

    def mostrar_tela_inicio(self):
        self._esconder_todas(self.frame_inicio)
        self.frame_inicio.pack(expand=True, fill="both")
        self._montar_conteudo_inicio()

    def mostrar_tela_obras(self):
        self._esconder_todas(self.frame_obras)
        self.frame_obras.pack(expand=True, fill="both")
        self._montar_grid_obras()

    def mostrar_tela_volumes(self, nome_obra: str):
        self.obra_selecionada = nome_obra
        self._esconder_todas(self.frame_volumes)
        self.frame_volumes.pack(expand=True, fill="both")
        self._montar_grid_volumes(nome_obra)

    def abrir_tela_reviews(self):
        self._esconder_todas(self.frame_reviews)
        self.frame_reviews.pack(expand=True, fill="both")
        self.atualizar_tela_reviews()

    def abrir_tela_amigos(self):
        self._esconder_todas(self.frame_chatochat)
        self.frame_chatochat.pack(expand=True, fill="both")
        self.montar_tela_chatochat()

    def abrir_tela_perfil(self):
        self._esconder_todas(self.frame_perfil)
        self.frame_perfil.pack(expand=True, fill="both")
        self._montar_conteudo_perfil(alvo_nome=None)

    # ==========================================================
    # TELA: FEED (home)
    # ==========================================================
    def _montar_conteudo_inicio(self):
        for w in self.frame_inicio.winfo_children():
            w.destroy()

        banner = tk.Frame(self.frame_inicio, bg="#003366", height=60)
        banner.pack(fill="x")
        banner.pack_propagate(False)
        tk.Label(banner, text="🏠 Feed",
                 font=("Segoe UI", 16, "bold"), fg="white",
                 bg="#003366").pack(side="left", padx=20, pady=10)
        tk.Button(banner, text="👥 Ver Comunidade",
                  command=self.abrir_tela_comunidade,
                  bg="#DCEBFA", fg="#003366",
                  relief="raised").pack(side="right", padx=20, pady=10)

        canvas = tk.Canvas(self.frame_inicio, bg="#F0F4F8", highlightthickness=0)
        scroll = ttk.Scrollbar(self.frame_inicio, orient="vertical", command=canvas.yview)
        conteudo = ttk.Frame(canvas)
        conteudo.bind("<Configure>",
                      lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=conteudo, anchor="nw", width=1000,
                             tags="feed_conteudo")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig("feed_conteudo", width=e.width))

        self._montar_secao_destaques(conteudo)
        self._montar_secao_reviews_recentes(conteudo)

    def _montar_secao_destaques(self, parent):
        box = ttk.LabelFrame(parent, text=" 🔥 Obras em Destaque ", padding=15)
        box.pack(fill="x", padx=20, pady=(15, 10))

        NOMES_DESTAQUE = ["Naruto", "O Cortiço", "O Alienista", "Hunter x Hunter"]

        itens_destaque = []
        for nome in NOMES_DESTAQUE:
            item = self.repo_catalogo.obter_por_nome(nome)
            if item is not None:
                itens_destaque.append(item)

        if not itens_destaque:
            ttk.Label(box, text="Nenhuma obra em destaque configurada.",
                      font=("Segoe UI", 10, "italic"),
                      foreground="#888888").pack(pady=30)
            return

        grid = ttk.Frame(box)
        grid.pack(fill="x", pady=10)

        for idx, item in enumerate(itens_destaque):
            col = ttk.Frame(grid)
            col.pack(side="left", expand=True, padx=8)

            tk_capa = None
            if self._obra_tem_pdfs_local(item.nome):
                caminho_local = os.path.join(self.pasta_pdf, item.nome)
                try:
                    arquivos = [f for f in os.listdir(caminho_local)
                                if f.lower().endswith(".pdf")]
                    if arquivos:
                        tk_capa = self.gerar_capa_miniatura(
                            os.path.join(caminho_local, sorted(arquivos)[0]))
                except OSError:
                    pass

            if tk_capa:
                btn = tk.Button(col, image=tk_capa, relief="flat", bd=1,
                                bg="#FFFFFF", cursor="hand2",
                                command=lambda it=item: self._abrir_detalhes(it))
                btn.pack()
            else:
                capa_frame = tk.Frame(col, bg="#D0E3F7", width=140, height=200)
                capa_frame.pack()
                capa_frame.pack_propagate(False)
                placeholder = tk.Button(
                    capa_frame, text="📖", bg="#D0E3F7", fg="#003366",
                    font=("Segoe UI", 40), relief="flat", cursor="hand2",
                    command=lambda it=item: self._abrir_detalhes(it))
                placeholder.pack(expand=True, fill="both")

                if item.capa_url:
                    caminho_cache = self.capas.obter_cache(item.id)
                    if caminho_cache:
                        img = self._carregar_capa_ajustada(
                            caminho_cache, 140, 200, f"capa_{item.id}")
                        if img:
                            placeholder.config(image=img, text="")
                            placeholder.image = img
                    else:
                        def _cb(caminho, lbl=placeholder, iid=item.id):
                            self.root.after(0, lambda: self._aplicar_capa(lbl, caminho, iid))
                        self.capas.baixar_async(item.id, item.capa_url, _cb)

            ttk.Label(col, text=item.nome[:18],
                      font=("Segoe UI", 9, "bold"),
                      wraplength=120, justify="center").pack(pady=(6, 2))

            media, total = self.repo_reviews.media_da_obra(item.nome, item.id)
            if total > 0:
                estrelas = self._formatar_estrelas(media)
                ttk.Label(col, text=f"{estrelas} {media:.1f} ({total})",
                          font=("Segoe UI", 8),
                          foreground="#B77900").pack()
            else:
                ttk.Label(col, text="Sem avaliações",
                          font=("Segoe UI", 8, "italic"),
                          foreground="#888888").pack()

    def _montar_secao_reviews_recentes(self, parent):
        box = ttk.LabelFrame(parent, text=" 📝 Reviews Recentes ", padding=15)
        box.pack(fill="x", padx=20, pady=(10, 20))

        todas = sorted(self.repo_reviews.reviews,
                       key=lambda r: r.data, reverse=True)[:10]

        if not todas:
            ttk.Label(box,
                      text="Nenhuma review publicada ainda.\n\n"
                           "Vá em 'Minhas Reviews' e escreva a primeira!",
                      font=("Segoe UI", 10, "italic"),
                      foreground="#888888", justify="center").pack(pady=30)
            return

        for review in todas:
            card = ttk.Frame(box, relief="groove", padding=12)
            card.pack(fill="x", pady=6)

            header = ttk.Frame(card)
            header.pack(fill="x")

            ttk.Label(header, text=f"👤 {review.perfil}",
                      font=("Segoe UI", 10, "bold"),
                      foreground="#003366").pack(side="left")
            ttk.Label(header, text=f"  •  {review.data}",
                      font=("Segoe UI", 8),
                      foreground="#888888").pack(side="left")
            ttk.Label(header, text=f"  —  {review.obra}",
                      font=("Segoe UI", 9, "italic"),
                      foreground="#005A9E").pack(side="left")

            estrelas = "★" * review.nota + "☆" * (5 - review.nota)
            ttk.Label(card, text=f"{estrelas}   {review.nota}/5",
                      font=("Segoe UI", 11, "bold"),
                      foreground="#B77900").pack(anchor="w", pady=(4, 2))

            ttk.Label(card, text=review.texto, wraplength=900,
                      justify="left", font=("Segoe UI", 9)).pack(anchor="w")

    # ==========================================================
    # TELA: COMUNIDADE
    # ==========================================================
    def abrir_tela_comunidade(self):
        if self.modo != "api":
            messagebox.showinfo("Modo local",
                                 "A comunidade está disponível apenas em modo API.")
            return

        janela = tk.Toplevel(self.root)
        janela.title("Comunidade Sophia")
        janela.geometry("560x620")
        janela.configure(bg="#F0F4F8")
        janela.transient(self.root)

        corpo = ttk.Frame(janela, padding=18)
        corpo.pack(fill="both", expand=True)

        ttk.Label(corpo, text="👥 Comunidade",
                  font=("Segoe UI", 16, "bold"),
                  foreground="#003366").pack(anchor="w")
        ttk.Label(corpo,
                  text="Clique num usuário para ver o perfil dele e enviar uma amizade.",
                  font=("Segoe UI", 9, "italic"),
                  foreground="#666666").pack(anchor="w", pady=(2, 14))

        try:
            todos_usuarios = self._listar_todos_usuarios()
        except Exception as e:
            ttk.Label(corpo, text=f"⚠ {e}",
                      foreground="#C2185B",
                      font=("Segoe UI", 10)).pack(pady=20)
            ttk.Button(corpo, text="Fechar",
                       command=janela.destroy).pack()
            return

        meu_nome = self.sessao.nome if self.sessao else ""
        outros = [u for u in todos_usuarios if u.get("nome") != meu_nome]

        ttk.Label(corpo, text=f"{len(outros)} usuário(s) na comunidade",
                  font=("Segoe UI", 9),
                  foreground="#555555").pack(anchor="w", pady=(0, 8))

        if not outros:
            ttk.Label(corpo,
                      text="Nenhum outro usuário cadastrado ainda.",
                      font=("Segoe UI", 10, "italic"),
                      foreground="#888888").pack(pady=40)
            ttk.Button(corpo, text="Fechar",
                       command=janela.destroy).pack()
            return

        frame_lista = ttk.Frame(corpo, relief="sunken", borderwidth=1)
        frame_lista.pack(fill="both", expand=True)

        canvas = tk.Canvas(frame_lista, bg="#FFFFFF", highlightthickness=0)
        scroll = ttk.Scrollbar(frame_lista, orient="vertical", command=canvas.yview)
        interior = ttk.Frame(canvas)
        interior.bind("<Configure>",
                      lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=interior, anchor="nw", width=490)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        for u in outros:
            linha = ttk.Frame(interior, padding=10)
            linha.pack(fill="x", padx=4, pady=3)

            btn = tk.Button(
                linha,
                text=f"👤  {u['nome']}",
                anchor="w", justify="left",
                bg="#FFFFFF", activebackground="#D0E3F7",
                relief="flat", bd=0, cursor="hand2",
                font=("Segoe UI", 11),
                command=lambda n=u["nome"]: self._abrir_perfil_e_fechar(n, janela),
            )
            btn.pack(side="left", fill="x", expand=True)

            ttk.Label(linha, text=u.get("criado_em", ""),
                      font=("Segoe UI", 8),
                      foreground="#888888").pack(side="right", padx=8)

        ttk.Button(corpo, text="Fechar",
                   command=janela.destroy).pack(pady=(14, 0))

    def _listar_todos_usuarios(self):
        try:
            return [
                {"id": u.id, "nome": u.nome, "criado_em": u.criado_em}
                for u in self.busca_api.listar_todos()
            ]
        except ErroBusca as e:
            raise e

    # ==========================================================
    # JANELA: SOBRE A SOPHIA
    # ==========================================================
    def abrir_janela_sobre(self):
        janela = tk.Toplevel(self.root)
        janela.title("Sobre a Sophia")
        janela.geometry("820x680")
        janela.configure(bg="#F0F4F8")
        janela.transient(self.root)

        canvas = tk.Canvas(janela, bg="#F0F4F8", highlightthickness=0)
        scroll = ttk.Scrollbar(janela, orient="vertical", command=canvas.yview)
        conteudo = ttk.Frame(canvas)
        conteudo.bind("<Configure>",
                      lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=conteudo, anchor="nw", width=780)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        hora = datetime.datetime.now().hour
        saudacao = "Bom dia" if hora < 12 else ("Boa tarde" if hora < 18 else "Boa noite")

        # ---------- Banner ----------
        banner = tk.Frame(conteudo, bg="#003366", padx=20, pady=20)
        banner.pack(fill="x", padx=15, pady=15)
        tk.Label(banner, text=f"{saudacao}! 📖 Sophia — Leitura e Comunidade",
                 font=("Segoe UI", 15, "bold"), fg="#FFFFFF",
                 bg="#003366").pack(anchor="w")
        tk.Label(banner,
                 text="Do grego Σοφία: sabedoria. Um espaço para ler, avaliar e compartilhar.",
                 font=("Segoe UI", 10), fg="#D0E3F7",
                 bg="#003366").pack(anchor="w", pady=(5, 0))

        main = ttk.Frame(conteudo, relief="ridge", padding=15)
        main.pack(expand=True, fill="both", padx=15, pady=(0, 15))

        # ---------- Sobre ----------
        box_sobre = ttk.LabelFrame(main, text=" 🎯 Sobre a Sophia ", padding=12)
        box_sobre.pack(fill="x", expand=False, padx=5, pady=(0, 10))
        ttk.Label(box_sobre, text=(
            "Sophia é um leitor de mangás, livros e quadrinhos que também funciona "
            "como uma rede social de leitura.\n\n"
            "A ideia é simples: aqui você não só lê — você conversa sobre o que leu. "
            "Dá para avaliar obras, favoritar as preferidas, comentar no mural dos "
            "amigos, trocar mensagens e descobrir novas histórias pelas recomendações "
            "da comunidade.\n\n"
            "O nome vem do grego Σοφία, que significa sabedoria. É uma homenagem à "
            "curiosidade de quem lê e à vontade de compartilhar o que aprendeu."
        ), wraplength=730, justify="left").pack(anchor="w", fill="x", expand=True)

        # ---------- O que dá para fazer ----------
        box_recursos = ttk.LabelFrame(main, text=" ✨ O que dá para fazer ", padding=12)
        box_recursos.pack(fill="x", expand=False, padx=5, pady=5)
        box_recursos.columnconfigure(1, weight=1)

        recursos = [
            (" 📚 Leitura de PDFs:",
             "Abra mangás, livros e quadrinhos direto no app. Renderização nítida com "
             "PyMuPDF, salvamento automático da página em que você parou e navegação "
             "por teclado (setas esquerda/direita)."),
            (" 🗂️ Biblioteca organizada:",
             "Todas as suas obras separadas por tema (Livros, Mangás). Cada uma com "
             "capa, autor, ano, sinopse e contagem de volumes."),
            (" 📥 Catálogo com download integrado:",
             "Baixe obras direto do Internet Archive ou direto do nosso servidor, "
             "volume por volume, com barra de progresso e cancelamento."),
            (" ⭐ Avaliações e notas:",
             "Dê de 1 a 5 estrelas, escreva uma análise e veja a média das obras. "
             "Suas reviews ficam no seu perfil e no mural do catálogo."),
            (" 💬 Mural de recados:",
             "Visite o perfil de outros usuários, leia o que estão lendo e deixe um "
             "recado. Um cantinho de comunidade dentro do app."),
            (" 👥 Amizades e busca:",
             "Busque outros leitores, envie pedidos de amizade e acompanhe o que eles "
             "estão lendo."),
            (" 💌 ChatoChat:",
             "Converse em tempo real com seus amigos. Cada conversa tem seu histórico "
             "e notificações quando chegam mensagens novas."),
            (" 🔥 Feed com destaques:",
             "A tela inicial mostra obras em destaque e as reviews mais recentes da "
             "comunidade, para você descobrir novas leituras."),
            (" 🔒 Conteúdo exclusivo:",
             "Alguns mangás são protegidos por código de acesso, mantendo a "
             "distribuição controlada onde necessário."),
        ]
        for i, (titulo, desc) in enumerate(recursos):
            ttk.Label(box_recursos, text=titulo,
                      font=("Segoe UI", 9, "bold"),
                      foreground="#003366").grid(row=i, column=0, sticky="nw",
                                                  padx=(0, 15), pady=8)
            ttk.Label(box_recursos, text=desc, justify="left",
                      wraplength=560).grid(row=i, column=1, sticky="ew", pady=8)

        # ---------- Como usar ----------
        box_dicas = ttk.LabelFrame(main, text=" 🧭 Como navegar ", padding=12)
        box_dicas.pack(fill="x", expand=False, padx=5, pady=(10, 5))
        ttk.Label(box_dicas, text=(
            "• Início — feed com destaques e reviews recentes\n"
            "• Perfil — edite sua bio, foto e até 5 favoritos\n"
            "• Minhas Reviews — escreva, edite e exclua suas avaliações\n"
            "• Amigos — busca, mural e ChatoChat\n"
            "• Catálogo — todas as obras, divididas em Livros e Mangás\n"
            "• Setas do teclado — passam página no leitor\n"
            "• Clique-direito numa capa (na biblioteca) — marcar/desmarcar como lido"
        ), wraplength=730, justify="left").pack(anchor="w", fill="x", expand=True)

        # ---------- Créditos ----------
        box_creditos = ttk.LabelFrame(main, text=" 💡 Créditos ", padding=12)
        box_creditos.pack(fill="x", expand=False, padx=5, pady=5)
        ttk.Label(box_creditos, text=(
            "Projeto de estudo e portfólio de Engenharia de Software.\n"
            "Desenvolvido em Python com Tkinter, PyMuPDF e Pillow.\n"
            "Servidor em FastAPI + SQLite. Imagens hospedadas em Cloudflare R2.\n"
            "Obras de domínio público vindas do Internet Archive."
        ), wraplength=730, justify="left",
                  foreground="#555555").pack(anchor="w", fill="x", expand=True)

        ttk.Button(main, text="Fechar", command=janela.destroy).pack(pady=(15, 0))

    # ==========================================================
    # TELA: CATÁLOGO
    # ==========================================================
    def abrir_tela_catalogo(self):
        self._esconder_todas(self.frame_catalogo)
        self.frame_catalogo.pack(expand=True, fill="both")
        self._montar_grid_catalogo()

    def _montar_grid_catalogo(self, filtro_tema: str | None = None):
        for w in self.frame_catalogo.winfo_children():
            w.destroy()

        topo = ttk.Frame(self.frame_catalogo, padding=8)
        topo.pack(fill="x")

        if filtro_tema:
            titulo_mapa = {"livros": "📚 Livros", "mangas": "📕 Mangás"}
            titulo = titulo_mapa.get(filtro_tema, filtro_tema.capitalize())

            tk.Button(topo, text="◄ Voltar ao Catálogo",
                      command=lambda: self._montar_grid_catalogo(None),
                      bg="#DCEBFA", fg="#003366",
                      relief="raised", padx=10, pady=2,
                      cursor="hand2").pack(side="left", padx=5)

            self._lbl_titulo_catalogo = ttk.Label(
                topo, text=titulo,
                font=("Segoe UI", 12, "bold"),
                foreground="#003366",
            )
            self._lbl_titulo_catalogo.pack(side="left", padx=15)
        else:
            self._lbl_titulo_catalogo = ttk.Label(
                topo, text="Catálogo de Obras",
                font=("Segoe UI", 12, "bold"),
                foreground="#003366",
            )
            self._lbl_titulo_catalogo.pack(side="left", padx=5)
            ttk.Label(topo, text="(explore por categoria)",
                      font=("Segoe UI", 9, "italic"),
                      foreground="#555555").pack(side="left", padx=6)

        self._atualizar_contador_downloads()

        if filtro_tema:
            self._montar_grid_filtrado(filtro_tema)
        else:
            self._montar_catalogo_secoes()

    def _atualizar_contador_downloads(self):
        if not hasattr(self, "_lbl_titulo_catalogo"):
            return
        n = len(self._downloads_ativos)
        if n == 0:
            self._lbl_titulo_catalogo.config(text="Catálogo de Obras")
        else:
            self._lbl_titulo_catalogo.config(
                text=f"Catálogo de Obras  —  {n} download(s) ativo(s)")

    # ==========================================================
    # CATÁLOGO — VIEW POR SEÇÕES
    # ==========================================================
    def _montar_catalogo_secoes(self):
        itens = self.repo_catalogo.listar()

        if not itens:
            ttk.Label(self.frame_catalogo,
                      text="O catálogo está vazio.",
                      justify="center", font=("Segoe UI", 10),
                      foreground="#555555").pack(pady=40, padx=30)
            return

        frame_scroll = ttk.Frame(self.frame_catalogo)
        frame_scroll.pack(expand=True, fill="both", padx=10, pady=5)

        canvas_v = tk.Canvas(frame_scroll, bg="#E9EEF4", highlightthickness=0)
        scroll_v = ttk.Scrollbar(frame_scroll, orient="vertical",
                                  command=canvas_v.yview)
        conteudo = ttk.Frame(canvas_v)

        conteudo.bind("<Configure>",
                      lambda e: canvas_v.configure(
                          scrollregion=canvas_v.bbox("all")))
        canvas_v.create_window((0, 0), window=conteudo, anchor="nw",
                                tags="catalogo_conteudo")
        canvas_v.configure(yscrollcommand=scroll_v.set)
        canvas_v.bind("<Configure>",
                      lambda e: canvas_v.itemconfigure(
                          "catalogo_conteudo", width=e.width))
        canvas_v.pack(side="left", expand=True, fill="both")
        scroll_v.pack(side="right", fill="y")

        por_tema: dict[str, list] = {}
        for item in itens:
            por_tema.setdefault(item.tema, []).append(item)

        if "livros" in por_tema:
            self._criar_secao_horizontal(
                conteudo, "📚 Livros", por_tema["livros"], "livros",
            )

        if "mangas" in por_tema:
            self._criar_secao_horizontal(
                conteudo, "📕 Mangás", por_tema["mangas"], "mangas",
            )

        for tema in sorted(set(por_tema) - {"livros", "mangas"}):
            self._criar_secao_horizontal(
                conteudo, tema.capitalize(), por_tema[tema], tema,
            )

    def _criar_secao_horizontal(self, parent, titulo: str, itens: list, tema: str):
        box = ttk.LabelFrame(parent, text=f" {titulo} ", padding=10)
        box.pack(fill="x", padx=10, pady=10)

        header = ttk.Frame(box)
        header.pack(fill="x", pady=(0, 8))

        ttk.Label(header, text=f"{len(itens)} obra(s) disponível(is)",
                  font=("Segoe UI", 9, "italic"),
                  foreground="#666666").pack(side="left", padx=4)

        tk.Button(header, text="Ver todos  →",
                  command=lambda t=tema: self._montar_grid_catalogo(t),
                  bg="#DCEBFA", fg="#003366",
                  relief="flat", bd=1, padx=12, pady=3,
                  cursor="hand2",
                  font=("Segoe UI", 9, "bold")).pack(side="right", padx=4)

        scroll_area = ttk.Frame(box)
        scroll_area.pack(fill="x")

        canvas = tk.Canvas(scroll_area, bg="#E9EEF4", height=300, highlightthickness=0)
        canvas._scroll_horizontal = True

        btn_left = tk.Button(scroll_area, text="◄", width=3,
                              command=lambda c=canvas: c.xview_scroll(-3, "units"),
                              bg="#DCEBFA", fg="#003366",
                              relief="flat",
                              font=("Segoe UI", 12, "bold"),
                              cursor="hand2")
        btn_left.pack(side="left", fill="y", padx=(0, 4))

        btn_right = tk.Button(scroll_area, text="►", width=3,
                               command=lambda c=canvas: c.xview_scroll(3, "units"),
                               bg="#DCEBFA", fg="#003366",
                               relief="flat",
                               font=("Segoe UI", 12, "bold"),
                               cursor="hand2")
        btn_right.pack(side="right", fill="y", padx=(4, 0))

        canvas.pack(side="left", fill="both", expand=True)

        inner = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=inner, anchor="nw", tags="inner")
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        for item in itens[:10]:
            self._criar_card_horizontal(inner, item)

    def _criar_card_horizontal(self, parent, item):
        card = ttk.Frame(parent, padding=8, relief="solid")
        card.pack(side="left", padx=8, pady=8)

        capa_frame = tk.Frame(card, bg="#D0E3F7", width=150, height=210)
        capa_frame.pack()
        capa_frame.pack_propagate(False)

        capa_label = tk.Label(capa_frame, text="📖", bg="#D0E3F7",
                               fg="#003366", font=("Segoe UI", 40),
                               cursor="hand2")
        capa_label.pack(expand=True, fill="both")
        capa_label.bind("<Button-1>", lambda e, it=item: self._abrir_detalhes(it))

        if item.capa_url:
            caminho_cache = self.capas.obter_cache(item.id)
            if caminho_cache:
                img = self._carregar_capa_ajustada(caminho_cache, 150, 210,
                                                    f"capa_{item.id}")
                if img:
                    capa_label.config(image=img, text="")
                    capa_label.image = img
            else:
                def _cb(caminho, lbl=capa_label, iid=item.id):
                    self.root.after(0, lambda: self._aplicar_capa(lbl, caminho, iid))
                self.capas.baixar_async(item.id, item.capa_url, _cb)

        nome_curto = item.nome if len(item.nome) <= 22 else item.nome[:20] + "…"
        nome_lbl = ttk.Label(card, text=nome_curto,
                              font=("Segoe UI", 9, "bold"),
                              wraplength=150, justify="center",
                              cursor="hand2")
        nome_lbl.pack(pady=(6, 2), fill="x")
        nome_lbl.bind("<Button-1>", lambda e, it=item: self._abrir_detalhes(it))

        if item.autor:
            autor_curto = item.autor if len(item.autor) <= 22 else item.autor[:20] + "…"
            ttk.Label(card, text=autor_curto,
                      font=("Segoe UI", 7, "italic"),
                      foreground="#666666",
                      wraplength=150, justify="center").pack(fill="x")

        ttk.Label(card, text=f"{len(item.volumes)} vol",
                  font=("Segoe UI", 8),
                  foreground="#888888").pack(pady=(2, 0))

    def _montar_grid_filtrado(self, filtro_tema: str):
        todos = self.repo_catalogo.listar()
        itens = [i for i in todos if i.tema == filtro_tema]

        if not itens:
            ttk.Label(self.frame_catalogo,
                      text="Nenhuma obra nesta categoria.",
                      font=("Segoe UI", 11, "italic"),
                      foreground="#888888").pack(pady=40)
            return

        frame_scroll = ttk.Frame(self.frame_catalogo, relief="ridge")
        frame_scroll.pack(expand=True, fill="both", padx=15, pady=5)

        canvas = tk.Canvas(frame_scroll, bg="#E9EEF4", highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame_scroll, orient="vertical",
                                    command=canvas.yview)
        conteudo = ttk.Frame(canvas)

        conteudo.bind("<Configure>",
                      lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=conteudo, anchor="nw",
                             tags="catalogo_conteudo")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure("catalogo_conteudo",
                                                     width=e.width))
        canvas.pack(side="left", expand=True, fill="both")
        scrollbar.pack(side="right", fill="y")

        grid = ttk.Frame(conteudo)
        grid.pack(expand=True, fill="both", pady=15, padx=15)

        colunas = 3
        for c in range(colunas):
            grid.grid_columnconfigure(c, weight=1, uniform="catalogo")

        self._cards_catalogo.clear()
        self._fav_frames.clear()

        for i, item in enumerate(itens):
            linha, coluna = divmod(i, colunas)

            card = ttk.Frame(grid, padding=12, relief="solid")
            card.grid(row=linha, column=coluna, padx=10, pady=10, sticky="nsew")

            capa_container = tk.Frame(card, bg="#D0E3F7", height=260)
            capa_container.pack(fill="x", pady=(0, 8))
            capa_container.pack_propagate(False)

            capa_label = tk.Label(capa_container, text="📖", bg="#D0E3F7",
                                   fg="#003366", font=("Segoe UI", 56),
                                   cursor="hand2")
            capa_label.pack(expand=True, fill="both")
            capa_label.bind("<Button-1>",
                            lambda e, it=item: self._abrir_detalhes(it))

            if item.capa_url:
                caminho_cache = self.capas.obter_cache(item.id)
                if caminho_cache:
                    img = self._carregar_capa_ajustada(caminho_cache, 180, 260,
                                                        f"capa_{item.id}")
                    if img:
                        capa_label.config(image=img, text="")
                        capa_label.image = img
                else:
                    def _cb(caminho, lbl=capa_label, iid=item.id):
                        self.root.after(0, lambda: self._aplicar_capa(lbl, caminho, iid))
                    self.capas.baixar_async(item.id, item.capa_url, _cb)

            nome_label = ttk.Label(card, text=item.nome,
                                    font=("Segoe UI", 10, "bold"),
                                    wraplength=180, justify="center",
                                    cursor="hand2")
            nome_label.pack(pady=(4, 2), fill="x")
            nome_label.bind("<Button-1>",
                            lambda e, it=item: self._abrir_detalhes(it))

            if item.autor:
                ttk.Label(card, text=f"por {item.autor}",
                          font=("Segoe UI", 8, "italic"),
                          foreground="#666666",
                          wraplength=180, justify="center").pack(fill="x")

            qtd_vol = len(item.volumes)
            total_mb = sum(v.tamanho_mb for v in item.volumes)

            media, n_reviews = self.repo_reviews.media_da_obra(item.nome, item.id)
            if n_reviews > 0:
                estrelas = self._formatar_estrelas(media)
                texto_meta = (f"{qtd_vol} vol • {total_mb:.1f} MB • "
                              f"{estrelas} {media:.1f} ({n_reviews})")
            else:
                texto_meta = f"{qtd_vol} vol • {total_mb:.1f} MB"

            ttk.Label(card, text=texto_meta,
                      font=("Segoe UI", 8),
                      foreground="#555555").pack(pady=(6, 8))

            area_fav = ttk.Frame(card)
            area_fav.pack(fill="x", pady=(0, 6))
            self._fav_frames[item.id] = area_fav

            area_acao = ttk.Frame(card)
            area_acao.pack(fill="x")

            self._cards_catalogo[item.id] = {
                "item": item,
                "area_acao": area_acao,
            }

            self._atualizar_botao_favorito(item.id)

            if item.tema == "mangas":
                self._mostrar_estado_manga(item.id)
            else:
                ja_local = self._obra_tem_pdfs_local(item.nome)
                if ja_local:
                    self._mostrar_estado_baixado(item.id)
                else:
                    self._mostrar_estado_disponivel(item.id)

    # ==========================================================
    # DOWNLOADS
    # ==========================================================
    def _mostrar_estado_disponivel(self, item_id: str):
        ref = self._cards_catalogo.get(item_id)
        if ref is None:
            return
        area = ref["area_acao"]
        for w in area.winfo_children():
            w.destroy()
        item = ref["item"]
        tk.Button(area, text="⬇ Baixar",
                  command=lambda: self._baixar_item_catalogo(item),
                  bg="#003366", fg="white",
                  relief="raised", padx=10, pady=4).pack(fill="x")

    def _mostrar_estado_manga(self, item_id: str):
        ref = self._cards_catalogo.get(item_id)
        if ref is None:
            return
        area = ref["area_acao"]
        for w in area.winfo_children():
            w.destroy()
        item = ref["item"]

        n_baixados = self._contar_volumes_baixados(item)
        n_total = len(item.volumes)

        if n_baixados > 0:
            ttk.Label(area, text=f"📚 {n_baixados}/{n_total} baixados",
                      font=("Segoe UI", 8, "bold"),
                      foreground="#008000").pack()
        else:
            ttk.Label(area, text="📚 Mangá",
                      font=("Segoe UI", 8, "italic"),
                      foreground="#6A1B9A").pack()

        texto_btn = "🔓 Ver Volumes" if not self._mangas_desbloqueados else "📚 Ver Volumes"
        tk.Button(area, text=texto_btn,
                  command=lambda: self._baixar_item_catalogo(item),
                  bg="#6A1B9A", fg="white",
                  relief="raised", padx=10, pady=4).pack(fill="x", pady=(4, 0))

    def _mostrar_estado_baixando(self, item_id: str):
        ref = self._cards_catalogo.get(item_id)
        if ref is None:
            return
        area = ref["area_acao"]
        for w in area.winfo_children():
            w.destroy()

        lbl = ttk.Label(area, text="Baixando...", font=("Segoe UI", 8))
        lbl.pack()
        prog = ttk.Progressbar(area, mode="determinate", maximum=100, length=170)
        prog.pack(fill="x", pady=(2, 4))

        tk.Button(area, text="✖ Cancelar",
                  bg="#F0F4F8", fg="#C2185B",
                  relief="flat", bd=1, padx=6, pady=1,
                  cursor="hand2",
                  command=lambda: self._cancelar_download_item(item_id),
                  ).pack(fill="x")

        ref["label_progresso"] = lbl
        ref["progressbar"] = prog

    def _mostrar_estado_baixado(self, item_id: str):
        ref = self._cards_catalogo.get(item_id)
        if ref is None:
            return
        area = ref["area_acao"]
        for w in area.winfo_children():
            w.destroy()

        item = ref["item"]
        ttk.Label(area, text="✔ Já na biblioteca",
                  font=("Segoe UI", 9, "bold"),
                  foreground="#008000").pack()
        tk.Button(area, text="Abrir",
                  command=lambda n=item.nome: self.mostrar_tela_volumes(n)
                  ).pack(pady=4, fill="x")

        if (self._detalhes_item_atual is not None
                and self._detalhes_item_atual.id == item_id
                and self.frame_detalhes_obra.winfo_ismapped()):
            self._montar_detalhes_obra(self._detalhes_item_atual)

    def _baixar_item_catalogo(self, item: CatalogoItem):
        if not item.volumes:
            messagebox.showwarning("Catálogo",
                                    f"'{item.nome}' não tem volumes para baixar.")
            return

        if item.tema == "mangas":
            if not self._verificar_desbloqueio_manga():
                return
            self._abrir_tela_volumes_manga(item)
            return

        self._downloads_cancelados.discard(item.id)
        self._mostrar_estado_baixando(item.id)
        self._baixar_proximo_volume(item, 0)

    def _cancelar_download_item(self, item_id: str):
        self._downloads_cancelados.add(item_id)
        chave_atual = self._downloads_ativos.get(item_id)
        if chave_atual:
            self.gerenciador.cancelar(chave_atual)
        else:
            self._downloads_cancelados.discard(item_id)
            self._downloads_ativos.pop(item_id, None)
            self._mostrar_estado_disponivel(item_id)
            self._atualizar_contador_downloads()

    def _baixar_proximo_volume(self, item: CatalogoItem, indice: int):
        if item.id in self._downloads_cancelados:
            self._downloads_cancelados.discard(item.id)
            self._downloads_ativos.pop(item.id, None)
            self._mostrar_estado_disponivel(item.id)
            self._atualizar_contador_downloads()
            return

        if indice >= len(item.volumes):
            self._downloads_ativos.pop(item.id, None)
            self._mostrar_estado_baixado(item.id)
            self._atualizar_contador_downloads()
            self._notificar(
                titulo="Download concluído",
                mensagem=f"'{item.nome}' está pronto para ler!",
                icone="📚",
                tipo="download",
                dado={"nome": item.nome},
                som="download",
            )
            return

        volume = item.volumes[indice]
        chave = f"{item.id}:vol{volume.numero}"
        destino = os.path.join(self.pasta_pdf, item.nome, f"{volume.titulo}.pdf")

        if os.path.exists(destino):
            resposta = messagebox.askyesnocancel(
                "Arquivo já existe",
                f"'{volume.titulo}.pdf' já existe em '{item.nome}'.\n\n"
                f"• Sim → Substituir\n"
                f"• Não → Pular este volume\n"
                f"• Cancelar → Abortar a série",
                parent=self.root,
            )
            if resposta is None:
                self._downloads_cancelados.discard(item.id)
                self._downloads_ativos.pop(item.id, None)
                self._mostrar_estado_disponivel(item.id)
                self._atualizar_contador_downloads()
                return
            if resposta is False:
                self._baixar_proximo_volume(item, indice + 1)
                return

        self._downloads_ativos[item.id] = chave
        self._atualizar_contador_downloads()

        total_volumes = len(item.volumes)

        def on_progresso(baixado: int, total: int) -> None:
            ref = self._cards_catalogo.get(item.id)
            if ref is None:
                return
            prog = ref.get("progressbar")
            lbl = ref.get("label_progresso")
            if total > 0:
                pct = int(baixado * 100 / total)
                if prog is not None:
                    prog["value"] = pct
                if lbl is not None:
                    mb_b = baixado / (1024 * 1024)
                    mb_t = total / (1024 * 1024)
                    lbl.config(text=f"Vol. {volume.numero}/{total_volumes}  •  "
                                    f"{pct}%  •  {mb_b:.1f}/{mb_t:.1f} MB")
            else:
                if lbl is not None:
                    lbl.config(text=f"Vol. {volume.numero}/{total_volumes}  —  "
                                    f"{baixado // 1024} KB")

        def on_concluido() -> None:
            self._baixar_proximo_volume(item, indice + 1)

        def on_erro(mensagem: str) -> None:
            self._downloads_ativos.pop(item.id, None)
            self._downloads_cancelados.discard(item.id)
            messagebox.showerror(
                "Erro no download",
                f"Falha ao baixar '{volume.titulo}':\n\n{mensagem}",
            )
            self._mostrar_estado_disponivel(item.id)
            self._atualizar_contador_downloads()

        def on_cancelado() -> None:
            self._downloads_ativos.pop(item.id, None)
            self._baixar_proximo_volume(item, indice + 1)

        self.gerenciador.baixar(
            chave=chave, url=volume.url, destino=destino,
            callbacks=Callbacks(
                on_progresso=on_progresso, on_concluido=on_concluido,
                on_erro=on_erro, on_cancelado=on_cancelado,
            ),
        )

    # ==========================================================
    # MANGÁS — CÓDIGO + TELA DE VOLUMES
    # ==========================================================
    def _verificar_desbloqueio_manga(self) -> bool:
        if self._mangas_desbloqueados:
            return True

        codigo_esperado = self.repo_catalogo.codigo_acesso_mangas()
        if not codigo_esperado:
            self._mangas_desbloqueados = True
            return True

        codigo = simpledialog.askstring(
            "🔒 Código de acesso — Mangás",
            "Os mangás são protegidos por um código de acesso.\n\n"
            "Digite o código para desbloquear (fica liberado durante "
            "esta sessão do app):",
            show="*",
            parent=self.root,
        )
        if codigo is None:
            return False

        if codigo.strip() != codigo_esperado:
            messagebox.showerror(
                "Código incorreto",
                "❌ Código de acesso inválido.\n\n"
                "Os mangás permanecem bloqueados.",
                parent=self.root,
            )
            return False

        self._mangas_desbloqueados = True
        self._notificar(
            titulo="Mangás desbloqueados!",
            mensagem="Você pode baixar volumes durante esta sessão.",
            icone="🔓",
            tipo="geral",
            som="notificacao",
        )
        if self.frame_catalogo.winfo_ismapped():
            self._montar_grid_catalogo()
        return True

    def _abrir_tela_volumes_manga(self, item: CatalogoItem):
        self._manga_selecionado = item
        self._esconder_todas(self.frame_volumes_manga)
        self.frame_volumes_manga.pack(expand=True, fill="both")
        self._montar_tela_volumes_manga(item)

    def _montar_tela_volumes_manga(self, item: CatalogoItem):
        for w in self.frame_volumes_manga.winfo_children():
            w.destroy()
        self._volumes_ui.clear()

        topo = tk.Frame(self.frame_volumes_manga, bg="#6A1B9A", height=70)
        topo.pack(fill="x")
        topo.pack_propagate(False)

        tk.Button(topo, text="◄ Voltar ao Catálogo",
                  command=self.abrir_tela_catalogo,
                  bg="#DCEBFA", fg="#4A148C",
                  relief="raised").pack(side="left", padx=15, pady=15)

        tk.Label(topo, text=f"📚 {item.nome}",
                 font=("Segoe UI", 15, "bold"),
                 fg="white", bg="#6A1B9A").pack(side="left", padx=10)

        n_baixados = self._contar_volumes_baixados(item)
        tk.Label(topo, text=f"{n_baixados}/{len(item.volumes)} baixados",
                 font=("Segoe UI", 9, "italic"),
                 fg="#E1BEE7", bg="#6A1B9A").pack(side="left", padx=6)

        tk.Button(topo, text="⬇ Baixar Todos os Pendentes",
                  command=lambda: self._baixar_todos_manga(item),
                  bg="#DCEBFA", fg="#4A148C",
                  relief="raised").pack(side="right", padx=15, pady=15)

        info_box = ttk.LabelFrame(self.frame_volumes_manga,
                                    text=" Sobre o mangá ", padding=10)
        info_box.pack(fill="x", padx=15, pady=(10, 4))

        ttk.Label(info_box, text=f"por {item.autor} • {item.categoria} • {item.ano}",
                  font=("Segoe UI", 9, "italic"),
                  foreground="#555555").pack(anchor="w")
        ttk.Label(info_box, text=item.descricao, wraplength=950,
                  justify="left").pack(anchor="w", pady=(4, 0))

        frame_scroll = ttk.Frame(self.frame_volumes_manga, relief="ridge")
        frame_scroll.pack(expand=True, fill="both", padx=15, pady=8)

        canvas = tk.Canvas(frame_scroll, bg="#E9EEF4", highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame_scroll, orient="vertical", command=canvas.yview)
        conteudo = ttk.Frame(canvas)
        conteudo.bind("<Configure>",
                      lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=conteudo, anchor="nw",
                             tags="vols_manga_conteudo")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure("vols_manga_conteudo", width=e.width))
        canvas.pack(side="left", expand=True, fill="both")
        scrollbar.pack(side="right", fill="y")

        for vol in item.volumes:
            self._render_item_volume(conteudo, item, vol)

    def _render_item_volume(self, parent, item: CatalogoItem, vol):
        linha = ttk.Frame(parent, padding=10, relief="groove")
        linha.pack(fill="x", padx=10, pady=4)

        info = ttk.Frame(linha)
        info.pack(side="left", fill="x", expand=True)

        ttk.Label(info, text=f"Vol. {vol.numero:02d} — {vol.titulo}",
                  font=("Segoe UI", 10, "bold"),
                  foreground="#003366").pack(anchor="w")

        meta = f"{vol.tamanho_mb:.1f} MB"
        if vol.fonte:
            meta += f" • {vol.fonte}"
        ttk.Label(info, text=meta,
                  font=("Segoe UI", 8),
                  foreground="#666666").pack(anchor="w", pady=(2, 0))

        area_acao = ttk.Frame(linha)
        area_acao.pack(side="right")

        chave = f"{item.id}:vol{vol.numero}"
        self._volumes_ui[chave] = {
            "item": item,
            "vol": vol,
            "linha": linha,
            "area_acao": area_acao,
        }
        self._atualizar_volume_ui(chave)

    def _atualizar_volume_ui(self, chave: str):
        ref = self._volumes_ui.get(chave)
        if ref is None:
            return
        item = ref["item"]
        vol = ref["vol"]
        area = ref["area_acao"]

        for w in area.winfo_children():
            w.destroy()
        ref.pop("progressbar", None)
        ref.pop("label_pct", None)

        caminho = os.path.join(self.pasta_pdf, item.nome, f"{vol.titulo}.pdf")

        if self.gerenciador.esta_ativo(chave):
            prog = ttk.Progressbar(area, mode="determinate", maximum=100, length=120)
            prog.pack(side="left", padx=4)
            lbl = ttk.Label(area, text="0%", font=("Segoe UI", 8), width=4)
            lbl.pack(side="left")
            tk.Button(area, text="✖",
                      command=lambda c=chave: self.gerenciador.cancelar(c),
                      bg="#F0F4F8", fg="#C2185B",
                      relief="flat", bd=1, padx=6).pack(side="left", padx=4)
            ref["progressbar"] = prog
            ref["label_pct"] = lbl
            return

        if os.path.exists(caminho):
            ttk.Label(area, text="✔ Baixado",
                      font=("Segoe UI", 9, "bold"),
                      foreground="#008000").pack(side="left", padx=6)
            tk.Button(area, text="Abrir",
                      command=lambda p=caminho: self.abrir_manga_da_biblioteca(p),
                      bg="#003366", fg="white", relief="raised",
                      padx=10, pady=3).pack(side="left")
            return

        tk.Button(area, text="⬇ Baixar",
                  command=lambda: self._baixar_volume_manga(item, vol),
                  bg="#003366", fg="white", relief="raised",
                  padx=10, pady=3).pack(side="left")

    def _baixar_volume_manga(self, item: CatalogoItem, vol, on_fim=None):
        chave = f"{item.id}:vol{vol.numero}"

        if self.gerenciador.esta_ativo(chave):
            return

        destino = os.path.join(self.pasta_pdf, item.nome, f"{vol.titulo}.pdf")

        if os.path.exists(destino):
            if not messagebox.askyesno(
                "Arquivo existe",
                f"'{vol.titulo}.pdf' já existe. Substituir?",
            ):
                if on_fim:
                    self.root.after(0, on_fim)
                return

        self._atualizar_volume_ui(chave)

        def on_progresso(baixado: int, total: int) -> None:
            ref = self._volumes_ui.get(chave)
            if ref is None:
                return
            prog = ref.get("progressbar")
            lbl = ref.get("label_pct")
            if total > 0 and prog is not None and lbl is not None:
                pct = int(baixado * 100 / total)
                try:
                    prog["value"] = pct
                    lbl.config(text=f"{pct}%")
                except tk.TclError:
                    pass

        def on_concluido() -> None:
            self._atualizar_volume_ui(chave)
            self._notificar(
                titulo="Volume baixado",
                mensagem=f"{item.nome} — Vol. {vol.numero:02d}",
                icone="📚",
                tipo="geral",
                som="download",
            )
            if on_fim:
                self.root.after(100, on_fim)

        def on_erro(msg: str) -> None:
            self._atualizar_volume_ui(chave)
            messagebox.showerror(
                "Erro no download",
                f"Falha ao baixar '{vol.titulo}':\n\n{msg}",
            )
            if on_fim:
                self.root.after(100, on_fim)

        def on_cancelado() -> None:
            self._atualizar_volume_ui(chave)
            if on_fim:
                self.root.after(100, on_fim)

        self.gerenciador.baixar(
            chave=chave, url=vol.url, destino=destino,
            callbacks=Callbacks(
                on_progresso=on_progresso,
                on_concluido=on_concluido,
                on_erro=on_erro,
                on_cancelado=on_cancelado,
            ),
        )
        self._atualizar_volume_ui(chave)

    def _baixar_todos_manga(self, item: CatalogoItem):
        pendentes = []
        for vol in item.volumes:
            chave = f"{item.id}:vol{vol.numero}"
            if self.gerenciador.esta_ativo(chave):
                continue
            caminho = os.path.join(self.pasta_pdf, item.nome, f"{vol.titulo}.pdf")
            if os.path.exists(caminho):
                continue
            pendentes.append(vol)

        if not pendentes:
            messagebox.showinfo("Tudo em dia",
                                 "Todos os volumes já estão baixados ou em download.")
            return

        total_mb = sum(v.tamanho_mb for v in pendentes)
        if not messagebox.askyesno(
            "Baixar todos os pendentes",
            f"Baixar {len(pendentes)} volume(s) de '{item.nome}'?\n\n"
            f"Tamanho estimado: ~{total_mb:.0f} MB"
        ):
            return

        self._fila_download_manga = list(pendentes)
        self._processar_fila_manga(item)

    def _processar_fila_manga(self, item: CatalogoItem):
        if not self._fila_download_manga:
            self._notificar(
                titulo="Download em lote concluído",
                mensagem=f"'{item.nome}' está completo!",
                icone="📚",
                tipo="geral",
                som="download",
            )
            if (self._manga_selecionado
                    and self._manga_selecionado.id == item.id):
                self._montar_tela_volumes_manga(item)
            return

        vol = self._fila_download_manga.pop(0)
        self._baixar_volume_manga(
            item, vol,
            on_fim=lambda: self._processar_fila_manga(item),
        )

    # ==========================================================
    # FAVORITOS
    # ==========================================================
    def _atualizar_botao_favorito(self, item_id: str) -> None:
        area = self._fav_frames.get(item_id)
        if area is None:
            return
        for w in area.winfo_children():
            w.destroy()

        perfil = self.repo_perfis.ativo()
        if perfil is None:
            return

        favoritado = self.repo_perfis.eh_favorito(perfil.id, item_id)

        if favoritado:
            texto, bg, fg = "♥  Favorito", "#FFE5EC", "#C2185B"
        else:
            texto, bg, fg = "♡  Favoritar", "#F0F4F8", "#555555"

        tk.Button(area, text=texto, bg=bg, fg=fg,
                  relief="flat", bd=1, padx=6, pady=2, cursor="hand2",
                  command=lambda: self._alternar_favorito_catalogo(item_id),
                  ).pack(fill="x")

    def _alternar_favorito_catalogo(self, item_id: str) -> None:
        perfil = self.repo_perfis.ativo()
        if perfil is None:
            return
        sucesso, mensagem = self.repo_perfis.alternar_favorito(perfil.id, item_id)
        if not sucesso:
            messagebox.showinfo("Favoritos", mensagem)
            return
        self._atualizar_botao_favorito(item_id)
        if self.frame_perfil.winfo_ismapped():
            self._montar_conteudo_perfil(alvo_nome=self._perfil_alvo_nome)
        if (self._detalhes_item_atual is not None
                and self._detalhes_item_atual.id == item_id
                and self.frame_detalhes_obra.winfo_ismapped()):
            self._montar_detalhes_obra(self._detalhes_item_atual)

    def abrir_dialogo_favoritos(self) -> None:
        perfil = self.repo_perfis.ativo()
        if perfil is None:
            return

        itens = self.repo_catalogo.listar()
        if not itens:
            messagebox.showinfo("Catálogo vazio",
                                "Não há obras no catálogo para escolher como favoritas.")
            return

        janela = tk.Toplevel(self.root)
        janela.title("Escolher Favoritos")
        janela.geometry("620x560")
        janela.configure(bg="#F0F4F8")
        janela.transient(self.root)
        janela.grab_set()

        corpo = ttk.Frame(janela, padding=18)
        corpo.pack(fill="both", expand=True)

        ttk.Label(corpo, text="Escolha até 5 obras favoritas",
                  font=("Segoe UI", 15, "bold"),
                  foreground="#003366").pack(anchor="w")

        lbl_contador = ttk.Label(corpo, text="", font=("Segoe UI", 9, "italic"),
                                  foreground="#555555")
        lbl_contador.pack(anchor="w", pady=(2, 12))

        frame_lista = ttk.Frame(corpo, relief="sunken", borderwidth=1)
        frame_lista.pack(fill="both", expand=True)

        canvas = tk.Canvas(frame_lista, bg="#FFFFFF", highlightthickness=0)
        scroll = ttk.Scrollbar(frame_lista, orient="vertical", command=canvas.yview)
        interior = ttk.Frame(canvas)
        interior.bind("<Configure>",
                      lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=interior, anchor="nw", width=560)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        selecionados: dict[str, tk.BooleanVar] = {}

        def atualizar_contador():
            n = sum(1 for v in selecionados.values() if v.get())
            lbl_contador.config(
                text=f"{n}/{self.repo_perfis.LIMITE_FAVORITOS} selecionados")

        def ao_alternar(item_id: str):
            n = sum(1 for v in selecionados.values() if v.get())
            if n > self.repo_perfis.LIMITE_FAVORITOS:
                selecionados[item_id].set(False)
                messagebox.showinfo(
                    "Limite atingido",
                    f"Você só pode escolher {self.repo_perfis.LIMITE_FAVORITOS} "
                    f"favoritos. Desmarque um antes.",
                    parent=janela)
            atualizar_contador()

        favoritos_atuais = set(perfil.favoritos)

        for item in itens:
            var = tk.BooleanVar(value=item.id in favoritos_atuais)
            selecionados[item.id] = var

            linha = ttk.Frame(interior, padding=8)
            linha.pack(fill="x", padx=4, pady=2)

            tk.Checkbutton(linha, variable=var,
                           command=lambda iid=item.id: ao_alternar(iid),
                           bg="#FFFFFF", activebackground="#FFFFFF").pack(side="left")

            texto = item.nome + (f"  —  {item.autor}" if item.autor else "")
            ttk.Label(linha, text=texto, font=("Segoe UI", 10),
                      background="#FFFFFF").pack(side="left", padx=6)
            ttk.Label(linha, text=f"({len(item.volumes)} vol)",
                      font=("Segoe UI", 8, "italic"),
                      foreground="#888888",
                      background="#FFFFFF").pack(side="right")

        atualizar_contador()

        botoes = ttk.Frame(corpo)
        botoes.pack(fill="x", pady=(12, 0))

        def salvar():
            ids_escolhidos = [iid for iid, v in selecionados.items() if v.get()]

            # 1) Salva local
            self.repo_perfis.definir_favoritos(perfil.id, ids_escolhidos)

            # 2) Envia pra API (usa o endpoint que já existe no perfis_api.py)
            if self.modo == "api" and self.sessao is not None:
                try:
                    from perfis_api import RepositorioPerfisAPI
                    api = RepositorioPerfisAPI(
                        os.environ.get("SOPHIA_API_URL",
                                        "https://sophia-api-lzwc.onrender.com"),
                        token=self.sessao.token,
                    )
                    resultado = api.definir_favoritos(perfil.nome, ids_escolhidos)
                    print(f"[favoritos-sync] enviados {len(ids_escolhidos)}, "
                          f"servidor confirmou {len(resultado)}")
                except Exception as e:
                    print(f"[favoritos-sync] ERRO: {e}")
                    messagebox.showwarning(
                        "Aviso",
                        f"Favoritos salvos local, mas falhou enviar ao servidor:\n{e}"
                    )

            janela.destroy()
            if self.frame_catalogo.winfo_ismapped():
                for iid in self._fav_frames:
                    self._atualizar_botao_favorito(iid)
            if self.frame_perfil.winfo_ismapped():
                self._montar_conteudo_perfil(alvo_nome=self._perfil_alvo_nome)

        ttk.Button(botoes, text="Cancelar",
                   command=janela.destroy).pack(side="right", padx=5)
        ttk.Button(botoes, text="Salvar Favoritos",
                   command=salvar).pack(side="right")

    # ==========================================================
    # DETALHES DA OBRA — COM CAPA DINÂMICA
    # ==========================================================
    def _abrir_detalhes(self, item: CatalogoItem, origem: str = "catalogo"):
        self._detalhes_item_atual = item
        self._detalhes_origem = origem
        self._esconder_todas(self.frame_detalhes_obra)
        self.frame_detalhes_obra.pack(expand=True, fill="both")
        self._montar_detalhes_obra(item)

    def _voltar_dos_detalhes(self):
        if self._detalhes_origem == "biblioteca":
            self.mostrar_tela_obras()
        else:
            self.abrir_tela_catalogo()

    def _formatar_estrelas(self, media: float) -> str:
        cheias = int(round(media))
        cheias = max(0, min(5, cheias))
        return "★" * cheias + "☆" * (5 - cheias)

    def _montar_detalhes_obra(self, item: CatalogoItem):
        for w in self.frame_detalhes_obra.winfo_children():
            w.destroy()

        topo = ttk.Frame(self.frame_detalhes_obra, padding=8)
        topo.pack(fill="x")
        ttk.Button(topo, text="◄ Voltar",
                   command=self._voltar_dos_detalhes).pack(side="left", padx=5)
        ttk.Label(topo, text=f"Detalhes: {item.nome}",
                  font=("Segoe UI", 11, "bold"),
                  foreground="#003366").pack(side="left", padx=15)

        frame_scroll = ttk.Frame(self.frame_detalhes_obra)
        frame_scroll.pack(expand=True, fill="both", padx=15, pady=5)

        canvas = tk.Canvas(frame_scroll, bg="#F0F4F8", highlightthickness=0)
        scroll = ttk.Scrollbar(frame_scroll, orient="vertical", command=canvas.yview)
        conteudo = ttk.Frame(canvas)
        conteudo.bind("<Configure>",
                      lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=conteudo, anchor="nw",
                             width=910, tags="det_conteudo")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure("det_conteudo", width=e.width))

        cab = ttk.Frame(conteudo, relief="solid", padding=15)
        cab.pack(fill="x", padx=10, pady=10)

        # ---------- CAPA DINÂMICA ----------
        capa_frame = tk.Frame(cab, bg="#D0E3F7", width=200, height=280)
        capa_frame.pack(side="left", padx=(0, 18))
        capa_frame.pack_propagate(False)

        capa_lbl = tk.Label(capa_frame, text="📖", bg="#D0E3F7",
                            fg="#003366", font=("Segoe UI", 56))
        capa_lbl.pack(expand=True, fill="both")

        # Tenta 1) capa local do PDF; 2) cache remoto; 3) dispara download
        carregou = False

        if self._obra_tem_pdfs_local(item.nome):
            caminho_local = os.path.join(self.pasta_pdf, item.nome)
            try:
                arquivos = [f for f in os.listdir(caminho_local)
                            if f.lower().endswith(".pdf")]
                if arquivos:
                    img = self.gerar_capa_miniatura(
                        os.path.join(caminho_local, sorted(arquivos)[0]))
                    if img:
                        capa_lbl.config(image=img, text="")
                        capa_lbl.image = img
                        carregou = True
            except OSError:
                pass

        if not carregou and item.capa_url:
            caminho_cache = self.capas.obter_cache(item.id)
            if caminho_cache:
                img = self._carregar_capa_ajustada(caminho_cache, 200, 280,
                                                    f"capa_det_{item.id}")
                if img:
                    capa_lbl.config(image=img, text="")
                    capa_lbl.image = img
                    carregou = True
            else:
                def _cb(caminho, lbl=capa_lbl, iid=item.id):
                    self.root.after(0, lambda: self._aplicar_capa_detalhe(
                        lbl, caminho, iid))
                self.capas.baixar_async(item.id, item.capa_url, _cb)

        # ---------- INFO ----------
        info = ttk.Frame(cab)
        info.pack(side="left", fill="both", expand=True)

        ttk.Label(info, text=item.nome,
                  font=("Segoe UI", 20, "bold")).pack(anchor="w")
        if item.autor:
            ttk.Label(info, text=f"por {item.autor}",
                      font=("Segoe UI", 10, "italic"),
                      foreground="#666666").pack(anchor="w", pady=(2, 8))
        if item.descricao:
            ttk.Label(info, text=item.descricao, wraplength=520,
                      justify="left").pack(anchor="w", pady=(0, 10))

        media, n_reviews = self.repo_reviews.media_da_obra(item.nome, item.id)
        if n_reviews > 0:
            estrelas = self._formatar_estrelas(media)
            linha_nota = ttk.Frame(info)
            linha_nota.pack(anchor="w", pady=(0, 10))
            ttk.Label(linha_nota, text=estrelas,
                      font=("Segoe UI", 14, "bold"),
                      foreground="#B77900").pack(side="left")
            ttk.Label(linha_nota, text=f"  {media:.1f}/5  •  {n_reviews} review(s)",
                      font=("Segoe UI", 10),
                      foreground="#555555").pack(side="left")
        else:
            ttk.Label(info, text="Sem avaliações ainda",
                      font=("Segoe UI", 9, "italic"),
                      foreground="#999999").pack(anchor="w", pady=(0, 10))

        qtd_vol = len(item.volumes)
        total_mb = sum(v.tamanho_mb for v in item.volumes)
        ttk.Label(info, text=f"{qtd_vol} volume(s) • {total_mb:.1f} MB total",
                  font=("Segoe UI", 9),
                  foreground="#555555").pack(anchor="w")

        botoes = ttk.Frame(info)
        botoes.pack(anchor="w", pady=(12, 0))

        perfil = self.repo_perfis.ativo()
        ja_local = self._obra_tem_pdfs_local(item.nome)
        favoritado = perfil is not None and self.repo_perfis.eh_favorito(perfil.id, item.id)

        txt_fav = "♥  Favorito" if favoritado else "♡  Favoritar"
        bg_fav = "#FFE5EC" if favoritado else "#F0F4F8"
        fg_fav = "#C2185B" if favoritado else "#555555"
        tk.Button(botoes, text=txt_fav, bg=bg_fav, fg=fg_fav,
                  relief="flat", bd=1, padx=10, pady=4, cursor="hand2",
                  command=lambda: self._alternar_favorito_detalhes(item)
                  ).pack(side="left", padx=(0, 6))

        if item.tema == "mangas":
            tk.Button(botoes, text="📚 Ver Volumes", bg="#6A1B9A", fg="white",
                      relief="raised", padx=12, pady=4,
                      command=lambda it=item: self._baixar_item_catalogo(it)
                      ).pack(side="left", padx=(0, 6))
        elif ja_local:
            tk.Button(botoes, text="📖 Ler", bg="#003366", fg="white",
                      relief="raised", padx=12, pady=4,
                      command=lambda n=item.nome: self.mostrar_tela_volumes(n)
                      ).pack(side="left", padx=(0, 6))
        else:
            tk.Button(botoes, text="⬇ Baixar", bg="#003366", fg="white",
                      relief="raised", padx=12, pady=4,
                      command=lambda: self._baixar_dos_detalhes(item)
                      ).pack(side="left", padx=(0, 6))

        ttk.Button(botoes, text="📝 Escrever Review",
                   command=lambda: self.formulario_review(
                       obra_nome=item.nome, obra_id=item.id)
                   ).pack(side="left")

        # ---------- REVIEWS ----------
        frame_reviews = ttk.LabelFrame(conteudo, text=" 💬 Reviews da Obra ",
                                        padding=10)
        frame_reviews.pack(fill="x", padx=10, pady=(0, 10))

        reviews = self.repo_reviews.listar_por_obra(item.nome, item.id)
        if not reviews:
            ttk.Label(frame_reviews,
                      text="Nenhuma review publicada ainda.",
                      justify="center", font=("Segoe UI", 10),
                      foreground="#777777").pack(pady=25, padx=20)
            return

        reviews.sort(key=lambda r: r.data, reverse=True)
        for review in reviews:
            card = ttk.Frame(frame_reviews, relief="groove", padding=10)
            card.pack(fill="x", pady=5)

            estrelas = "★" * review.nota + "☆" * (5 - review.nota)
            ttk.Label(card, text=f"{estrelas}   {review.nota}/5",
                      font=("Segoe UI", 11, "bold"),
                      foreground="#B77900").pack(anchor="w")
            ttk.Label(card, text=f"Por {review.perfil}  •  {review.data}",
                      foreground="#555555").pack(anchor="w", pady=(2, 6))
            ttk.Label(card, text=review.texto, wraplength=820,
                      justify="left").pack(anchor="w", fill="x")

    def _alternar_favorito_detalhes(self, item: CatalogoItem):
        perfil = self.repo_perfis.ativo()
        if perfil is None:
            return
        sucesso, mensagem = self.repo_perfis.alternar_favorito(perfil.id, item.id)
        if not sucesso:
            messagebox.showinfo("Favoritos", mensagem)
            return
        if item.id in self._fav_frames:
            self._atualizar_botao_favorito(item.id)
        self._montar_detalhes_obra(item)

    def _baixar_dos_detalhes(self, item: CatalogoItem):
        if not item.volumes:
            messagebox.showwarning("Catálogo",
                                    f"'{item.nome}' não tem volumes para baixar.")
            return
        self._esconder_todas(self.frame_catalogo)
        self.frame_catalogo.pack(expand=True, fill="both")
        self._montar_grid_catalogo()
        self._baixar_item_catalogo(item)
        self._esconder_todas(self.frame_detalhes_obra)
        self.frame_detalhes_obra.pack(expand=True, fill="both")

    # ==========================================================
    # OBRAS (BIBLIOTECA)
    # ==========================================================
    def _montar_grid_obras(self):
        for w in self.frame_obras.winfo_children():
            w.destroy()

        ttk.Label(self.frame_obras, text="Biblioteca de Obras",
                  font=("Segoe UI", 12, "bold"),
                  foreground="#003366").pack(anchor="w", padx=15, pady=10)

        frame_scroll = ttk.Frame(self.frame_obras, relief="ridge")
        frame_scroll.pack(expand=True, fill="both", padx=15, pady=5)

        canvas = tk.Canvas(frame_scroll, bg="#E9EEF4", highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame_scroll, orient="vertical", command=canvas.yview)
        conteudo = ttk.Frame(canvas)
        conteudo.bind("<Configure>",
                      lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=conteudo, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", expand=True, fill="both")
        scrollbar.pack(side="right", fill="y")

        self.capas_memoria.clear()

        pasta_raiz = os.path.join(_pasta_dados(), "pdf_padrao")
        if not os.path.isdir(pasta_raiz):
            ttk.Label(conteudo, text="A pasta 'pdf_padrao' não foi encontrada.").pack(
                padx=20, pady=20)
            return

        try:
            obras = [d for d in os.listdir(pasta_raiz)
                     if os.path.isdir(os.path.join(pasta_raiz, d))]
        except OSError:
            obras = []

        if not obras:
            ttk.Label(conteudo, text="Nenhuma obra encontrada.").pack(padx=20, pady=20)
            return

        colunas = 4
        i = 0
        for obra in obras:
            caminho_obra = os.path.join(pasta_raiz, obra)
            try:
                volumes = [f for f in os.listdir(caminho_obra)
                           if f.lower().endswith(".pdf")]
            except OSError:
                continue
            if not volumes:
                continue

            tk_capa = self.gerar_capa_miniatura(os.path.join(caminho_obra, volumes[0]))
            linha, coluna = divmod(i, colunas)

            card = ttk.Frame(conteudo, padding=10, relief="solid")
            card.grid(row=linha, column=coluna, padx=15, pady=15)

            if tk_capa:
                tk.Button(card, image=tk_capa,
                          command=lambda o=obra: self.mostrar_tela_volumes(o),
                          relief="flat", bd=1, bg="#FFFFFF",
                          activebackground="#D0E3F7").pack()

            ttk.Label(card, text=obra,
                      font=("Segoe UI", 9, "bold")).pack(pady=4)

            item_catalogo = self.repo_catalogo.obter_por_nome(obra)
            obra_id = item_catalogo.id if item_catalogo else None

            media, n_reviews = self.repo_reviews.media_da_obra(obra, obra_id)
            if n_reviews > 0:
                estrelas = self._formatar_estrelas(media)
                ttk.Label(card,
                          text=f"{len(volumes)} vol • {estrelas} {media:.1f} ({n_reviews})",
                          font=("Segoe UI", 8),
                          foreground="#555555").pack()
            else:
                ttk.Label(card, text=f"{len(volumes)} vol(s)",
                          font=("Segoe UI", 8),
                          foreground="#555555").pack()
            i += 1

    def _montar_grid_volumes(self, nome_obra: str):
        for w in self.frame_volumes.winfo_children():
            w.destroy()

        topo = ttk.Frame(self.frame_volumes, padding=8)
        topo.pack(fill="x")
        ttk.Button(topo, text="◄ Voltar para Obras",
                   command=self.mostrar_tela_obras).pack(side="left", padx=5)
        ttk.Label(topo, text=f"Obra: {nome_obra}",
                  font=("Segoe UI", 11, "bold"),
                  foreground="#003366").pack(side="left", padx=15)

        frame_scroll = ttk.Frame(self.frame_volumes, relief="ridge")
        frame_scroll.pack(expand=True, fill="both", padx=15, pady=5)

        canvas = tk.Canvas(frame_scroll, bg="#E9EEF4", highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame_scroll, orient="vertical", command=canvas.yview)
        conteudo = ttk.Frame(canvas)
        conteudo.bind("<Configure>",
                      lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=conteudo, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", expand=True, fill="both")
        scrollbar.pack(side="right", fill="y")

        caminho_obra = os.path.join(_pasta_dados(), "pdf_padrao", nome_obra)
        try:
            volumes = [f for f in os.listdir(caminho_obra)
                       if f.lower().endswith(".pdf")]
        except OSError:
            volumes = []

        colunas = 4
        for idx, vol in enumerate(volumes):
            caminho_vol = os.path.join(caminho_obra, vol)
            tk_capa = self.gerar_capa_miniatura(caminho_vol)
            linha, coluna = divmod(idx, colunas)

            item = ttk.Frame(conteudo, padding=8, relief="solid")
            item.grid(row=linha, column=coluna, padx=12, pady=12)

            if tk_capa:
                btn = tk.Button(item, image=tk_capa,
                                command=lambda p=caminho_vol: self.abrir_manga_da_biblioteca(p),
                                relief="flat", bd=1, bg="#FFFFFF",
                                activebackground="#D0E3F7")
                btn.pack()
                btn.bind("<Button-3>",
                         lambda e, p=caminho_vol: self.exibir_menu_contexto(e, p))

            ttk.Label(item, text=os.path.splitext(vol)[0],
                      font=("Segoe UI", 8)).pack(pady=2)

            progresso = self.repo_progresso.obter(caminho_vol)
            if progresso.concluido:
                tk.Label(item, text="✔ LIDO", font=("Segoe UI", 8, "bold"),
                         fg="#008000", bg="#E9EEF4").pack()

    def exibir_menu_contexto(self, event, caminho_vol: str):
        menu = tk.Menu(self.root, tearoff=0)
        esta_concluido = self.repo_progresso.obter(caminho_vol).concluido
        if esta_concluido:
            menu.add_command(
                label="Desmarcar como lido",
                command=lambda: self.alternar_status_lido_manual(caminho_vol))
        else:
            menu.add_command(
                label="Marcar como lido",
                command=lambda: self.alternar_status_lido_manual(caminho_vol))
        menu.tk_popup(event.x_root, event.y_root)

    def alternar_status_lido_manual(self, caminho_vol: str):
        sucesso = self._executar_persistencia(
            lambda: self.repo_progresso.alternar_concluido(caminho_vol),
            "Erro ao atualizar status")
        if sucesso and self.obra_selecionada:
            self.mostrar_tela_volumes(self.obra_selecionada)

    # ==========================================================
    # LEITOR
    # ==========================================================
    def montar_tela_leitor(self):
        controles = ttk.Frame(self.frame_leitor, padding=6, relief="groove")
        controles.pack(side="top", fill="x")

        ttk.Button(controles, text="◄ Voltar aos Volumes",
                   command=self.voltar_para_volumes).pack(side="left", padx=5)
        ttk.Separator(controles, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(controles, text="◄ Anterior",
                   command=self.pagina_anterior).pack(side="left", padx=5)

        self.lbl_status_pagina = ttk.Label(controles, text="Página: 0 / 0",
                                            font=("Segoe UI", 9, "bold"))
        self.lbl_status_pagina.pack(side="left", padx=10)

        ttk.Button(controles, text="Próxima ►",
                   command=self.proxima_pagina).pack(side="left", padx=5)

        # ---------- Controles de zoom ----------
        ttk.Separator(controles, orient="vertical").pack(side="left", fill="y", padx=8)

        ttk.Label(controles, text="Zoom:",
                  font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))

        tk.Button(controles, text=" − ", command=self.zoom_out,
                  font=("Segoe UI", 11, "bold"), width=3,
                  bg="#F0F4F8", activebackground="#D0E3F7",
                  relief="raised", bd=1).pack(side="left", padx=1)

        self.lbl_zoom = ttk.Label(controles, text="100%",
                                   font=("Segoe UI", 9, "bold"),
                                   foreground="#003366", width=5,
                                   anchor="center")
        self.lbl_zoom.pack(side="left", padx=4)

        tk.Button(controles, text=" + ", command=self.zoom_in,
                  font=("Segoe UI", 11, "bold"), width=3,
                  bg="#F0F4F8", activebackground="#D0E3F7",
                  relief="raised", bd=1).pack(side="left", padx=1)

        tk.Button(controles, text="Ajustar", command=self.zoom_reset,
                  font=("Segoe UI", 8),
                  bg="#F0F4F8", activebackground="#D0E3F7",
                  relief="raised", bd=1, padx=6).pack(side="left", padx=6)

        # ---------- Canvas com scroll ----------
        frame_canvas = ttk.Frame(self.frame_leitor, relief="sunken")
        frame_canvas.pack(expand=True, fill="both", padx=8, pady=8)

        self.canvas = tk.Canvas(frame_canvas, bg="#50555A", highlightthickness=0)
        self.canvas.pack(side="left", expand=True, fill="both")

        scrollbar_v = ttk.Scrollbar(frame_canvas, orient="vertical",
                                      command=self.canvas.yview)
        scrollbar_v.pack(side="right", fill="y")

        scrollbar_h = ttk.Scrollbar(self.frame_leitor, orient="horizontal",
                                      command=self.canvas.xview)
        scrollbar_h.pack(side="bottom", fill="x", padx=8)

        self.canvas.configure(yscrollcommand=scrollbar_v.set,
                                xscrollcommand=scrollbar_h.set)

        self._resize_after_id = None
        self.canvas.bind("<Configure>", self._agendar_rerender)
        self.canvas.bind("<MouseWheel>", self._on_reader_scroll)
        self.canvas.bind("<Button-4>", self._on_reader_scroll_linux_up)
        self.canvas.bind("<Button-5>", self._on_reader_scroll_linux_down)

    def _agendar_rerender(self, _event=None):
        if not self.doc:
            return
        if self._resize_after_id is not None:
            try:
                self.root.after_cancel(self._resize_after_id)
            except tk.TclError:
                pass
        self._resize_after_id = self.root.after(150, self.exibir_pagina)

    def zoom_in(self):
        novo = self.zoom_atual * 1.25
        if novo > self.zoom_max:
            novo = self.zoom_max
        if abs(novo - self.zoom_atual) < 0.01:
            return
        self.zoom_atual = novo
        self.exibir_pagina()

    def zoom_out(self):
        novo = self.zoom_atual / 1.25
        if novo < self.zoom_min:
            novo = self.zoom_min
        if abs(novo - self.zoom_atual) < 0.01:
            return
        self.zoom_atual = novo
        self.exibir_pagina()

    def zoom_reset(self):
        self.zoom_atual = 1.0
        self.exibir_pagina()

    def _on_reader_scroll(self, event):
        """Scroll normal no canvas. Ctrl+scroll = zoom."""
        if event.state & 0x0004:
            if event.delta > 0:
                self.zoom_in()
            else:
                self.zoom_out()
        else:
            self.canvas.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def _on_reader_scroll_linux_up(self, event):
        if event.state & 0x0004:
            self.zoom_in()
        else:
            self.canvas.yview_scroll(-1, "units")
        return "break"

    def _on_reader_scroll_linux_down(self, event):
        if event.state & 0x0004:
            self.zoom_out()
        else:
            self.canvas.yview_scroll(1, "units")
        return "break"

    def voltar_para_volumes(self):
        if self.obra_selecionada:
            self.mostrar_tela_volumes(self.obra_selecionada)
        else:
            self.mostrar_tela_obras()

    def gerar_capa_miniatura(self, caminho_pdf: str):
        try:
            doc_temp = fitz.open(caminho_pdf)
            page = doc_temp.load_page(0)
            pix = page.get_pixmap(dpi=40)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            img.thumbnail((110, 150), Image.Resampling.LANCZOS)
            tk_capa = ImageTk.PhotoImage(img, master=self.root)
            self.capas_memoria.append(tk_capa)
            doc_temp.close()
            return tk_capa
        except Exception:
            return None

    def abrir_manga_da_biblioteca(self, caminho_pdf: str):
        self.carregar_documento(caminho_pdf)
        self._esconder_todas(self.frame_leitor)
        self.frame_leitor.pack(expand=True, fill="both")

    # ==========================================================
    # IMPORTAÇÃO
    # ==========================================================
    def importar_pasta_de_obra(self):
        pasta_origem = filedialog.askdirectory(
            title="Escolha a pasta que contém os PDFs da obra", mustexist=True)
        if not pasta_origem:
            return

        try:
            arquivos = os.listdir(pasta_origem)
        except OSError as e:
            messagebox.showerror("Erro ao ler pasta",
                                  f"Não foi possível abrir a pasta:\n{e}")
            return

        pdfs = sorted(f for f in arquivos
                      if f.lower().endswith(".pdf")
                      and os.path.isfile(os.path.join(pasta_origem, f)))

        if not pdfs:
            messagebox.showwarning(
                "Nenhum PDF encontrado",
                "A pasta escolhida não contém arquivos PDF.")
            return

        nome_obra = os.path.basename(os.path.normpath(pasta_origem))
        destino = os.path.join(self.pasta_pdf, nome_obra)
        ja_existe = os.path.isdir(destino)

        if ja_existe:
            resposta = messagebox.askyesnocancel(
                "Obra já existe",
                f"Já existe uma obra chamada '{nome_obra}'.\n\n"
                f"Deseja MESCLAR os arquivos novos com os existentes?")
            if resposta is None or resposta is False:
                return

        copiados = 0
        pulados = 0
        erros: list[str] = []

        try:
            os.makedirs(destino, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Erro ao criar pasta",
                                  f"Não foi possível criar '{destino}':\n{e}")
            return

        for nome_arquivo in pdfs:
            origem_arq = os.path.join(pasta_origem, nome_arquivo)
            destino_arq = os.path.join(destino, nome_arquivo)

            if os.path.exists(destino_arq):
                pulados += 1
                continue

            try:
                shutil.copy2(origem_arq, destino_arq)
                copiados += 1
            except OSError as e:
                erros.append(f"{nome_arquivo}: {e}")

        resumo = (f"Obra '{nome_obra}' importada.\n\n"
                  f"• {copiados} copiado(s)\n"
                  f"• {pulados} pulado(s)")
        if erros:
            resumo += f"\n\n⚠ {len(erros)} falharam"

        if copiados > 0:
            messagebox.showinfo("Importação concluída", resumo)
        else:
            messagebox.showwarning("Nada foi copiado", resumo)

        self.mostrar_tela_obras()

    def abrir_pasta_biblioteca(self):
        pasta = self.pasta_pdf
        if not os.path.isdir(pasta):
            try:
                os.makedirs(pasta, exist_ok=True)
            except OSError as e:
                messagebox.showerror("Erro", f"Não foi possível criar a pasta:\n{e}")
                return

        try:
            if os.name == "nt":
                os.startfile(pasta)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", pasta])
            else:
                subprocess.Popen(["xdg-open", pasta])
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível abrir a pasta:\n{e}")

    def abrir_pdf_externo(self):
        caminho = filedialog.askopenfilename(
            title="Selecione o PDF", filetypes=[("Arquivos PDF", "*.pdf")])
        if caminho:
            self.carregar_documento(caminho)
            self._esconder_todas(self.frame_leitor)
            self.frame_leitor.pack(expand=True, fill="both")

    def pagina_anterior(self):
        self._ultima_render_key = None
        if self.doc and self.pagina_atual > 0:
            self.pagina_atual -= 1
            self.registrar_pagina_atual()
            self.exibir_pagina()

    def proxima_pagina(self):
        self._ultima_render_key = None
        if self.doc and self.pagina_atual < self.total_paginas - 1:
            self.pagina_atual += 1
            self.registrar_pagina_atual()
            self.exibir_pagina()

    def carregar_documento(self, caminho: str):
        self.zoom_atual = 1.0 
        try:
            if self.doc:
                self.doc.close()
            self.doc = fitz.open(caminho)
            self.caminho_pdf_atual = caminho
            self.total_paginas = len(self.doc)

            progresso = self.repo_progresso.obter(caminho)
            self.pagina_atual = progresso.ultima_pagina
            if self.pagina_atual >= self.total_paginas:
                self.pagina_atual = 0

            self.exibir_pagina()
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível abrir o arquivo:\n{e}")

    def registrar_pagina_atual(self):
        if not self.caminho_pdf_atual:
            return
        try:
            self.repo_progresso.registrar_pagina(
                self.caminho_pdf_atual, self.pagina_atual, self.total_paginas)
        except ErroPersistencia:
            pass

    def exibir_pagina(self):
        if not self.doc:
            return

        self.root.update_idletasks()
        largura = self.canvas.winfo_width()
        altura = self.canvas.winfo_height()

        # Evita re-render se as dimensões não mudaram de verdade
        cache_key = (self.pagina_atual, largura, altura,
                     round(self.zoom_atual, 3))
        if getattr(self, "_ultima_render_key", None) == cache_key:
            return
        self._ultima_render_key = cache_key

        page = self.doc.load_page(self.pagina_atual)

        if largura > 10 and altura > 10:
            zoom_base = (altura - 20) / page.rect.height
            zoom = zoom_base * self.zoom_atual
        else:
            zoom = self.zoom_atual

        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))

        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self.tk_img = ImageTk.PhotoImage(img, master=self.root)

        img_w = pix.width
        img_h = pix.height

        scroll_w = max(img_w, largura)
        scroll_h = max(img_h, altura)

        x = (scroll_w - img_w) // 2
        y = (scroll_h - img_h) // 2

        self.canvas.delete("all")
        self.canvas.create_image(x, y, anchor="nw", image=self.tk_img)
        self.canvas.configure(scrollregion=(0, 0, scroll_w, scroll_h))

        self.lbl_status_pagina.config(
            text=f"Página: {self.pagina_atual + 1} / {self.total_paginas}")

        if hasattr(self, "lbl_zoom"):
            pct = int(round(self.zoom_atual * 100))
            self.lbl_zoom.config(text=f"{pct}%")

    # ==========================================================
    # PERFIL
    # ==========================================================
    def _montar_conteudo_perfil(self, alvo_nome: str | None = None):
        for w in self.frame_perfil.winfo_children():
            w.destroy()

        nome_proprio = self.sessao.nome if self.sessao is not None else "Leitor"
        self._perfil_alvo_nome = alvo_nome
        eh_perfil_proprio = (alvo_nome is None or alvo_nome == nome_proprio)
        if self.modo != "api":
            eh_perfil_proprio = True

        perfil_local = self.repo_perfis.ativo()

        canvas_perfil = tk.Canvas(self.frame_perfil, bg="#F0F4F8", highlightthickness=0)
        scroll_perfil = ttk.Scrollbar(self.frame_perfil, orient="vertical",
                                       command=canvas_perfil.yview)
        conteudo = ttk.Frame(canvas_perfil)
        conteudo.bind("<Configure>",
                      lambda e: canvas_perfil.configure(
                          scrollregion=canvas_perfil.bbox("all")))
        canvas_perfil.create_window((0, 0), window=conteudo, anchor="nw", width=910)
        canvas_perfil.configure(yscrollcommand=scroll_perfil.set)
        canvas_perfil.pack(side="left", fill="both", expand=True)
        scroll_perfil.pack(side="right", fill="y")

        cabecalho = ttk.Frame(conteudo, relief="solid", padding=15)
        cabecalho.pack(fill="x", padx=15, pady=10)

        # ---------- Carrega foto, bio e favoritos do perfil ----------
        foto_path_exibir = ""
        bio_exibir = ""
        favoritos_exibir: list[str] = []

        if eh_perfil_proprio:
            if perfil_local:
                foto_path_exibir = perfil_local.foto_path
                bio_exibir = perfil_local.bio.strip()
                favoritos_exibir = list(perfil_local.favoritos[:5])
        else:
            try:
                from perfis_api import RepositorioPerfisAPI
                api = RepositorioPerfisAPI(
                    os.environ.get("SOPHIA_API_URL",
                                    "https://sophia-api-lzwc.onrender.com"),
                    token=self.sessao.token if self.sessao else None,
                )
                p_remoto = api.obter(alvo_nome)
                if p_remoto:
                    foto_path_exibir = p_remoto.foto_path
                    bio_exibir = p_remoto.bio.strip()
                    favoritos_exibir = list(p_remoto.favoritos[:5])
                    print(f"[perfil] {alvo_nome} tem {len(favoritos_exibir)} favoritos")
            except Exception as e:
                print(f"[perfil] erro ao buscar {alvo_nome}: {e}")

        # Renderiza a foto
        img = None
        if foto_path_exibir:
            img = self._carregar_foto_perfil(foto_path_exibir, (120, 120))
        if img is None:
            img = self.carregar_icone("profile1.png", (120, 120))

        if img:
            lbl_foto = tk.Label(cabecalho, image=img)
            lbl_foto.pack(side="left", padx=(0, 15))
            lbl_foto.image = img
        else:
            tk.Label(cabecalho, text="(sem foto)", width=15, height=8,
                     bg="#D0E3F7", fg="#003366").pack(side="left", padx=(0, 15))

        textos = ttk.Frame(cabecalho)
        textos.pack(side="left", fill="both", expand=True)

        nome_exibicao = nome_proprio if eh_perfil_proprio else alvo_nome
        ttk.Label(textos, text=nome_exibicao,
                  font=("Segoe UI", 18, "bold")).pack(anchor="w", pady=(0, 5))

        if eh_perfil_proprio:
            bio = (perfil_local.bio.strip() if perfil_local and perfil_local.bio
                   else "Sem bio ainda. Clique em 'Editar Perfil' para escrever uma.")
            ttk.Label(textos, text=bio, wraplength=500,
                      justify="left").pack(anchor="w")
            ttk.Button(cabecalho, text="✏ Editar Perfil",
                       command=self.abrir_dialogo_editar_perfil).pack(
                side="right", anchor="n")
        else:
            if bio_exibir:
                ttk.Label(textos, text=bio_exibir, wraplength=500,
                          justify="left").pack(anchor="w", pady=(0, 10))
            else:
                ttk.Label(textos, text="Sem bio ainda.",
                          font=("Segoe UI", 9, "italic"),
                          foreground="#888888").pack(anchor="w", pady=(0, 10))

            ja_amigo = False
            if self.amizades_api is not None:
                try:
                    lista = self.amizades_api.listar()
                    ja_amigo = any(a.nome == alvo_nome for a in lista)
                except ErroAmizade:
                    pass

            if not ja_amigo:
                ttk.Button(cabecalho, text="+ Adicionar amigo",
                           command=lambda: self._enviar_pedido_para(alvo_nome)
                           ).pack(side="right", anchor="n")

        corpo = ttk.Frame(conteudo)
        corpo.pack(fill="x", padx=15, pady=5)

        if eh_perfil_proprio:
            titulo_fav = " 🌟 Meus 5 Favoritos "
        else:
            titulo_fav = f" 🌟 Favoritos de {nome_exibicao} "

        favoritos = ttk.LabelFrame(corpo, text=titulo_fav, padding=10)
        favoritos.pack(side="left", expand=True, fill="both", padx=(0, 10))

        ids_favoritos = list(favoritos_exibir[:5])
        while len(ids_favoritos) < 5:
            ids_favoritos.append(None)

        for i, obra_id in enumerate(ids_favoritos, start=1):
            col = ttk.Frame(favoritos)
            col.pack(side="left", expand=True, padx=5)

            if obra_id is None:
                if eh_perfil_proprio:
                    tk.Button(col, text="➕\nAdicionar",
                              bg="#E9EEF4", fg="#666666",
                              relief="flat", width=12, height=7,
                              font=("Segoe UI", 9), cursor="hand2",
                              command=self.abrir_dialogo_favoritos).pack()
                else:
                    tk.Label(col, text="", bg="#E9EEF4",
                             width=12, height=7, relief="flat").pack()
                ttk.Label(col, text=f"#{i}", font=("Segoe UI", 8, "bold"),
                          foreground="#AAAAAA").pack(pady=4)
                continue

            item = self.repo_catalogo.obter(obra_id)
            if item is None:
                tk.Button(col, text="⚠\nIndisponível",
                          bg="#F5F5F5", fg="#999999",
                          relief="flat", width=12, height=7,
                          font=("Segoe UI", 9), state="disabled").pack()
                ttk.Label(col, text=f"#{i}", font=("Segoe UI", 8, "bold"),
                          foreground="#AAAAAA").pack(pady=4)
                continue

            # Comando de clique: próprio perfil abre volumes, outro abre detalhes
            if eh_perfil_proprio:
                cmd_capa = lambda n=item.nome: self.mostrar_tela_volumes(n)
            else:
                cmd_capa = lambda it=item: self._abrir_detalhes(it)

            tk_capa = None
            if self._obra_tem_pdfs_local(item.nome):
                caminho_local = os.path.join(self.pasta_pdf, item.nome)
                try:
                    arquivos = [f for f in os.listdir(caminho_local)
                                if f.lower().endswith(".pdf")]
                    if arquivos:
                        tk_capa = self.gerar_capa_miniatura(
                            os.path.join(caminho_local, sorted(arquivos)[0]))
                except OSError:
                    pass

            if tk_capa:
                tk.Button(col, image=tk_capa, relief="flat", bd=1, bg="#FFFFFF",
                          cursor="hand2", command=cmd_capa).pack()
            else:
                capa_frame = tk.Frame(col, bg="#D0E3F7", width=120, height=170)
                capa_frame.pack()
                capa_frame.pack_propagate(False)
                btn = tk.Button(capa_frame, text="📖", bg="#D0E3F7", fg="#003366",
                                 font=("Segoe UI", 32), relief="flat",
                                 cursor="hand2", command=cmd_capa)
                btn.pack(expand=True, fill="both")

                if item.capa_url:
                    caminho_cache = self.capas.obter_cache(item.id)
                    if caminho_cache:
                        img = self._carregar_capa_ajustada(
                            caminho_cache, 120, 170, f"capa_{item.id}")
                        if img:
                            btn.config(image=img, text="")
                            btn.image = img

            ttk.Label(col, text=f"#{i}", font=("Segoe UI", 8, "bold")).pack(pady=4)

        if eh_perfil_proprio:
            ttk.Button(favoritos, text="Editar",
                       command=self.abrir_dialogo_favoritos
                       ).pack(side="right", padx=5, anchor="n")

            amigos_frame = ttk.LabelFrame(corpo, text=" 👥 Amigos ", padding=5)
            amigos_frame.pack(side="right", fill="y", padx=(10, 0))
            self._montar_lista_amigos_perfil(amigos_frame)

        mural = ttk.LabelFrame(conteudo,
                                text=f" 💬 Mural de {nome_exibicao}", padding=10)
        mural.pack(fill="x", padx=15, pady=10)
        self._montar_mural(mural, nome_exibicao)

    def _montar_lista_amigos_perfil(self, parent):
        canvas_amigos = tk.Canvas(parent, width=160, height=250,
                                   bg="#F0F4F8", highlightthickness=0)
        scroll_amigos = ttk.Scrollbar(parent, orient="vertical",
                                       command=canvas_amigos.yview)
        lista_amigos = ttk.Frame(canvas_amigos)
        lista_amigos.bind("<Configure>",
                          lambda e: canvas_amigos.configure(
                              scrollregion=canvas_amigos.bbox("all")))
        canvas_amigos.create_window((0, 0), window=lista_amigos, anchor="nw")
        canvas_amigos.configure(yscrollcommand=scroll_amigos.set)
        canvas_amigos.pack(side="left", fill="both", expand=True)
        scroll_amigos.pack(side="right", fill="y")

        if self.amizades_api is not None:
            try:
                amigos_reais = self.amizades_api.listar()
            except ErroAmizade:
                amigos_reais = []

            if not amigos_reais:
                ttk.Label(lista_amigos, text="Sem amigos ainda",
                          font=("Segoe UI", 8, "italic"),
                          foreground="#888888").pack(pady=10, padx=5)
            else:
                for amigo in amigos_reais:
                    f = ttk.Frame(lista_amigos, cursor="hand2")
                    f.pack(fill="x", pady=2)

                    lbl = ttk.Label(f, text=f"👤 {amigo.nome}",
                                    font=("Segoe UI", 9), cursor="hand2")
                    lbl.pack(side="left", padx=5)
                    tk.Label(f, text="●", fg="#4CAF50", bg="#F0F4F8",
                             font=("Arial", 8)).pack(side="right", padx=5)

                    for w in (f, lbl):
                        w.bind("<Button-1>",
                               lambda e, n=amigo.nome: self._abrir_perfil_de(n))
                        w.bind("<Button-3>",
                               lambda e, n=amigo.nome: self._menu_perfil_amigo(e, n))
        else:
            for amigo in self.repo_chat.amigos:
                f = ttk.Frame(lista_amigos)
                f.pack(fill="x", pady=2)
                ttk.Label(f, text=f"👤 {amigo}",
                          font=("Segoe UI", 9)).pack(side="left", padx=5)
                tk.Label(f, text="●", fg="#4CAF50", bg="#F0F4F8",
                         font=("Arial", 8)).pack(side="right", padx=5)

    def _montar_mural(self, parent, alvo_nome: str):
        eh_perfil_proprio = (alvo_nome == (self.sessao.nome if self.sessao else "Leitor"))

        if self.comentarios_api is not None:
            linha_novo = ttk.Frame(parent)
            linha_novo.pack(fill="x", pady=(0, 12))

            self.var_novo_comentario = tk.StringVar()
            entrada = ttk.Entry(linha_novo, textvariable=self.var_novo_comentario,
                                font=("Segoe UI", 10))
            entrada.pack(side="left", fill="x", expand=True, padx=(0, 8))
            entrada.bind("<Return>", lambda e: self._postar_comentario(alvo_nome))

            ttk.Button(linha_novo, text="Postar",
                       command=lambda: self._postar_comentario(alvo_nome)
                       ).pack(side="right")
        elif not eh_perfil_proprio:
            ttk.Label(parent, text="(mural indisponível em modo local)",
                      font=("Segoe UI", 9, "italic"),
                      foreground="#888888").pack(pady=10)

        if self.comentarios_api is not None:
            try:
                comentarios = self.comentarios_api.listar(alvo_nome)
            except ErroComentario as e:
                ttk.Label(parent, text=f"⚠ {e}",
                          foreground="#C2185B",
                          font=("Segoe UI", 9)).pack(pady=15)
                return
        else:
            comentarios = None

        if comentarios is not None and not comentarios:
            ttk.Label(parent, text="Nenhum recado ainda. Seja o primeiro a escrever!",
                      font=("Segoe UI", 10, "italic"),
                      foreground="#888888").pack(pady=25)
            return

        if comentarios is not None:
            for c in comentarios:
                box = ttk.Frame(parent, relief="groove", padding=8)
                box.pack(fill="x", pady=5)

                header = ttk.Frame(box)
                header.pack(fill="x")

                ttk.Label(header, text=c.autor_nome,
                          font=("Segoe UI", 9, "bold"),
                          foreground="#005A9E").pack(side="left")
                ttk.Label(header, text=f"  •  {c.criado_em}",
                          font=("Segoe UI", 8),
                          foreground="#888888").pack(side="left")

                eu_sou_autor = self.sessao and c.autor_nome == self.sessao.nome
                eu_sou_dono = eh_perfil_proprio
                if eu_sou_autor or eu_sou_dono:
                    tk.Button(header, text="✖", fg="#C2185B", bg="#F0F4F8",
                              relief="flat", bd=0, cursor="hand2",
                              font=("Segoe UI", 9),
                              command=lambda cid=c.id: self._deletar_comentario(
                                  cid, alvo_nome)
                              ).pack(side="right")

                ttk.Label(box, text=c.texto, wraplength=820,
                          justify="left").pack(anchor="w", pady=(4, 0))
        else:
            recados = [
                ("xX_DarkSasuke_Xx", "Que perfil daora!"),
                ("LeitoraVoraz", "Passando pra deixar um +rep."),
                ("SophiaFan", "Esse aplicativo tá ficando muito bom!"),
                ("NoobMaster69", "Alguém sabe me dizer como passa de página?"),
            ]
            for autor, msg in recados:
                box = ttk.Frame(parent, relief="groove", padding=8)
                box.pack(fill="x", pady=5)
                ttk.Label(box, text=autor, font=("Segoe UI", 9, "bold"),
                          foreground="#005A9E").pack(anchor="w")
                ttk.Label(box, text=msg, wraplength=820).pack(anchor="w", pady=(3, 0))

    def _abrir_perfil_de(self, nome_usuario: str):
        if self.modo != "api":
            messagebox.showinfo("Modo local",
                                "Ver perfil de outros só funciona em modo API.")
            return
        self._esconder_todas(self.frame_perfil)
        self.frame_perfil.pack(expand=True, fill="both")
        self._montar_conteudo_perfil(alvo_nome=nome_usuario)

    def _menu_perfil_amigo(self, event, nome_usuario: str):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label=f"Ver perfil de {nome_usuario}",
                         command=lambda: self._abrir_perfil_de(nome_usuario))
        menu.tk_popup(event.x_root, event.y_root)

    def _enviar_pedido_para(self, nome_usuario: str):
        if self.amizades_api is None:
            return
        try:
            self.amizades_api.enviar_pedido(nome_usuario)
        except ErroAmizade as e:
            messagebox.showerror("Erro", str(e))
            return
        messagebox.showinfo("Pedido enviado",
                            f"Pedido de amizade enviado para '{nome_usuario}'.")
        self._abrir_perfil_de(nome_usuario)

    def _postar_comentario(self, alvo_nome: str):
        if self.comentarios_api is None:
            return
        texto = self.var_novo_comentario.get().strip()
        if not texto:
            return
        try:
            self.comentarios_api.postar(alvo_nome, texto)
        except ErroComentario as e:
            messagebox.showerror("Erro ao postar", str(e))
            return
        self._montar_conteudo_perfil(alvo_nome=self._perfil_alvo_nome)

    def _deletar_comentario(self, comentario_id: str, alvo_nome: str):
        if self.comentarios_api is None:
            return
        if not messagebox.askyesno("Deletar comentário",
                                    "Tem certeza que deseja deletar este comentário?"):
            return
        try:
            self.comentarios_api.deletar(comentario_id)
        except ErroComentario as e:
            messagebox.showerror("Erro ao deletar", str(e))
            return
        self._montar_conteudo_perfil(alvo_nome=self._perfil_alvo_nome)

    # ==========================================================
    # DIÁLOGO: EDITAR PERFIL
    # ==========================================================
    def abrir_dialogo_editar_perfil(self):
        perfil = self.repo_perfis.ativo()
        if perfil is None:
            return

        janela = tk.Toplevel(self.root)
        janela.title("Editar Perfil")
        janela.geometry("560x620")
        janela.configure(bg="#F0F4F8")
        janela.transient(self.root)
        janela.grab_set()

        corpo = ttk.Frame(janela, padding=18)
        corpo.pack(fill="both", expand=True)

        ttk.Label(corpo, text="Editar Perfil",
                  font=("Segoe UI", 15, "bold"),
                  foreground="#003366").pack(anchor="w", pady=(0, 12))

        ttk.Label(corpo, text="Nome:").pack(anchor="w")
        ttk.Label(corpo, text=perfil.nome, font=("Segoe UI", 10, "bold"),
                  foreground="#005A9E").pack(anchor="w", pady=(2, 2))
        ttk.Label(corpo, text="(o nome identifica o perfil nas reviews)",
                  font=("Segoe UI", 8, "italic"),
                  foreground="#777777").pack(anchor="w", pady=(0, 12))

        ttk.Label(corpo, text="Foto de perfil:").pack(anchor="w")
        linha_foto = ttk.Frame(corpo)
        linha_foto.pack(fill="x", pady=(4, 12))

        ttk.Label(corpo, text="Favoritos do catálogo:").pack(anchor="w", pady=(10, 0))
        linha_fav = ttk.Frame(corpo)
        linha_fav.pack(fill="x", pady=(4, 12))

        qtd_fav = len([f for f in perfil.favoritos if f])
        ttk.Label(linha_fav,
                  text=f"{qtd_fav} de {self.repo_perfis.LIMITE_FAVORITOS} escolhidos",
                  font=("Segoe UI", 9, "italic"),
                  foreground="#555555").pack(side="left")
        ttk.Button(linha_fav, text="⭐ Definir Favoritos",
                   command=self.abrir_dialogo_favoritos).pack(side="right")

        foto_ref = {"tk": None}
        lbl_foto = tk.Label(linha_foto, width=10, height=5, bg="#E9EEF4")
        lbl_foto.pack(side="left", padx=(0, 12))

        def atualizar_preview():
            img = self._carregar_foto_perfil(perfil.foto_path, (80, 80))
            if img is None:
                img = self.carregar_icone("profile1.png", (80, 80))
            foto_ref["tk"] = img
            if img:
                lbl_foto.config(image=img, text="")
            else:
                lbl_foto.config(image="", text="(sem foto)")

        atualizar_preview()

        def escolher_foto():
            import base64
            from io import BytesIO

            caminho = filedialog.askopenfilename(
                title="Escolha uma foto de perfil",
                filetypes=[("Imagens", "*.png *.jpg *.jpeg *.gif *.webp"),
                           ("Todos os arquivos", "*.*")],
                parent=janela)
            if not caminho:
                return

            try:
                img = Image.open(caminho).convert("RGB")
                img.thumbnail((200, 200), Image.Resampling.LANCZOS)
                buffer = BytesIO()
                img.save(buffer, format="JPEG", quality=85)
                dados = buffer.getvalue()
                b64 = base64.b64encode(dados).decode("ascii")
                perfil.foto_path = f"data:image/jpeg;base64,{b64}"
                print(f"[foto] convertida pra base64: {len(b64)} chars")
            except Exception as e:
                messagebox.showerror("Erro",
                                      f"Nao foi possivel processar a imagem:\n{e}",
                                      parent=janela)
                return

            atualizar_preview()

        ttk.Button(linha_foto, text="Escolher Foto...",
                   command=escolher_foto).pack(side="left", anchor="n")

        ttk.Label(corpo, text="Bio:").pack(anchor="w")
        texto_bio = tk.Text(corpo, height=8, wrap="word",
                            font=("Segoe UI", 10), relief="sunken", bd=2)
        texto_bio.pack(fill="both", expand=True, pady=(3, 12))
        texto_bio.insert("1.0", perfil.bio)

        def salvar():
            perfil.bio = texto_bio.get("1.0", "end-1c").strip()
            sucesso = self._executar_persistencia(
                lambda: self.repo_perfis.atualizar(perfil),
                "Erro ao salvar perfil")
            if not sucesso:
                return

            # ---------- Envia pro servidor ----------
            if self.modo == "api" and self.sessao is not None:
                try:
                    from perfis_api import RepositorioPerfisAPI
                    api = RepositorioPerfisAPI(
                        os.environ.get("SOPHIA_API_URL",
                                        "https://sophia-api-lzwc.onrender.com"),
                        token=self.sessao.token,
                    )
                    api.atualizar(perfil.nome, perfil.bio, perfil.foto_path)
                    print("[perfil-sync] bio/foto enviados pro servidor")
                except Exception as e:
                    print(f"[perfil-sync] ERRO ao enviar: {e}")
                    messagebox.showwarning(
                        "Aviso",
                        f"Perfil salvo local, mas falhou enviar ao servidor:\n{e}"
                    )

            janela.destroy()
            self.abrir_tela_perfil()

        botoes = ttk.Frame(corpo)
        botoes.pack(fill="x")
        ttk.Button(botoes, text="Cancelar",
                   command=janela.destroy).pack(side="right", padx=5)
        ttk.Button(botoes, text="Salvar",
                   command=salvar).pack(side="right")

    # ==========================================================
    # TELA: REVIEWS
    # ==========================================================
    def atualizar_tela_reviews(self):
        for w in self.frame_reviews.winfo_children():
            w.destroy()

        topo = ttk.Frame(self.frame_reviews, padding=12)
        topo.pack(fill="x")
        ttk.Label(topo, text="Diário de Reviews",
                  font=("Segoe UI", 16, "bold"),
                  foreground="#003366").pack(side="left")
        ttk.Button(topo, text="+ Escrever Review",
                   command=self.formulario_review).pack(side="right", padx=5)

        faixa = ttk.Frame(self.frame_reviews, padding=(12, 0, 12, 10))
        faixa.pack(fill="x")
        ttk.Label(faixa, text="Perfil:",
                  font=("Segoe UI", 9, "bold")).pack(side="left")

        nome_perfil = self._perfil_atual()
        ttk.Label(faixa, text=f"👤 {nome_perfil}",
                  font=("Segoe UI", 10, "bold"),
                  foreground="#005A9E").pack(side="left", padx=6)

        lista = ttk.Frame(self.frame_reviews, padding=(12, 0, 12, 12))
        lista.pack(fill="both", expand=True)
        canvas = tk.Canvas(lista, bg="#E9EEF4", highlightthickness=0)
        barra = ttk.Scrollbar(lista, orient="vertical", command=canvas.yview)
        interior = ttk.Frame(canvas)
        interior.bind("<Configure>",
                      lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=interior, anchor="nw",
                             width=900, tags="interior")
        canvas.configure(yscrollcommand=barra.set)
        canvas.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure("interior", width=e.width))

        reviews = self.repo_reviews.listar_por_perfil(nome_perfil)
        if not reviews:
            ttk.Label(interior,
                      text="Você ainda não publicou nenhuma review.\n"
                           "Clique em '+ Escrever Review' para começar!",
                      justify="center", font=("Segoe UI", 11),
                      foreground="#555555").pack(pady=45, padx=20)
            return

        reviews.sort(key=lambda r: r.data, reverse=True)
        for review in reviews:
            card = ttk.LabelFrame(interior, text=f"  {review.obra}  ", padding=12)
            card.pack(fill="x", padx=12, pady=8)
            estrelas = "★" * review.nota + "☆" * (5 - review.nota)
            ttk.Label(card, text=f"{estrelas}   {review.nota}/5",
                      font=("Segoe UI", 12, "bold"),
                      foreground="#B77900").pack(anchor="w")
            ttk.Label(card, text=f"Por {review.perfil}  •  {review.data}",
                      foreground="#555555").pack(anchor="w", pady=(2, 6))
            ttk.Label(card, text=review.texto, wraplength=820,
                      justify="left").pack(anchor="w", fill="x")
            botoes = ttk.Frame(card)
            botoes.pack(anchor="e", pady=(8, 0))
            ttk.Button(botoes, text="Editar",
                       command=lambda rid=review.id: self.formulario_review(rid)
                       ).pack(side="left", padx=3)
            ttk.Button(botoes, text="Excluir",
                       command=lambda rid=review.id: self.excluir_review(rid)
                       ).pack(side="left", padx=3)

    def _perfil_atual(self) -> str:
        if self.modo == "api" and self.sessao is not None:
            return self.sessao.nome
        return "Leitor"

    def formulario_review(self, review_id: str | None = None,
                          obra_nome: str | None = None,
                          obra_id: str | None = None):
        obras = self.listar_obras_para_review()
        if obra_nome and obra_nome not in obras:
            obras = [obra_nome] + obras

        if not obras:
            messagebox.showinfo("Biblioteca vazia",
                                "Adicione pelo menos uma obra com PDFs antes.")
            return

        existente = self.repo_reviews.obter(review_id) if review_id else None

        janela = tk.Toplevel(self.root)
        janela.title("Editar Review" if existente else "Escrever Review")
        janela.geometry("520x440")
        janela.configure(bg="#F0F4F8")
        janela.transient(self.root)
        janela.grab_set()

        corpo = ttk.Frame(janela, padding=18)
        corpo.pack(fill="both", expand=True)
        ttk.Label(corpo, text="Nova avaliação",
                  font=("Segoe UI", 15, "bold"),
                  foreground="#003366").pack(anchor="w", pady=(0, 12))

        ttk.Label(corpo, text="Obra da biblioteca:").pack(anchor="w")
        valor_inicial = (existente.obra if existente else (obra_nome or obras[0]))
        var_obra = tk.StringVar(value=valor_inicial)
        ttk.Combobox(corpo, textvariable=var_obra, values=obras,
                     state="readonly").pack(fill="x", pady=(3, 12))

        ttk.Label(corpo, text="Sua nota (1 a 5 estrelas):").pack(anchor="w")
        var_nota = tk.IntVar(value=existente.nota if existente else 5)
        linha = ttk.Frame(corpo)
        linha.pack(anchor="w", pady=4)
        for n in range(1, 6):
            ttk.Radiobutton(linha, text="★" * n, value=n,
                            variable=var_nota).pack(side="left", padx=4)

        ttk.Label(corpo, text="Sua análise:").pack(anchor="w", pady=(10, 0))
        texto = tk.Text(corpo, height=9, wrap="word",
                        font=("Segoe UI", 10), relief="sunken", bd=2)
        texto.pack(fill="both", expand=True, pady=5)
        if existente:
            texto.insert("1.0", existente.texto)

        def salvar():
            conteudo = texto.get("1.0", "end-1c").strip()
            if not conteudo:
                messagebox.showwarning("Review vazia",
                                        "Escreva sua análise antes de salvar.",
                                        parent=janela)
                return

            nome_obra_escolhida = var_obra.get()
            item_cat = self.repo_catalogo.obter_por_nome(nome_obra_escolhida)
            id_auto = item_cat.id if item_cat else None

            if existente:
                existente.obra = nome_obra_escolhida
                existente.obra_id = id_auto
                existente.nota = var_nota.get()
                existente.texto = conteudo
                existente.editada_em = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
                acao = lambda: self.repo_reviews.atualizar(existente)
            else:
                nova = Review.nova(
                    self._perfil_atual(),
                    nome_obra_escolhida,
                    var_nota.get(),
                    conteudo,
                    obra_id=id_auto,
                )
                acao = lambda: self.repo_reviews.adicionar(nova)

            if not self._executar_persistencia(acao, "Erro ao salvar review"):
                return
            janela.destroy()
            self.atualizar_tela_reviews()

            if (self._detalhes_item_atual is not None
                    and self.frame_detalhes_obra.winfo_ismapped()):
                self._montar_detalhes_obra(self._detalhes_item_atual)

        ttk.Button(corpo, text="Salvar Review",
                   command=salvar).pack(anchor="e", pady=(8, 0))

    def listar_obras_para_review(self) -> list[str]:
        pasta = os.path.join(_pasta_dados(), "pdf_padrao")
        if not os.path.isdir(pasta):
            return []
        resultado = []
        try:
            for nome in os.listdir(pasta):
                caminho = os.path.join(pasta, nome)
                if not os.path.isdir(caminho):
                    continue
                try:
                    if any(f.lower().endswith(".pdf") for f in os.listdir(caminho)):
                        resultado.append(nome)
                except OSError:
                    continue
        except OSError:
            return []
        return sorted(resultado)

    def excluir_review(self, review_id: str):
        if not messagebox.askyesno("Excluir review",
                                    "Tem certeza de que deseja excluir esta avaliação?"):
            return
        sucesso = self._executar_persistencia(
            lambda: self.repo_reviews.remover(review_id),
            "Erro ao excluir review")
        if sucesso:
            self.atualizar_tela_reviews()
            if (self._detalhes_item_atual is not None
                    and self.frame_detalhes_obra.winfo_ismapped()):
                self._montar_detalhes_obra(self._detalhes_item_atual)

    # ==========================================================
    # BUSCA DE USUÁRIOS
    # ==========================================================
    def _buscar_usuario(self):
        termo = self.var_busca.get().strip()
        if not termo:
            return

        if self.busca_api is None:
            messagebox.showinfo("Modo local",
                                 "Busca de usuários só funciona em modo API.")
            return

        try:
            resultados = self.busca_api.buscar(termo)
        except ErroBusca as e:
            messagebox.showerror("Erro na busca", str(e))
            return

        self._mostrar_resultados_busca(resultados, termo)

    def _mostrar_resultados_busca(self, resultados, termo):
        janela = tk.Toplevel(self.root)
        janela.title(f"Busca: {termo}")
        janela.geometry("440x480")
        janela.configure(bg="#F0F4F8")
        janela.transient(self.root)
        janela.grab_set()
        janela.bind("<Escape>", lambda e: janela.destroy())

        corpo = ttk.Frame(janela, padding=18)
        corpo.pack(fill="both", expand=True)

        ttk.Label(corpo, text=f"🔍 Resultados para '{termo}'",
                  font=("Segoe UI", 14, "bold"),
                  foreground="#003366").pack(anchor="w")
        ttk.Label(corpo, text=f"{len(resultados)} usuário(s) encontrado(s)",
                  font=("Segoe UI", 9, "italic"),
                  foreground="#666666").pack(anchor="w", pady=(2, 14))

        if not resultados:
            ttk.Label(corpo,
                      text="Nenhum usuário encontrado.\n\n"
                           "Verifique a grafia ou tente outro termo.",
                      justify="center", font=("Segoe UI", 10),
                      foreground="#888888").pack(pady=40)
            ttk.Button(corpo, text="Fechar",
                       command=janela.destroy).pack()
            return

        frame_lista = ttk.Frame(corpo, relief="sunken", borderwidth=1)
        frame_lista.pack(fill="both", expand=True)

        canvas = tk.Canvas(frame_lista, bg="#FFFFFF", highlightthickness=0)
        scroll = ttk.Scrollbar(frame_lista, orient="vertical", command=canvas.yview)
        interior = ttk.Frame(canvas)
        interior.bind("<Configure>",
                      lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=interior, anchor="nw", width=370)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        for u in resultados:
            linha = ttk.Frame(interior, padding=10)
            linha.pack(fill="x", padx=4, pady=2)

            texto = f"👤  {u.nome}"
            if u.eu_mesmo:
                texto += "  (você)"

            btn = tk.Button(
                linha, text=texto,
                anchor="w", justify="left",
                bg="#FFFFFF", activebackground="#D0E3F7",
                relief="flat", bd=0, cursor="hand2",
                font=("Segoe UI", 11),
                command=lambda n=u.nome: self._abrir_perfil_e_fechar(n, janela),
            )
            btn.pack(side="left", fill="x", expand=True)

            ttk.Label(linha, text=u.criado_em,
                      font=("Segoe UI", 8),
                      foreground="#888888").pack(side="right", padx=8)

        ttk.Button(corpo, text="Fechar",
                   command=janela.destroy).pack(pady=(14, 0))

    def _abrir_perfil_e_fechar(self, nome, janela):
        janela.destroy()
        self._abrir_perfil_de(nome)

    # ==========================================================
    # TELA: CHATOCHAT
    # ==========================================================
    def montar_tela_chatochat(self):
        for w in self.frame_chatochat.winfo_children():
            w.destroy()

        cabecalho = tk.Frame(self.frame_chatochat, bg="#003366", height=54)
        cabecalho.pack(fill="x")
        cabecalho.pack_propagate(False)
        tk.Label(cabecalho, text="💬 ChatoChat", bg="#003366", fg="white",
                 font=("Segoe UI", 16, "bold")).pack(side="left", padx=16, pady=10)

        if self.amizades_api is not None:
            tk.Button(cabecalho, text="📬 Pedidos",
                      command=self._abrir_pedidos_pendentes,
                      bg="#DCEBFA", fg="#003366",
                      relief="raised").pack(side="right", padx=12, pady=10)
        else:
            tk.Label(cabecalho, text="(modo local — lista fictícia)",
                     bg="#003366", fg="#A8C6E0",
                     font=("Segoe UI", 9, "italic")).pack(side="right", padx=12, pady=10)

        area = ttk.Frame(self.frame_chatochat, padding=10)
        area.pack(fill="both", expand=True)

        painel_contatos = ttk.LabelFrame(area, text=" Conversas ", padding=6)
        painel_contatos.pack(side="left", fill="y", padx=(0, 10))
        painel_contatos.configure(width=245)
        painel_contatos.pack_propagate(False)

        lista_canvas = tk.Canvas(painel_contatos, bg="#E9EEF4",
                                  highlightthickness=0, width=220)
        lista_scroll = ttk.Scrollbar(painel_contatos, orient="vertical",
                                       command=lista_canvas.yview)
        lista_interna = ttk.Frame(lista_canvas)
        lista_interna.bind("<Configure>",
                            lambda e: lista_canvas.configure(
                                scrollregion=lista_canvas.bbox("all")))
        lista_canvas.create_window((0, 0), window=lista_interna,
                                    anchor="nw", width=215)
        lista_canvas.configure(yscrollcommand=lista_scroll.set)
        lista_canvas.pack(side="left", fill="both", expand=True)
        lista_scroll.pack(side="right", fill="y")

        painel_chat = ttk.LabelFrame(area, text=" Mensagens ", padding=8)
        painel_chat.pack(side="left", fill="both", expand=True)

        self.chat_titulo = ttk.Label(painel_chat,
                                      text="Escolha um amigo para abrir a conversa",
                                      font=("Segoe UI", 12, "bold"),
                                      foreground="#003366")
        self.chat_titulo.pack(anchor="w", pady=(0, 8))

        self.chat_mensagens_canvas = tk.Canvas(painel_chat, bg="#F7F9FC",
                                                highlightthickness=0)
        barra_msgs = ttk.Scrollbar(painel_chat, orient="vertical",
                                     command=self.chat_mensagens_canvas.yview)
        self.chat_mensagens_frame = ttk.Frame(self.chat_mensagens_canvas)
        self.chat_mensagens_frame.bind(
            "<Configure>",
            lambda e: self.chat_mensagens_canvas.configure(
                scrollregion=self.chat_mensagens_canvas.bbox("all")))
        self.chat_mensagens_canvas.create_window(
            (0, 0), window=self.chat_mensagens_frame, anchor="nw", tags="msgs")
        self.chat_mensagens_canvas.bind(
            "<Configure>",
            lambda e: self.chat_mensagens_canvas.itemconfig("msgs", width=e.width))
        self.chat_mensagens_canvas.configure(yscrollcommand=barra_msgs.set)
        self.chat_mensagens_canvas.pack(side="left", fill="both", expand=True)
        barra_msgs.pack(side="right", fill="y")

        rodape = ttk.Frame(painel_chat, padding=(0, 8, 0, 0))
        rodape.pack(fill="x")
        self.var_mensagem_chat = tk.StringVar()
        self.entrada_chat = ttk.Entry(rodape, textvariable=self.var_mensagem_chat,
                                       font=("Segoe UI", 10))
        self.entrada_chat.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entrada_chat.bind("<Return>", lambda e: self.enviar_mensagem_chat())
        ttk.Button(rodape, text="Enviar ➤",
                   command=self.enviar_mensagem_chat).pack(side="right")

        self._botoes_contatos = {}

        if self.chat_api is not None:
            try:
                conversas = self.chat_api.listar_conversas()
            except ErroChat as e:
                ttk.Label(lista_interna, text=f"⚠ {e}",
                          foreground="#C2185B", wraplength=190,
                          font=("Segoe UI", 9)).pack(pady=20, padx=10)
                return

            if not conversas:
                ttk.Label(lista_interna,
                          text="Você ainda não tem amigos.\n\n"
                               "Clique em '+ Adicionar amigo'.",
                          foreground="#666666", justify="center",
                          font=("Segoe UI", 9)).pack(pady=30, padx=10)
                return

            for c in conversas:
                preview = c.ultima_mensagem or "Comece uma conversa..."
                preview = preview[:25]

                badge = f"  ({c.nao_lidas})" if c.nao_lidas > 0 else ""
                texto = f"👤  {c.amigo_nome}{badge}\n{preview}"
                bg_btn = "#DCEBFA" if c.nao_lidas > 0 else "#F0F4F8"
                fg_btn = "#003366" if c.nao_lidas > 0 else "#000000"

                btn = tk.Button(
                    lista_interna, text=texto,
                    anchor="w", justify="left", wraplength=185,
                    bg=bg_btn, fg=fg_btn, activebackground="#D0E3F7",
                    relief="groove", padx=8, pady=9,
                    command=lambda a=c.amigo_nome: self.abrir_conversa_chat(a),
                )
                btn.pack(fill="x", pady=3)
                self._botoes_contatos[c.amigo_nome] = btn
        else:
            for nome in self.repo_chat.amigos:
                conversa = self.repo_chat.obter_conversa(nome)
                ultima = conversa[-1].texto if conversa else "Comece uma conversa..."
                btn = tk.Button(
                    lista_interna,
                    text=f"👤  {nome}\n{ultima[:27]}",
                    anchor="w", justify="left", wraplength=185,
                    bg="#F0F4F8", activebackground="#D0E3F7",
                    relief="groove", padx=8, pady=9,
                    command=lambda a=nome: self.abrir_conversa_chat(a),
                )
                btn.pack(fill="x", pady=3)
                self._botoes_contatos[nome] = btn

        if self.amigo_chat_ativo in self._botoes_contatos:
            self.abrir_conversa_chat(self.amigo_chat_ativo)

    def abrir_conversa_chat(self, amigo: str):
        self.amigo_chat_ativo = amigo
        self.chat_titulo.config(text=f"👤  {amigo}")
        self._chat_ultimo_id = None
        self._chat_msgs_renderizadas = set()

        for w in self.chat_mensagens_frame.winfo_children():
            w.destroy()

        if self.chat_api is not None:
            try:
                mensagens = self.chat_api.listar_mensagens(amigo)
            except ErroChat as e:
                ttk.Label(self.chat_mensagens_frame,
                          text=f"⚠ {e}",
                          foreground="#C2185B",
                          font=("Segoe UI", 10)).pack(pady=25, padx=12)
                return

            if not mensagens:
                ttk.Label(self.chat_mensagens_frame,
                          text="Esta conversa está vazia. Mande um oi!",
                          foreground="#666666").pack(pady=25, padx=12)
                return

            for m in mensagens:
                self._render_mensagem(m)
                self._chat_msgs_renderizadas.add(m.id)

            self._chat_ultimo_id = mensagens[-1].id
            self.chat_mensagens_canvas.update_idletasks()
            self.chat_mensagens_canvas.yview_moveto(1.0)
            self.entrada_chat.focus_set()
            return

        mensagens_locais = self.repo_chat.obter_conversa(amigo)
        if not mensagens_locais:
            ttk.Label(self.chat_mensagens_frame,
                      text="Esta conversa está vazia. Mande um oi!",
                      foreground="#666666").pack(pady=25, padx=12)

        for msg in mensagens_locais:
            minha = msg.autor == "Você"
            self._criar_bolha(msg.texto, msg.hora, minha)

        self.chat_mensagens_canvas.update_idletasks()
        self.chat_mensagens_canvas.yview_moveto(1.0)
        self.entrada_chat.focus_set()

    def _render_mensagem(self, m):
        meu_nome = self.sessao.nome if self.sessao else ""
        minha = (m.remetente_nome == meu_nome)
        self._criar_bolha(m.texto, m.enviado_em, minha, msg_id=m.id)

    def _criar_bolha(self, texto: str, hora: str, minha: bool,
                      msg_id: str | None = None):
        linha = tk.Frame(self.chat_mensagens_frame, bg="#F7F9FC")
        linha.pack(fill="x", padx=10, pady=4)
        if msg_id:
            linha.msg_id = msg_id

        if minha:
            bg = "#CFE7FB"
            anchor = "e"
            side = "right"
        else:
            bg = "#F0F0F0"
            anchor = "w"
            side = "left"

        bolha = tk.Frame(linha, bg=bg, relief="flat")
        bolha.pack(side=side, anchor=anchor)

        tk.Label(bolha, text=texto,
                 bg=bg, fg="#1F2933",
                 justify="left", wraplength=420,
                 padx=10, pady=6,
                 font=("Segoe UI", 10)).pack(anchor="w")

        tk.Label(bolha, text=hora,
                 bg=bg, fg="#666666",
                 font=("Segoe UI", 7),
                 padx=10, pady=2).pack(anchor="e")

    def enviar_mensagem_chat(self):
        texto = self.var_mensagem_chat.get().strip()
        if not texto:
            return
        if not self.amigo_chat_ativo:
            messagebox.showinfo("ChatoChat",
                                 "Escolha um amigo antes de enviar uma mensagem.")
            return

        if self.chat_api is not None:
            try:
                msg = self.chat_api.enviar(self.amigo_chat_ativo, texto)
            except ErroChat as e:
                messagebox.showerror("Erro ao enviar", str(e))
                return

            self.var_mensagem_chat.set("")
            self._render_mensagem(msg)
            self._chat_msgs_renderizadas.add(msg.id)
            self._chat_ultimo_id = msg.id

            self.sons.tocar("enviar")

            self.chat_mensagens_canvas.update_idletasks()
            self.chat_mensagens_canvas.yview_moveto(1.0)
            return

        sucesso = self._executar_persistencia(
            lambda: self.repo_chat.adicionar_mensagem(
                self.amigo_chat_ativo, Mensagem.nova("Você", texto)),
            "Erro ao enviar mensagem")
        if sucesso:
            self.var_mensagem_chat.set("")
            self.abrir_conversa_chat(self.amigo_chat_ativo)
            self._atualizar_preview_contato(self.amigo_chat_ativo)

    def _atualizar_preview_contato(self, amigo: str):
        btn = getattr(self, "_botoes_contatos", {}).get(amigo)
        if btn is None:
            return
        conversa = self.repo_chat.obter_conversa(amigo)
        ultima = conversa[-1].texto if conversa else "Comece uma conversa..."
        btn.config(text=f"👤  {amigo}\n{ultima[:27]}")

    # ==========================================================
    # AMIZADES — ações em modo API
    # ==========================================================
    def _menu_contexto_amigo(self, event, amigo: Amigo):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(
            label=f"Desfazer amizade com {amigo.nome}",
            command=lambda: self._desfazer_amizade(amigo))
        menu.tk_popup(event.x_root, event.y_root)

    def _desfazer_amizade(self, amigo: Amigo):
        if not messagebox.askyesno(
            "Desfazer amizade",
            f"Tem certeza que deseja desfazer a amizade com {amigo.nome}?"
        ):
            return
        try:
            self.amizades_api.desfazer(amigo.amizade_id)
        except ErroAmizade as e:
            messagebox.showerror("Erro", str(e))
            return
        self.montar_tela_chatochat()

    def _abrir_dialogo_adicionar_amigo(self):
        nome = simpledialog.askstring("Adicionar amigo",
                                       "Digite o nome do usuário:",
                                       parent=self.root)
        if not nome:
            return
        nome = nome.strip()
        if not nome:
            return

        try:
            self.amizades_api.enviar_pedido(nome)
        except ErroAmizade as e:
            messagebox.showerror("Erro", str(e), parent=self.root)
            return

        messagebox.showinfo("Pedido enviado",
                            f"Pedido de amizade enviado para '{nome}'.",
                            parent=self.root)

    def _abrir_pedidos_pendentes(self):
        try:
            pendentes = self.amizades_api.listar_pendentes()
        except ErroAmizade as e:
            messagebox.showerror("Erro", str(e))
            return

        janela = tk.Toplevel(self.root)
        janela.title("Pedidos de amizade")
        janela.geometry("480x420")
        janela.configure(bg="#F0F4F8")
        janela.transient(self.root)
        janela.grab_set()

        corpo = ttk.Frame(janela, padding=18)
        corpo.pack(fill="both", expand=True)

        ttk.Label(corpo, text="📬 Pedidos de amizade",
                  font=("Segoe UI", 15, "bold"),
                  foreground="#003366").pack(anchor="w")
        ttk.Label(corpo, text="Aceite ou recuse quem quer ser seu amigo",
                  font=("Segoe UI", 9, "italic"),
                  foreground="#666666").pack(anchor="w", pady=(2, 14))

        if not pendentes:
            ttk.Label(corpo, text="Nenhum pedido pendente.",
                      foreground="#888888",
                      font=("Segoe UI", 10)).pack(pady=40)
            ttk.Button(corpo, text="Fechar",
                       command=janela.destroy).pack()
            return

        frame_lista = ttk.Frame(corpo, relief="sunken", borderwidth=1)
        frame_lista.pack(fill="both", expand=True)

        canvas = tk.Canvas(frame_lista, bg="#FFFFFF", highlightthickness=0)
        scroll = ttk.Scrollbar(frame_lista, orient="vertical", command=canvas.yview)
        interior = ttk.Frame(canvas)
        interior.bind("<Configure>",
                      lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=interior, anchor="nw", width=420)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        def recarregar():
            janela.destroy()
            self._abrir_pedidos_pendentes()

        for p in pendentes:
            linha = ttk.Frame(interior, padding=10)
            linha.pack(fill="x", padx=6, pady=4)

            info = ttk.Frame(linha)
            info.pack(side="left", fill="x", expand=True)
            ttk.Label(info, text=f"👤  {p.nome}",
                      font=("Segoe UI", 11, "bold")).pack(anchor="w")
            ttk.Label(info, text=f"Enviado em {p.criado_em}",
                      font=("Segoe UI", 8, "italic"),
                      foreground="#888888").pack(anchor="w")

            def aceitar(aid=p.amizade_id):
                try:
                    self.amizades_api.aceitar(aid)
                except ErroAmizade as e:
                    messagebox.showerror("Erro", str(e))
                    return
                recarregar()

            def recusar(aid=p.amizade_id):
                try:
                    self.amizades_api.recusar(aid)
                except ErroAmizade as e:
                    messagebox.showerror("Erro", str(e))
                    return
                recarregar()

            ttk.Button(linha, text="Aceitar",
                       command=aceitar).pack(side="right", padx=3)
            ttk.Button(linha, text="Recusar",
                       command=recusar).pack(side="right", padx=3)

        ttk.Button(corpo, text="Fechar",
                   command=janela.destroy).pack(pady=(14, 0))


# ==========================================================
# COMPOSITION ROOT
# ==========================================================
if __name__ == "__main__":
    from repositories import (
        RepositorioProgresso, RepositorioReviews, RepositorioChat,
        RepositorioPerfis, RepositorioCatalogo,
    )
    from repositories_api import RepositorioReviewsAPI
    from tela_splash import SplashScreen

    # ---------- Pastas (funciona em dev e em .exe) ----------
    base_dir = _pasta_dados()
    MODO = "api"
    API_URL = os.environ.get(
        "SOPHIA_API_URL",
        "https://sophia-api-lzwc.onrender.com",
    )

    # ---------- Repositórios ----------
    repo_progresso = RepositorioProgresso(
        os.path.join(base_dir, "progresso.json"))
    repo_chat = RepositorioChat(
        os.path.join(base_dir, "chatochat.json"), modo_demo=True)
    repo_perfis = RepositorioPerfis(
        os.path.join(base_dir, "perfis.json"))
    repo_catalogo = RepositorioCatalogo(
        os.path.join(_pasta_recursos(), "catalogo", "catalogo.json"))

    if MODO == "api":
        repo_reviews = RepositorioReviewsAPI(API_URL)
    else:
        repo_reviews = RepositorioReviews(
            os.path.join(base_dir, "reviews.json"))

    root = tk.Tk()
    root.title("Sophia")
    root.geometry("1024x768")
    root.withdraw()  # esconde até o splash terminar

    def iniciar_app(sessao=None, modo_offline=False):
        modo_final = "local" if modo_offline else MODO
        root.deiconify()
        root.lift()
        root.focus_force()
        return SophiaApp(
            root, repo_progresso, repo_reviews, repo_chat,
            repo_perfis, repo_catalogo,
            modo=modo_final, sessao=sessao,
        )

    # ---------- Splash ----------
    splash = SplashScreen(root, api_url=API_URL)
    resultado = splash.executar()

    if resultado == "cancelado":
        root.destroy()
        raise SystemExit(0)

    if resultado == "offline":
        print("[Sophia] Iniciando em modo offline")
        root.deiconify()
        iniciar_app(sessao=None, modo_offline=True)

    else:  # "online" — fluxo normal de login / sessão
        auth_api = RepositorioAuthAPI(API_URL)
        sessao_mgr = GerenciadorSessao(
            os.path.join(base_dir, "session.json"))

        sessao_salva = sessao_mgr.carregar()
        if sessao_salva is not None:
            try:
                r = requests.get(
                    f"{API_URL}/auth/eu",
                    headers={"Authorization": f"Bearer {sessao_salva.token}"},
                    timeout=5)
                if r.status_code == 200:
                    # ---------- Sincroniza perfil antes de abrir ----------
                    try:
                        from perfis_api import RepositorioPerfisAPI
                        api_p = RepositorioPerfisAPI(
                            API_URL, token=sessao_salva.token)
                        p_remoto = api_p.obter(sessao_salva.nome)
                        if p_remoto is None:
                            p_remoto = api_p.criar(sessao_salva.nome)

                        perfil_local = repo_perfis.obter(sessao_salva.nome)
                        if perfil_local is None:
                            repo_perfis.criar(sessao_salva.nome)
                            perfil_local = repo_perfis.obter(sessao_salva.nome)

                        if perfil_local and p_remoto:
                            perfil_local.bio = p_remoto.bio
                            perfil_local.foto_path = p_remoto.foto_path
                            perfil_local.favoritos = list(p_remoto.favoritos)
                            repo_perfis.atualizar(perfil_local)
                            repo_perfis.definir_ativo(sessao_salva.nome)
                            print(f"[perfil-sync] startup OK: {p_remoto.nome}")
                    except Exception as e:
                        print(f"[perfil-sync] startup erro: {e}")

                    root.deiconify()
                    iniciar_app(sessao=sessao_salva)
                else:
                    sessao_mgr.limpar()
                    sessao_salva = None
            except Exception:
                sessao_salva = None

        if sessao_salva is None:
            root.deiconify()

            def apos_login(sessao):
                # Sincronizar perfil com o servidor
                try:
                    from perfis_api import RepositorioPerfisAPI
                    api_perfis = RepositorioPerfisAPI(
                        API_URL, token=sessao.token)

                    p_remoto = api_perfis.obter(sessao.nome)
                    if p_remoto is None:
                        print("[perfil-sync] criando perfil no servidor")
                        p_remoto = api_perfis.criar(sessao.nome)

                    perfil_local = repo_perfis.obter(sessao.nome)
                    if perfil_local is None:
                        repo_perfis.criar(sessao.nome)
                        perfil_local = repo_perfis.obter(sessao.nome)

                    if perfil_local and p_remoto:
                        perfil_local.bio = p_remoto.bio
                        perfil_local.foto_path = p_remoto.foto_path
                        perfil_local.favoritos = list(p_remoto.favoritos)
                        repo_perfis.atualizar(perfil_local)
                        print("[perfil-sync] OK: " + p_remoto.nome)
                        repo_perfis.definir_ativo(sessao.nome)
                except Exception as e:
                    print("[perfil-sync] erro: " + str(e))

                try:
                    tela.destruir()
                except Exception as e:
                    print(f"[apos_login] tela.destruir() falhou (ignorando): {e}")
                iniciar_app(sessao=sessao)

            tela = TelaLogin(root, auth_api, sessao_mgr, apos_login)

    root.mainloop()