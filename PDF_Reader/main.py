"""MangaReader 2000 — Retro Edition.

Ponto de entrada da aplicação. Toda a lógica de UI e navegação vive aqui.
A persistência é delegada a repositórios recebidos por injeção de dependência
(ver composition root no final do arquivo).
"""
from __future__ import annotations

import datetime
import gc
import os
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

import pymupdf as fitz
from PIL import Image, ImageTk

from gerenciador_downloads import GerenciadorDownloads, Callbacks

from models import Review, Mensagem, Perfil, CatalogoItem
from repositories import (
    CatalogoRepositoryProtocol,
    ChatRepositoryProtocol,
    ErroPersistencia,
    PerfisRepositoryProtocol,
    ProgressoRepositoryProtocol,
    ReviewsRepositoryProtocol,
)

class MangaReaderRetro:
    def __init__(
        self,
        root: tk.Tk,
        repo_progresso: ProgressoRepositoryProtocol,
        repo_reviews: ReviewsRepositoryProtocol,
        repo_chat: ChatRepositoryProtocol,
        repo_perfis: PerfisRepositoryProtocol,
        repo_catalogo: CatalogoRepositoryProtocol,
    ):
        self.root = root
        self.root.title("MangaReader 2000")
        self.root.geometry("1024x768")
        self.root.configure(bg="#F0F4F8")

        self.icones_toolbar = {}
        self.capas_memoria = []

        # ---------- ESTILO ----------
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

        # ---------- REPOSITÓRIOS ----------
        self.repo_progresso = repo_progresso
        self.repo_reviews = repo_reviews
        self.repo_chat = repo_chat
        self.repo_perfis = repo_perfis
        self.repo_catalogo = repo_catalogo

        # Caminho da pasta de PDFs (usado pelo gerenciador e pelo catálogo)
        self.pasta_pdf = os.path.join(os.path.dirname(__file__), "pdf_padrao")

        # Gerenciador de downloads em background
        self.gerenciador = GerenciadorDownloads(self.root, self.pasta_pdf)

        # Referências aos cards do catálogo (para atualizar a UI durante o download)
        self._cards_catalogo: dict[str, dict] = {}

        # ---------- ESTADO ----------
        self.doc = None
        self.caminho_pdf_atual: str | None = None
        self.obra_selecionada: str | None = None
        self.pagina_atual = 0
        self.total_paginas = 0
        self.amigo_chat_ativo: str | None = None
        self._resize_after_id: str | None = None

        # ---------- SCROLL ROUTER ----------
        self.root.bind_all("<MouseWheel>", self._rotear_scroll_canvas)
        self.root.bind_all("<Button-4>", self._scroll_linux_cima)
        self.root.bind_all("<Button-5>", self._scroll_linux_baixo)

        # ---------- MENU / TOOLBAR / CONTAINER ----------
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

        self.montar_tela_leitor()
        self.mostrar_tela_inicio()

        self.root.bind("<Left>", lambda e: self.pagina_anterior())
        self.root.bind("<Right>", lambda e: self.proxima_pagina())

    # ==========================================================
    # PERSISTÊNCIA — helper
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
        m_arquivo.add_command(label="Abrir PDF Externo...", command=self.abrir_pdf_externo)
        m_arquivo.add_separator()
        m_arquivo.add_command(label="Sair", command=self.root.quit)
        barra.add_cascade(label="Arquivo", menu=m_arquivo)

        m_biblioteca = tk.Menu(barra, tearoff=0)
        m_biblioteca.add_command(label="Ver Obras", command=self.mostrar_tela_obras)
        barra.add_cascade(label="Biblioteca", menu=m_biblioteca)

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
        canvas = self._canvas_sob_mouse(event)
        if canvas is None:
            return
        delta = getattr(event, "delta", 0)
        if not delta:
            return
        unidades = int(-delta / 120)
        if unidades == 0:
            unidades = -1 if delta > 0 else 1
        try:
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
        """Carrega imagem da pasta assets/icones."""
        caminho = os.path.join(os.path.dirname(__file__), "assets", "icones", nome_arquivo)
        return self.carregar_imagem(caminho, tamanho, chave_cache=nome_arquivo)

    def carregar_imagem(self, caminho: str, tamanho: tuple, chave_cache: str | None = None):
        """Carrega imagem de qualquer caminho. Retorna None se não existir/der erro."""
        if not caminho or not os.path.exists(caminho):
            return None
        try:
            img = Image.open(caminho).resize(tamanho, Image.Resampling.LANCZOS)
            tk_img = ImageTk.PhotoImage(img)
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

    # ==========================================================
    # NAVEGAÇÃO
    # ==========================================================
    def _esconder_todas(self, manter: tk.Frame | None = None):
        for tela in (self.frame_inicio, self.frame_obras, self.frame_volumes,
                     self.frame_leitor, self.frame_perfil, self.frame_reviews,
                     self.frame_chatochat, self.frame_catalogo):
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
        self._montar_conteudo_perfil()

    # ==========================================================
    # TELA: INÍCIO (inalterada)
    # ==========================================================
    def _montar_conteudo_inicio(self):
        for w in self.frame_inicio.winfo_children():
            w.destroy()

        hora = datetime.datetime.now().hour
        saudacao = "Bom dia" if hora < 12 else ("Boa tarde" if hora < 18 else "Boa noite")

        banner = ttk.Frame(self.frame_inicio, style="Banner.TFrame", padding=20)
        banner.pack(fill="x", padx=15, pady=15)
        tk.Label(banner, text=f"{saudacao}! 📖 MangaReader 2000 — Retrô Edition",
                 font=("Segoe UI", 16, "bold"), fg="#FFFFFF",
                 bg="#003366").pack(anchor="w")
        tk.Label(banner, text="Seu leitor de mangás, quadrinhos e PDFs",
                 font=("Segoe UI", 10), fg="#D0E3F7",
                 bg="#003366").pack(anchor="w", pady=(5, 0))

        rodape = (
            '"Só existem dois dias no ano que nada pode ser feito. Um se chama ontem '
            'e o outro se chama amanhã, portanto hoje é o dia certo para amar, '
            'acreditar, fazer e principalmente viver." - Dalai Lama\n\n'
            '~Programa feito por Chumbinho~'
        )
        ttk.Label(self.frame_inicio, text=rodape, font=("Segoe UI", 9, "italic"),
                  justify="center", foreground="#555555",
                  background="#F0F4F8").pack(side="bottom", pady=15)

        main = ttk.Frame(self.frame_inicio, relief="ridge", padding=15)
        main.pack(expand=True, fill="both", padx=15, pady=(0, 5))

        box_sobre = ttk.LabelFrame(main, text=" 🎯 Sobre o Projeto ", padding=12)
        box_sobre.pack(fill="x", expand=False, padx=5, pady=(0, 10))
        ttk.Label(box_sobre, text=(
            "Esta aplicação foi desenvolvida em Python como um projeto de estudo e "
            "portfólio de Engenharia de Software.\n"
            "Combina uma interface gráfica inspirada na era Windows XP (RETRÔ) com "
            "técnicas modernas de renderização vetorial e gerenciamento de memória "
            "em tempo real.\n"
            "Essa aplicação foi criada com o intuito de difundir obras e incentivar "
            "a leitura, além de oferecer um ambiente agradável para que os usuários "
            "possam postar suas avaliações, se expressar e, principalmente, se divertir!\n"
        ), wraplength=850, justify="left").pack(anchor="w", fill="x", expand=True)

        box_recursos = ttk.LabelFrame(main, text=" ✨ Principais Funcionalidades ", padding=12)
        box_recursos.pack(fill="x", expand=False, padx=5, pady=5)
        box_recursos.columnconfigure(1, weight=1)

        recursos = [
            (" Interface Aero / Retrô:",
             "Design clássico com botões estilizados, sombras e paleta suave em Segoe UI."),
            (" Coleção em 3 Níveis:",
             "Organização automática por Obras, Seletor de Volumes e Leitor Canvas integrado."),
            (" High Performance Matrix:",
             "Renderização direta via PyMuPDF (fitz.Matrix), garantindo imagens ultra "
             "nítidas sem travamentos."),
            (" Memória de Leitura & Status:",
             "Salva a página exata onde você parou em arquivo JSON local e permite "
             "marcar volumes como lidos (✔)."),
            (" Navegação por Teclado:",
             "Passe as páginas usando as setas direcionais do teclado."),
        ]
        for i, (titulo, desc) in enumerate(recursos):
            ttk.Label(box_recursos, text=titulo, font=("Segoe UI", 9, "bold"),
                      foreground="#003366").grid(row=i, column=0, sticky="w",
                                                  padx=(0, 15), pady=6)
            ttk.Label(box_recursos, text=desc, justify="left").grid(
                row=i, column=1, sticky="ew", pady=6)


    # ==========================================================
    # TELA: CATÁLOGO (obras disponíveis para download)
    # ==========================================================
    def abrir_tela_catalogo(self):
        self._esconder_todas(self.frame_catalogo)
        self.frame_catalogo.pack(expand=True, fill="both")
        self._montar_grid_catalogo()

    # ==========================================================
    # TELA: CATÁLOGO
    # ==========================================================
    def abrir_tela_catalogo(self):
        self._esconder_todas(self.frame_catalogo)
        self.frame_catalogo.pack(expand=True, fill="both")
        self._montar_grid_catalogo()

    def _montar_grid_catalogo(self):
        for w in self.frame_catalogo.winfo_children():
            w.destroy()

        topo = ttk.Frame(self.frame_catalogo, padding=8)
        topo.pack(fill="x")
        ttk.Label(topo, text="Catálogo de Obras",
                  font=("Segoe UI", 12, "bold"),
                  foreground="#003366").pack(side="left", padx=5)
        ttk.Label(topo, text="(obras disponíveis para baixar)",
                  font=("Segoe UI", 9, "italic"),
                  foreground="#555555").pack(side="left", padx=6)

        frame_scroll = ttk.Frame(self.frame_catalogo, relief="ridge")
        frame_scroll.pack(expand=True, fill="both", padx=15, pady=5)

        canvas = tk.Canvas(frame_scroll, bg="#E9EEF4", highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame_scroll, orient="vertical", command=canvas.yview)
        conteudo = ttk.Frame(canvas)

        conteudo.bind("<Configure>",
                      lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=conteudo, anchor="nw",
                             tags="catalogo_conteudo")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure("catalogo_conteudo", width=e.width))

        canvas.pack(side="left", expand=True, fill="both")
        scrollbar.pack(side="right", fill="y")

        itens = self.repo_catalogo.listar()
        if not itens:
            ttk.Label(conteudo,
                      text="O catálogo está vazio.\n\n"
                           "Se você está rodando localmente, verifique se o arquivo "
                           "'catalogo.json' existe na pasta do projeto.",
                      justify="center", font=("Segoe UI", 10),
                      foreground="#555555").pack(pady=40, padx=30)
            return

        grid = ttk.Frame(conteudo)
        grid.pack(expand=True, fill="both", pady=15)

        # limpa referências antigas antes de criar cards novos
        self._cards_catalogo.clear()

        colunas = 3
        for i, item in enumerate(itens):
            linha, coluna = divmod(i, colunas)
            card = ttk.Frame(grid, padding=12, relief="solid", width=200)
            card.grid(row=linha, column=coluna, padx=15, pady=15, sticky="n")
            card.grid_propagate(False)

            tk.Label(card, text="📖", bg="#D0E3F7", fg="#003366",
                     font=("Segoe UI", 32), width=10, height=4
                     ).pack(fill="x")

            ttk.Label(card, text=item.nome,
                      font=("Segoe UI", 10, "bold"),
                      wraplength=170, justify="center").pack(pady=(8, 2))
            if item.autor:
                ttk.Label(card, text=f"por {item.autor}",
                          font=("Segoe UI", 8, "italic"),
                          foreground="#666666").pack()

            qtd_vol = len(item.volumes)
            total_mb = sum(v.tamanho_mb for v in item.volumes)
            ttk.Label(card,
                      text=f"{qtd_vol} vol(s) • {total_mb:.1f} MB",
                      font=("Segoe UI", 8),
                      foreground="#555555").pack(pady=(4, 8))

            # ---- Área de ação (muda entre botão e progresso) ----
            area_acao = ttk.Frame(card)
            area_acao.pack(fill="x")

            # Guarda referência para manipular depois (durante download)
            self._cards_catalogo[item.id] = {
                "item": item,
                "area_acao": area_acao,
            }

            ja_local = os.path.isdir(os.path.join(self.pasta_pdf, item.nome))
            if ja_local:
                self._mostrar_estado_baixado(item.id)
            else:
                self._mostrar_estado_disponivel(item.id)

    # ==========================================================
    # DOWNLOADS — estados do card
    # ==========================================================
    def _mostrar_estado_disponivel(self, item_id: str):
        """Card mostra o botão 'Baixar'."""
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

    def _mostrar_estado_baixando(self, item_id: str):
        """Card mostra barra de progresso + label 'Baixando...'."""
        ref = self._cards_catalogo.get(item_id)
        if ref is None:
            return
        area = ref["area_acao"]
        for w in area.winfo_children():
            w.destroy()

        lbl = ttk.Label(area, text="Baixando...", font=("Segoe UI", 8))
        lbl.pack()

        prog = ttk.Progressbar(area, mode="determinate",
                                maximum=100, length=170)
        prog.pack(fill="x", pady=(2, 0))

        ref["label_progresso"] = lbl
        ref["progressbar"] = prog

    def _mostrar_estado_baixado(self, item_id: str):
        """Card mostra '✔ Já na biblioteca' + botão 'Abrir'."""
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

    # ==========================================================
    # DOWNLOADS — fluxo principal
    # ==========================================================
    def _baixar_item_catalogo(self, item: CatalogoItem):
        """Baixa todos os volumes de uma obra, um após o outro."""
        if not item.volumes:
            messagebox.showwarning("Catálogo",
                                    f"'{item.nome}' não tem volumes para baixar.")
            return
        self._mostrar_estado_baixando(item.id)
        self._baixar_proximo_volume(item, 0)

    def _baixar_proximo_volume(self, item: CatalogoItem, indice: int):
        """Baixa o volume `indice` e, quando terminar, chama o próximo."""
        if indice >= len(item.volumes):
            self._mostrar_estado_baixado(item.id)
            return

        volume = item.volumes[indice]
        chave = f"{item.id}:vol{volume.numero}"
        destino = os.path.join(
            self.pasta_pdf, item.nome, f"{volume.titulo}.pdf"
        )

        total_volumes = len(item.volumes)

        def on_progresso(baixado: int, total: int) -> None:
            ref = self._cards_catalogo.get(item.id)
            if ref is None:
                return
            prog = ref.get("progressbar")
            lbl = ref.get("label_progresso")
            if total > 0 and prog is not None:
                pct = int(baixado * 100 / total)
                prog["value"] = pct
            if lbl is not None:
                if total > 0:
                    mb_b = baixado / (1024 * 1024)
                    mb_t = total / (1024 * 1024)
                    lbl.config(text=f"Vol. {volume.numero}/{total_volumes} — "
                                    f"{mb_b:.1f}/{mb_t:.1f} MB")
                else:
                    lbl.config(text=f"Vol. {volume.numero}/{total_volumes} — "
                                    f"{baixado // 1024} KB")

        def on_concluido() -> None:
            self._baixar_proximo_volume(item, indice + 1)

        def on_erro(mensagem: str) -> None:
            messagebox.showerror(
                "Erro no download",
                f"Falha ao baixar '{volume.titulo}':\n\n{mensagem}",
            )
            self._mostrar_estado_disponivel(item.id)

        def on_cancelado() -> None:
            self._mostrar_estado_disponivel(item.id)

        self.gerenciador.baixar(
            chave=chave,
            url=volume.url,
            destino=destino,
            callbacks=Callbacks(
                on_progresso=on_progresso,
                on_concluido=on_concluido,
                on_erro=on_erro,
                on_cancelado=on_cancelado,
            ),
        )
    # ==========================================================
    # DOWNLOADS — estados do card
    # ==========================================================
    def _mostrar_estado_disponivel(self, item_id: str):
        """Card mostra o botão 'Baixar'."""
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

    def _mostrar_estado_baixando(self, item_id: str):
        """Card mostra barra de progresso + label 'Baixando...'."""
        ref = self._cards_catalogo.get(item_id)
        if ref is None:
            return
        area = ref["area_acao"]
        for w in area.winfo_children():
            w.destroy()

        lbl = ttk.Label(area, text="Baixando...", font=("Segoe UI", 8))
        lbl.pack()

        prog = ttk.Progressbar(area, mode="determinate",
                                maximum=100, length=170)
        prog.pack(fill="x", pady=(2, 0))

        ref["label_progresso"] = lbl
        ref["progressbar"] = prog

    def _mostrar_estado_baixado(self, item_id: str):
        """Card mostra '✔ Já na biblioteca' + botão 'Abrir'."""
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

    # ==========================================================
    # DOWNLOADS — fluxo principal
    # ==========================================================
    def _baixar_item_catalogo(self, item: CatalogoItem):
        """Baixa todos os volumes de uma obra, um após o outro."""
        if not item.volumes:
            messagebox.showwarning("Catálogo",
                                    f"'{item.nome}' não tem volumes para baixar.")
            return
        self._mostrar_estado_baixando(item.id)
        self._baixar_proximo_volume(item, 0)

    def _baixar_proximo_volume(self, item: CatalogoItem, indice: int):
        """Baixa o volume `indice` e, quando terminar, chama o próximo."""
        if indice >= len(item.volumes):
            # Acabaram todos — atualiza o card para 'Baixado'
            self._mostrar_estado_baixado(item.id)
            # Se estiver na tela de Obras, recarrega para a obra aparecer
            return

        volume = item.volumes[indice]
        chave = f"{item.id}:vol{volume.numero}"
        destino = os.path.join(
            self.pasta_pdf, item.nome, f"{volume.titulo}.pdf"
        )

        # Progresso do volume atual no label
        total_volumes = len(item.volumes)

        def on_progresso(baixado: int, total: int) -> None:
            ref = self._cards_catalogo.get(item.id)
            if ref is None:
                return
            prog = ref.get("progressbar")
            lbl = ref.get("label_progresso")
            if total > 0 and prog is not None:
                pct = int(baixado * 100 / total)
                prog["value"] = pct
            if lbl is not None:
                if total > 0:
                    mb_b = baixado / (1024 * 1024)
                    mb_t = total / (1024 * 1024)
                    lbl.config(text=f"Vol. {volume.numero}/{total_volumes} — "
                                    f"{mb_b:.1f}/{mb_t:.1f} MB")
                else:
                    lbl.config(text=f"Vol. {volume.numero}/{total_volumes} — "
                                    f"{baixado // 1024} KB")

        def on_concluido() -> None:
            self._baixar_proximo_volume(item, indice + 1)

        def on_erro(mensagem: str) -> None:
            messagebox.showerror(
                "Erro no download",
                f"Falha ao baixar '{volume.titulo}':\n\n{mensagem}",
            )
            # Volta o card para o estado inicial (permite tentar de novo)
            self._mostrar_estado_disponivel(item.id)

        def on_cancelado() -> None:
            self._mostrar_estado_disponivel(item.id)

        self.gerenciador.baixar(
            chave=chave,
            url=volume.url,
            destino=destino,
            callbacks=Callbacks(
                on_progresso=on_progresso,
                on_concluido=on_concluido,
                on_erro=on_erro,
                on_cancelado=on_cancelado,
            ),
        )

    # ==========================================================
    # TELA: OBRAS (inalterada)
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

        pasta_raiz = os.path.join(os.path.dirname(__file__), "pdf_padrao")
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
            ttk.Label(card, text=f"{len(volumes)} vol(s)",
                      font=("Segoe UI", 8), foreground="#555555").pack()
            i += 1

    # ==========================================================
    # TELA: VOLUMES (inalterada)
    # ==========================================================
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

        caminho_obra = os.path.join(os.path.dirname(__file__), "pdf_padrao", nome_obra)
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
            "Erro ao atualizar status",
        )
        if sucesso and self.obra_selecionada:
            self.mostrar_tela_volumes(self.obra_selecionada)

    # ==========================================================
    # TELA: LEITOR (inalterada)
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

        frame_canvas = ttk.Frame(self.frame_leitor, relief="sunken")
        frame_canvas.pack(expand=True, fill="both", padx=8, pady=8)

        self.canvas = tk.Canvas(frame_canvas, bg="#50555A", highlightthickness=0)
        self.canvas.pack(expand=True, fill="both")

        self._resize_after_id = None
        self.canvas.bind("<Configure>", self._agendar_rerender)

    def _agendar_rerender(self, _event=None):
        if not self.doc:
            return
        if self._resize_after_id is not None:
            try:
                self.root.after_cancel(self._resize_after_id)
            except tk.TclError:
                pass
        self._resize_after_id = self.root.after(150, self.exibir_pagina)

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
            tk_capa = ImageTk.PhotoImage(img)
            self.capas_memoria.append(tk_capa)
            doc_temp.close()
            return tk_capa
        except Exception:
            return None

    def abrir_manga_da_biblioteca(self, caminho_pdf: str):
        self.carregar_documento(caminho_pdf)
        self._esconder_todas(self.frame_leitor)
        self.frame_leitor.pack(expand=True, fill="both")

    def abrir_pdf_externo(self):
        caminho = filedialog.askopenfilename(
            title="Selecione o PDF", filetypes=[("Arquivos PDF", "*.pdf")])
        if caminho:
            self.carregar_documento(caminho)
            self._esconder_todas(self.frame_leitor)
            self.frame_leitor.pack(expand=True, fill="both")

    def pagina_anterior(self):
        if self.doc and self.pagina_atual > 0:
            self.pagina_atual -= 1
            self.registrar_pagina_atual()
            self.exibir_pagina()

    def proxima_pagina(self):
        if self.doc and self.pagina_atual < self.total_paginas - 1:
            self.pagina_atual += 1
            self.registrar_pagina_atual()
            self.exibir_pagina()

    def carregar_documento(self, caminho: str):
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

            gc.collect()
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
        page = self.doc.load_page(self.pagina_atual)

        largura = self.canvas.winfo_width()
        altura = self.canvas.winfo_height()

        if largura > 10 and altura > 10:
            zoom = (altura - 20) / page.rect.height
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        else:
            pix = page.get_pixmap(dpi=100)

        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self.tk_img = ImageTk.PhotoImage(img)

        self.canvas.delete("all")
        self.canvas.create_image(largura // 2, 10, anchor="n", image=self.tk_img)
        self.lbl_status_pagina.config(
            text=f"Página: {self.pagina_atual + 1} / {self.total_paginas}")

    # ==========================================================
    # TELA: PERFIL (reescrita — agora lê do repositório)
    # ==========================================================
    def _montar_conteudo_perfil(self):
        for w in self.frame_perfil.winfo_children():
            w.destroy()

        perfil = self.repo_perfis.ativo()
        if perfil is None:
            # Fallback defensivo — nunca deve acontecer porque o repo sempre
            # cria um "Leitor" na primeira inicialização.
            perfil = Perfil.novo("Leitor")

        canvas_perfil = tk.Canvas(self.frame_perfil, bg="#F0F4F8", highlightthickness=0)
        scroll_perfil = ttk.Scrollbar(self.frame_perfil, orient="vertical",
                                       command=canvas_perfil.yview)
        conteudo = ttk.Frame(canvas_perfil)
        conteudo.bind("<Configure>",
                      lambda e: canvas_perfil.configure(scrollregion=canvas_perfil.bbox("all")))
        canvas_perfil.create_window((0, 0), window=conteudo, anchor="nw", width=910)
        canvas_perfil.configure(yscrollcommand=scroll_perfil.set)
        canvas_perfil.pack(side="left", fill="both", expand=True)
        scroll_perfil.pack(side="right", fill="y")

        # ---------- CABEÇALHO ----------
        cabecalho = ttk.Frame(conteudo, relief="solid", padding=15)
        cabecalho.pack(fill="x", padx=15, pady=10)

        # Foto (do perfil, com fallback para profile1.png, com fallback textual)
        self.img_perfil_grande = None
        if perfil.foto_path:
            self.img_perfil_grande = self.carregar_imagem(perfil.foto_path, (120, 120))
        if self.img_perfil_grande is None:
            self.img_perfil_grande = self.carregar_icone("profile1.png", (120, 120))

        if self.img_perfil_grande:
            tk.Label(cabecalho, image=self.img_perfil_grande).pack(
                side="left", padx=(0, 15))
        else:
            tk.Label(cabecalho, text="(sem foto)", width=15, height=8,
                     bg="#D0E3F7", fg="#003366").pack(side="left", padx=(0, 15))

        textos = ttk.Frame(cabecalho)
        textos.pack(side="left", fill="both", expand=True)

        ttk.Label(textos, text=perfil.nome,
                  font=("Segoe UI", 18, "bold")).pack(anchor="w", pady=(0, 5))

        bio = perfil.bio.strip() or \
              "Sem bio ainda. Clique em 'Editar Perfil' para escrever uma."
        ttk.Label(textos, text=bio, wraplength=500,
                  justify="left").pack(anchor="w")

        ttk.Button(cabecalho, text="✏ Editar Perfil",
                   command=self.abrir_dialogo_editar_perfil).pack(
            side="right", anchor="n")

        # ---------- CORPO: Favoritos + Amigos ----------
        corpo = ttk.Frame(conteudo)
        corpo.pack(fill="x", padx=15, pady=5)

        favoritos = ttk.LabelFrame(corpo, text=" 🌟 Meus 5 Favoritos ", padding=10)
        favoritos.pack(side="left", expand=True, fill="both", padx=(0, 10))

        # Mostra os favoritos do perfil. Se vazios, mostra placeholders.
        nomes_favoritos = perfil.favoritos[:5]
        while len(nomes_favoritos) < 5:
            nomes_favoritos.append("")

        for i, nome_fav in enumerate(nomes_favoritos, start=1):
            col = ttk.Frame(favoritos)
            col.pack(side="left", expand=True, padx=5)
            if nome_fav:
                tk.Button(col, text=nome_fav, bg="#D0E3F7", fg="#003366",
                          relief="flat", width=12, height=7, cursor="hand2",
                          wraplength=90).pack()
                ttk.Label(col, text=f"#{i}",
                          font=("Segoe UI", 8, "bold")).pack(pady=4)
            else:
                tk.Button(col, text="Vazio", bg="#E9EEF4", fg="#888888",
                          relief="flat", width=12, height=7).pack()
                ttk.Label(col, text=f"#{i}",
                          font=("Segoe UI", 8, "bold"),
                          foreground="#AAAAAA").pack(pady=4)

        amigos = ttk.LabelFrame(corpo, text=" 👥 Amigos ", padding=5)
        amigos.pack(side="right", fill="y", padx=(10, 0))

        canvas_amigos = tk.Canvas(amigos, width=160, height=250,
                                   bg="#F0F4F8", highlightthickness=0)
        scroll_amigos = ttk.Scrollbar(amigos, orient="vertical",
                                       command=canvas_amigos.yview)
        lista_amigos = ttk.Frame(canvas_amigos)
        lista_amigos.bind("<Configure>",
                          lambda e: canvas_amigos.configure(
                              scrollregion=canvas_amigos.bbox("all")))
        canvas_amigos.create_window((0, 0), window=lista_amigos, anchor="nw")
        canvas_amigos.configure(yscrollcommand=scroll_amigos.set)
        canvas_amigos.pack(side="left", fill="both", expand=True)
        scroll_amigos.pack(side="right", fill="y")

        for amigo in self.repo_chat.amigos:
            f = ttk.Frame(lista_amigos)
            f.pack(fill="x", pady=2)
            ttk.Label(f, text=f"👤 {amigo}",
                      font=("Segoe UI", 9)).pack(side="left", padx=5)
            tk.Label(f, text="●", fg="#4CAF50", bg="#F0F4F8",
                     font=("Arial", 8)).pack(side="right", padx=5)

        # ---------- MURAL ----------
        mural = ttk.LabelFrame(conteudo, text=" 💬 Mural de Recados ", padding=10)
        mural.pack(fill="x", padx=15, pady=10)

        recados = [
            ("xX_DarkSasuke_Xx", "Que perfil daora! Qual seu mangá favorito dessa lista?"),
            ("LeitoraVoraz", "Passando pra deixar um +rep. Ótimo gosto pra leitura!"),
            ("ChumbinhoFan", "Esse aplicativo tá ficando muito bom, parabéns pelo projeto!"),
            ("NoobMaster69", "Alguém sabe me dizer como passa de página? Brincadeira kkkk"),
        ]
        for autor, msg in recados:
            box = ttk.Frame(mural, relief="groove", padding=8)
            box.pack(fill="x", pady=5)
            ttk.Label(box, text=autor, font=("Segoe UI", 9, "bold"),
                      foreground="#005A9E").pack(anchor="w")
            ttk.Label(box, text=msg, wraplength=820).pack(anchor="w", pady=(3, 0))

    # ==========================================================
    # DIÁLOGO: EDITAR PERFIL
    # ==========================================================
    def abrir_dialogo_editar_perfil(self):
        perfil = self.repo_perfis.ativo()
        if perfil is None:
            return

        janela = tk.Toplevel(self.root)
        janela.title("Editar Perfil")
        janela.geometry("560x500")
        janela.configure(bg="#F0F4F8")
        janela.transient(self.root)
        janela.grab_set()

        corpo = ttk.Frame(janela, padding=18)
        corpo.pack(fill="both", expand=True)

        ttk.Label(corpo, text="Editar Perfil",
                  font=("Segoe UI", 15, "bold"),
                  foreground="#003366").pack(anchor="w", pady=(0, 12))

        # --- Nome (não editável) ---
        ttk.Label(corpo, text="Nome:").pack(anchor="w")
        ttk.Label(corpo, text=perfil.nome,
                  font=("Segoe UI", 10, "bold"),
                  foreground="#005A9E").pack(anchor="w", pady=(2, 2))
        ttk.Label(corpo, text="(o nome identifica o perfil nas reviews e não pode "
                              "ser alterado por enquanto)",
                  font=("Segoe UI", 8, "italic"),
                  foreground="#777777").pack(anchor="w", pady=(0, 12))

        # --- Foto ---
        ttk.Label(corpo, text="Foto de perfil:").pack(anchor="w")
        linha_foto = ttk.Frame(corpo)
        linha_foto.pack(fill="x", pady=(4, 12))

        # Referência para manter a imagem viva (senão o GC apaga)
        foto_ref = {"tk": None}
        lbl_foto = tk.Label(linha_foto, width=10, height=5, bg="#E9EEF4")
        lbl_foto.pack(side="left", padx=(0, 12))

        def atualizar_preview():
            img = None
            if perfil.foto_path:
                img = self.carregar_imagem(perfil.foto_path, (80, 80))
            if img is None:
                img = self.carregar_icone("profile1.png", (80, 80))
            foto_ref["tk"] = img
            if img:
                lbl_foto.config(image=img, text="")
            else:
                lbl_foto.config(image="", text="(sem foto)")

        atualizar_preview()

        def escolher_foto():
            caminho = filedialog.askopenfilename(
                title="Escolha uma foto de perfil",
                filetypes=[
                    ("Imagens", "*.png *.jpg *.jpeg *.gif *.webp"),
                    ("Todos os arquivos", "*.*"),
                ],
                parent=janela,
            )
            if not caminho:
                return
            # Copia para assets/perfis/{id}.{ext} para o perfil ficar autocontido
            base = os.path.dirname(os.path.abspath(__file__))
            pasta = os.path.join(base, "assets", "perfis")
            os.makedirs(pasta, exist_ok=True)

            ext = os.path.splitext(caminho)[1].lower()
            if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                ext = ".png"
            destino = os.path.join(pasta, f"{perfil.id}{ext}")

            try:
                shutil.copy2(caminho, destino)
            except OSError as e:
                messagebox.showerror("Erro",
                                      f"Não foi possível copiar a imagem:\n{e}",
                                      parent=janela)
                return

            perfil.foto_path = destino
            atualizar_preview()

        ttk.Button(linha_foto, text="Escolher Foto...",
                   command=escolher_foto).pack(side="left", anchor="n")

        # --- Bio ---
        ttk.Label(corpo, text="Bio:").pack(anchor="w")
        texto_bio = tk.Text(corpo, height=8, wrap="word",
                            font=("Segoe UI", 10), relief="sunken", bd=2)
        texto_bio.pack(fill="both", expand=True, pady=(3, 12))
        texto_bio.insert("1.0", perfil.bio)

        # --- Botões ---
        def salvar():
            perfil.bio = texto_bio.get("1.0", "end-1c").strip()

            sucesso = self._executar_persistencia(
                lambda: self.repo_perfis.atualizar(perfil),
                "Erro ao salvar perfil",
            )
            if not sucesso:
                return  # mantém janela aberta

            janela.destroy()
            self.abrir_tela_perfil()  # re-renderiza com os dados novos

        botoes = ttk.Frame(corpo)
        botoes.pack(fill="x")
        ttk.Button(botoes, text="Cancelar",
                   command=janela.destroy).pack(side="right", padx=5)
        ttk.Button(botoes, text="Salvar",
                   command=salvar).pack(side="right")

    # ==========================================================
    # TELA: REVIEWS (adaptada para usar repo_perfis)
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
        ttk.Label(faixa, text="Perfil ativo:",
                  font=("Segoe UI", 9, "bold")).pack(side="left")

        self.var_perfil_reviews = tk.StringVar(value=self.repo_perfis.perfil_ativo)
        combo = ttk.Combobox(faixa, textvariable=self.var_perfil_reviews,
                             values=self.repo_perfis.nomes(),
                             state="readonly", width=24)
        combo.pack(side="left", padx=6)
        combo.bind("<<ComboboxSelected>>", self.trocar_perfil_reviews)
        ttk.Button(faixa, text="+ Novo perfil",
                   command=self.criar_perfil_review).pack(side="left", padx=5)

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

        reviews = self.repo_reviews.listar_por_perfil(self.repo_perfis.perfil_ativo)
        if not reviews:
            ttk.Label(interior,
                      text="Este perfil ainda não publicou nenhuma review.\n"
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

    def trocar_perfil_reviews(self, _event=None):
        sucesso = self._executar_persistencia(
            lambda: self.repo_perfis.definir_ativo(self.var_perfil_reviews.get()),
            "Erro ao trocar perfil",
        )
        if sucesso:
            self.atualizar_tela_reviews()

    def criar_perfil_review(self):
        nome = simpledialog.askstring("Novo perfil",
                                       "Digite o nome do novo perfil:",
                                       parent=self.root)
        if not nome:
            return
        if not self.repo_perfis.criar(nome):
            messagebox.showwarning("Perfil existente",
                                    "Já existe um perfil com esse nome.")
            return
        self.atualizar_tela_reviews()

    def formulario_review(self, review_id: str | None = None):
        obras = self.listar_obras_para_review()
        if not obras:
            messagebox.showinfo(
                "Biblioteca vazia",
                "Adicione pelo menos uma obra com arquivos PDF na pasta "
                "pdf_padrao antes de escrever uma review.")
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
        var_obra = tk.StringVar(value=existente.obra if existente else obras[0])
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

            if existente:
                existente.obra = var_obra.get()
                existente.nota = var_nota.get()
                existente.texto = conteudo
                existente.editada_em = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
                acao = lambda: self.repo_reviews.atualizar(existente)
            else:
                nova = Review.nova(self.repo_perfis.perfil_ativo,
                                   var_obra.get(), var_nota.get(), conteudo)
                acao = lambda: self.repo_reviews.adicionar(nova)

            if not self._executar_persistencia(acao, "Erro ao salvar review"):
                return
            janela.destroy()
            self.atualizar_tela_reviews()

        ttk.Button(corpo, text="Salvar Review",
                   command=salvar).pack(anchor="e", pady=(8, 0))

    def listar_obras_para_review(self) -> list[str]:
        pasta = os.path.join(os.path.dirname(__file__), "pdf_padrao")
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
            "Erro ao excluir review",
        )
        if sucesso:
            self.atualizar_tela_reviews()

    # ==========================================================
    # TELA: CHATOCHAT (com correção do preview)
    # ==========================================================
    def montar_tela_chatochat(self):
        for w in self.frame_chatochat.winfo_children():
            w.destroy()

        cabecalho = tk.Frame(self.frame_chatochat, bg="#003366", height=54)
        cabecalho.pack(fill="x")
        cabecalho.pack_propagate(False)
        tk.Label(cabecalho, text="💬 ChatoChat", bg="#003366", fg="white",
                 font=("Segoe UI", 16, "bold")).pack(side="left", padx=16, pady=10)
        tk.Button(cabecalho, text="+ Adicionar amigo",
                  command=self.adicionar_amigo_chat,
                  bg="#DCEBFA", fg="#003366",
                  relief="raised").pack(side="right", padx=12, pady=10)

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
        lista_canvas.create_window((0, 0), window=lista_interna, anchor="nw", width=215)
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
        self.chat_mensagens_canvas.configure(yscrollcommand=barra_msgs.set)
        self.chat_mensagens_canvas.pack(side="left", fill="both", expand=True)
        barra_msgs.pack(side="right", fill="y")

        rodape = ttk.Frame(painel_chat, padding=(0, 8, 0, 0))
        rodape.pack(fill="x")
        self.var_mensagem_chat = tk.StringVar()
        self.entrada_chat = ttk.Entry(rodape, textvariable=self.var_mensagem_chat)
        self.entrada_chat.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entrada_chat.bind("<Return>", lambda e: self.enviar_mensagem_chat())
        ttk.Button(rodape, text="Enviar ➤",
                   command=self.enviar_mensagem_chat).pack(side="right")

        # Guardamos referência aos botões laterais para atualizar o preview
        # sem reconstruir a tela inteira.
        self._botoes_contatos: dict[str, tk.Button] = {}

        for amigo in self.repo_chat.amigos:
            conversa = self.repo_chat.obter_conversa(amigo)
            ultima = conversa[-1].texto if conversa else "Comece uma conversa..."
            btn = tk.Button(lista_interna, text=f"👤  {amigo}\n{ultima[:27]}",
                            anchor="w", justify="left", wraplength=185,
                            bg="#F0F4F8", activebackground="#D0E3F7", relief="groove",
                            padx=8, pady=9,
                            command=lambda a=amigo: self.abrir_conversa_chat(a))
            btn.pack(fill="x", pady=3)
            self._botoes_contatos[amigo] = btn

        if self.amigo_chat_ativo in self.repo_chat.amigos:
            self.abrir_conversa_chat(self.amigo_chat_ativo)

    def _atualizar_preview_contato(self, amigo: str):
        """Atualiza só o botão lateral de um amigo (preview da última msg)."""
        btn = getattr(self, "_botoes_contatos", {}).get(amigo)
        if btn is None:
            return
        conversa = self.repo_chat.obter_conversa(amigo)
        ultima = conversa[-1].texto if conversa else "Comece uma conversa..."
        btn.config(text=f"👤  {amigo}\n{ultima[:27]}")

    def abrir_conversa_chat(self, amigo: str):
        self.amigo_chat_ativo = amigo
        self.chat_titulo.config(text=f"👤  {amigo}")
        for w in self.chat_mensagens_frame.winfo_children():
            w.destroy()

        mensagens = self.repo_chat.obter_conversa(amigo)
        if not mensagens:
            ttk.Label(self.chat_mensagens_frame,
                      text="Esta conversa está vazia. Mande um oi!",
                      foreground="#666666").pack(pady=25, padx=12)

        for msg in mensagens:
            minha = msg.autor == "Você"
            linha = tk.Frame(self.chat_mensagens_frame, bg="#F7F9FC")
            linha.pack(fill="x", padx=10, pady=4)
            tk.Label(linha, text=f"{msg.texto}\n{msg.hora}",
                     justify="left", wraplength=420, padx=10, pady=7,
                     bg="#D7EAFB" if minha else "#FFFFFF",
                     fg="#1F2933", relief="solid", bd=1
                     ).pack(side="right" if minha else "left",
                            anchor="e" if minha else "w")

        self.chat_mensagens_canvas.update_idletasks()
        self.chat_mensagens_canvas.yview_moveto(1.0)
        self.entrada_chat.focus_set()

    def enviar_mensagem_chat(self):
        texto = self.var_mensagem_chat.get().strip()
        if not texto:
            return
        if not self.amigo_chat_ativo:
            messagebox.showinfo("ChatoChat",
                                 "Escolha um amigo antes de enviar uma mensagem.")
            return
        sucesso = self._executar_persistencia(
            lambda: self.repo_chat.adicionar_mensagem(
                self.amigo_chat_ativo, Mensagem.nova("Você", texto)),
            "Erro ao enviar mensagem",
        )
        if sucesso:
            self.var_mensagem_chat.set("")
            self.abrir_conversa_chat(self.amigo_chat_ativo)
            # CORREÇÃO: atualiza o preview lateral sem reconstruir tudo.
            self._atualizar_preview_contato(self.amigo_chat_ativo)

    def adicionar_amigo_chat(self):
        nome = simpledialog.askstring("Adicionar amigo", "Nome do amigo:",
                                       parent=self.root)
        if not nome:
            return
        if not self.repo_chat.adicionar_amigo(nome):
            messagebox.showwarning("ChatoChat", "Esse amigo já está na sua lista.")
            return
        self.amigo_chat_ativo = nome.strip()
        self.montar_tela_chatochat()


# ==========================================================
# COMPOSITION ROOT
# ==========================================================

if __name__ == "__main__":

    from repositories import (
        RepositorioProgresso,
        RepositorioReviews,
        RepositorioChat,
        RepositorioPerfis,
        RepositorioCatalogo,
    )

    base_dir = os.path.dirname(os.path.abspath(__file__))

    repo_progresso = RepositorioProgresso(os.path.join(base_dir, "progresso.json"))
    repo_reviews = RepositorioReviews(os.path.join(base_dir, "reviews.json"))
    repo_chat = RepositorioChat(
        os.path.join(base_dir, "chatochat.json"),
        modo_demo=True,
    )
    repo_perfis = RepositorioPerfis(os.path.join(base_dir, "perfis.json"))
    repo_catalogo = RepositorioCatalogo(os.path.join(base_dir, "catalogo.json"))

    root = tk.Tk()
    app = MangaReaderRetro(
        root,
        repo_progresso,
        repo_reviews,
        repo_chat,
        repo_perfis,
        repo_catalogo,
    )
    root.mainloop()