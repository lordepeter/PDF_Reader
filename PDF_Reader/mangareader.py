import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import pymupdf as fitz
from PIL import Image, ImageTk
import os
import gc
import json
import datetime

class MangaReaderRetro:
    def __init__(self, root):
        self.root = root
        self.root.title("MangaReader 2000")
        self.root.geometry("1024x768")

        # Configura a janela com a cor de fundo padrão do Windows 7
        self.root.configure(bg="#F0F4F8")

        # Guardar referências das imagens para o Garbage Collector não apagar da memória
        self.icones_toolbar = {}

        # ESTILO WINDOWS VISTA / 7
        self.style = ttk.Style()
        temas_disponiveis = self.style.theme_names()
        if 'vista' in temas_disponiveis:
            self.style.theme_use('vista')
        elif 'xpnative' in temas_disponiveis:
            self.style.theme_use('xpnative')

        # Personalização da tipografia Segoe UI (Padrão Windows 7/10)
        self.style.configure(".", font=("Segoe UI", 9), background="#F0F4F8")
        self.style.configure("TLabel", background="#F0F4F8")
        self.style.configure("TLabelframe", background="#F0F4F8")
        self.style.configure("TLabelframe.Label", font=("Segoe UI", 9, "bold"), foreground="#003366")
        self.style.configure("Banner.TFrame", background="#003366")

        # Estado da Aplicação
        self.doc = None
        self.caminho_pdf_atual = None
        self.obra_selecionada = None
        self.pagina_atual = 0
        self.total_paginas = 0
        self.capas_memoria = []

        # Arquivo de Persistência de Progresso
        self.arquivo_progresso = os.path.join(os.path.dirname(__file__), "progresso.json")
        self.progresso = self.carregar_progresso()

        # --- 1. BARRA DE MENU DE TEXTO ---
        self.barra_menu = tk.Menu(self.root, bg="#F0F4F8", fg="#000000")
        
        menu_arquivo = tk.Menu(self.barra_menu, tearoff=0)
        menu_arquivo.add_command(label="Abrir PDF Externo...", command=self.abrir_pdf_externo)
        menu_arquivo.add_separator()
        menu_arquivo.add_command(label="Sair", command=self.root.quit)
        self.barra_menu.add_cascade(label="Arquivo", menu=menu_arquivo)

        menu_biblioteca = tk.Menu(self.barra_menu, tearoff=0)
        menu_biblioteca.add_command(label="Ver Obras", command=self.mostrar_tela_obras)
        self.barra_menu.add_cascade(label="Biblioteca", menu=menu_biblioteca)

        menu_exibir = tk.Menu(self.barra_menu, tearoff=0)
        menu_exibir.add_command(label="Página Inicial", command=self.mostrar_tela_inicio)
        self.barra_menu.add_cascade(label="Exibir", menu=menu_exibir)

        self.root.config(menu=self.barra_menu)

        # --- 2. BARRA DE FERRAMENTAS COM ÍCONES (TOOLBAR RETRÔ) ---
        self.criar_toolbar_icones()

        # --- CONTAINER PRINCIPAL ---
        self.container_principal = ttk.Frame(self.root)
        self.container_principal.pack(expand=True, fill="both")

        # As 4 Telas da Aplicação (Início, Obras, Volumes, Leitor)
        self.frame_inicio = ttk.Frame(self.container_principal)
        self.frame_obras = ttk.Frame(self.container_principal)
        self.frame_volumes = ttk.Frame(self.container_principal)
        self.frame_leitor = ttk.Frame(self.container_principal)
        self.frame_perfil = ttk.Frame(self.container_principal)
        self.frame_reviews = ttk.Frame(self.container_principal)

        # Reviews e perfis locais (persistidos em JSON)
        self.arquivo_reviews = os.path.join(os.path.dirname(__file__), "reviews.json")
        self.dados_reviews = self.carregar_dados_reviews()
        self.perfil_ativo = self.dados_reviews.get("perfil_ativo", "Leitor")

        self.montar_tela_leitor()
        
        # O aplicativo agora inicia na Página Principal!
        self.mostrar_tela_inicio()

        # Atalhos de Teclado
        self.root.bind("<Left>", lambda e: self.pagina_anterior())
        self.root.bind("<Right>", lambda e: self.proxima_pagina())

    # ==========================================
    # 🖼️ TOOLBAR E ÍCONES
    # ==========================================
    def carregar_icone(self, nome_arquivo, tamanho=(20, 20)):
        """Carrega uma imagem da pasta assets/icones e ajusta o tamanho."""
        caminho = os.path.join(os.path.dirname(__file__), "assets", "icones", nome_arquivo)
        
        if os.path.exists(caminho):
            img = Image.open(caminho)
            img = img.resize(tamanho, Image.Resampling.LANCZOS)
            tk_img = ImageTk.PhotoImage(img)
            self.icones_toolbar[nome_arquivo] = tk_img
            return tk_img
        return None

    def criar_toolbar_icones(self):
        """Cria a barra superior de ícones no estilo Windows XP/7."""
        frame_toolbar = ttk.Frame(self.root, padding=(5, 3), relief="groove")
        frame_toolbar.pack(side="top", fill="x")

        # Ícone 1: Voltar ao Início / Home
        img_home = self.carregar_icone("home.png")
        btn_home = tk.Button(
            frame_toolbar,
            image=img_home,
            text=" Início",
            compound="left",
            command=self.mostrar_tela_inicio,
            relief="flat",
            bd=1,
            padx=4,
            pady=2,
            bg="#F0F4F8",
            activebackground="#D0E3F7"
        )
        btn_home.pack(side="left", padx=2)

        ttk.Separator(frame_toolbar, orient="vertical").pack(side="left", fill="y", padx=5)

        # Ícone 2: Perfil do Usuário
        img_perfil = self.carregar_icone("profile.png")
        btn_perfil = tk.Button(
            frame_toolbar,
            image=img_perfil,
            text=" Perfil",
            compound="left",
            command=self.abrir_tela_perfil,
            relief="flat",
            bd=1,
            padx=4,
            pady=2,
            bg="#F0F4F8",
            activebackground="#D0E3F7"
        )
        btn_perfil.pack(side="left", padx=2)

        # Ícone 3: Reviews Feitas
        img_reviews = self.carregar_icone("reviews.png")
        btn_reviews = tk.Button(
            frame_toolbar,
            image=img_reviews,
            text=" Minhas Reviews",
            compound="left",
            command=self.abrir_tela_reviews,
            relief="flat",
            bd=1,
            padx=4,
            pady=2,
            bg="#F0F4F8",
            activebackground="#D0E3F7"
        )
        btn_reviews.pack(side="left", padx=2)

        # Ícone 4: Lista de Amigos
        img_amigos = self.carregar_icone("friendlist.png")
        btn_amigos = tk.Button(
            frame_toolbar,
            image=img_amigos,
            text=" Amigos",
            compound="left",
            command=self.abrir_tela_amigos,
            relief="flat",
            bd=1,
            padx=4,
            pady=2,
            bg="#F0F4F8",
            activebackground="#D0E3F7"
        )
        btn_amigos.pack(side="left", padx=2)

    def abrir_tela_perfil(self):
        self.frame_inicio.pack_forget()
        self.frame_obras.pack_forget()
        self.frame_volumes.pack_forget()
        self.frame_leitor.pack_forget()
        self.frame_reviews.pack_forget()
        self.frame_perfil.pack(expand=True, fill="both")

# --- LÓGICA DO SCROLL GERAL DA TELA DE PERFIL ---
        def rolar_perfil_geral(event):
            try:
                if canvas_perfil.winfo_ismapped():
                    x, y = event.x_root, event.y_root
                    
                    # Coordenadas da caixa de amigos (para não conflitar)
                    x_amigos = canvas_amigos.winfo_rootx()
                    y_amigos = canvas_amigos.winfo_rooty()
                    w_amigos = x_amigos + canvas_amigos.winfo_width()
                    h_amigos = y_amigos + canvas_amigos.winfo_height()
                    mouse_nos_amigos = (x_amigos <= x <= w_amigos and y_amigos <= y <= h_amigos)

                    # Coordenadas gerais do Canvas de Perfil
                    x1 = canvas_perfil.winfo_rootx()
                    y1 = canvas_perfil.winfo_rooty()
                    x2 = x1 + canvas_perfil.winfo_width()
                    y2 = y1 + canvas_perfil.winfo_height()

                    # Se o mouse estiver dentro do perfil e FORA da caixinha de amigos:
                    if x1 <= x <= x2 and y1 <= y <= y2 and not mouse_nos_amigos:
                        canvas_perfil.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        self.root.bind_all("<MouseWheel>", rolar_perfil_geral, add="+")
        # -----------------------------------------------

        def rolar_inicio(event):
            try:
                widget_sob_mouse = event.widget.winfo_containing(event.x_root, event.y_root)
                

                if widget_sob_mouse and str(widget_sob_mouse).startswith(str(self.frame_perfil)):
                    canvas_info.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        # O parâmetro add="+" é fundamental aqui. Ele soma essa rolagem à rolagem 
        # dos amigos, evitando que uma apague a outra da memória do aplicativo.
        self.root.bind_all("<MouseWheel>", rolar_inicio, add="+")


        for widget in self.frame_perfil.winfo_children():
            widget.destroy()

        # 1. Criação do Canvas Master e Scrollbar para a tela INTEIRA
        canvas_perfil = tk.Canvas(self.frame_perfil, bg="#F0F4F8", highlightthickness=0)
        scroll_perfil = ttk.Scrollbar(self.frame_perfil, orient="vertical", command=canvas_perfil.yview)
        
        # 2. O Frame que vai segurar TUDO dentro do Canvas
        frame_conteudo_perfil = ttk.Frame(canvas_perfil)
        
        frame_conteudo_perfil.bind("<Configure>", lambda e: canvas_perfil.configure(scrollregion=canvas_perfil.bbox("all")))
        
        # O parâmetro width=910 trava a largura do conteúdo para caber na sua tela sem barra horizontal
        canvas_perfil.create_window((0, 0), window=frame_conteudo_perfil, anchor="nw", width=910) 
        canvas_perfil.configure(yscrollcommand=scroll_perfil.set)

        canvas_perfil.pack(side="left", fill="both", expand=True)
        scroll_perfil.pack(side="right", fill="y")

        # ==========================================
        # MONTAGEM DOS BLOCOS DENTRO DE 'frame_conteudo_perfil'
        # ==========================================

        # BLOCO 1: CABEÇALHO
        frame_cabecalho = ttk.Frame(frame_conteudo_perfil, relief="solid", padding=15)
        frame_cabecalho.pack(fill="x", padx=15, pady=10)
        
        # 1. FOTO: Salva a imagem no 'self' e coloca dentro do frame_cabecalho
        self.img_perfil_grande = self.carregar_icone("profile1.png", (120, 120))
        lbl_foto = tk.Label(frame_cabecalho, image=self.img_perfil_grande)
        lbl_foto.pack(side="left", padx=(0, 15)) # padx=(0, 15) dá um espaço apenas na direita da foto

        # 2. CAIXA DE TEXTOS: Uma nova caixa (Frame) só para agrupar o Nome e a Bio
        frame_textos_bio = ttk.Frame(frame_cabecalho)
        frame_textos_bio.pack(side="left", fill="both", expand=True)
        
        # 3. TEXTOS: Adicionamos os Labels DENTRO do frame_textos_bio
        lbl_nome = ttk.Label(frame_textos_bio, text="Seu Nome Aqui", font=("Segoe UI", 18, "bold"))
        lbl_nome.pack(anchor="w", pady=(0, 5)) # anchor="w" alinha o texto à esquerda (West)
        
        texto_exemplo = "Bem-vindo ao meu perfil! Sou um grande fã de obras retrô, mangás de mistério e fantasia. Sempre em busca da próxima grande leitura."
        lbl_bio = ttk.Label(frame_textos_bio, text=texto_exemplo, wraplength=500, justify="left")
        lbl_bio.pack(anchor="w")


        # BLOCO 2: CORPO (Favoritos e Amigos)
        frame_corpo = ttk.Frame(frame_conteudo_perfil)
        frame_corpo.pack(fill="x", padx=15, pady=5)

        frame_favoritos = ttk.LabelFrame(frame_corpo, text=" 🌟 Meus 5 Favoritos ", padding=10)
        frame_favoritos.pack(side="left", expand=True, fill="both", padx=(0, 10))

        # --- PREENCHENDO OS 5 FAVORITOS ---
        for i in range(1, 6):
            # Cria uma coluninha para cada obra
            frame_item = ttk.Frame(frame_favoritos)
            frame_item.pack(side="left", expand=True, padx=5)

            # Simula a capa do mangá (um botão retangular azul)
            btn_capa = tk.Button(
                frame_item,
                text="Selecionar\nObra",
                bg="#D0E3F7",
                fg="#003366",
                relief="flat",
                width=12,
                height=7,
                cursor="hand2"
            )
            btn_capa.pack()

            # Título da obra embaixo da capa
            lbl_titulo = ttk.Label(frame_item, text=f"Top {i}", font=("Segoe UI", 8, "bold"))
            lbl_titulo.pack(pady=4)
        # ----------------------------------

        # --- BLOCO DA LISTA DE AMIGOS COM ROLAGEM PRÓPRIA ---
        frame_amigos = ttk.LabelFrame(frame_corpo, text=" 👥 Amigos ", padding=5)
        frame_amigos.pack(side="right", fill="y", padx=(10, 0))

        # 1. Canvas e Scrollbar restritos ao frame_amigos (height=250 trava a altura)
        canvas_amigos = tk.Canvas(frame_amigos, width=160, height=250, bg="#F0F4F8", highlightthickness=0)
        scroll_amigos = ttk.Scrollbar(frame_amigos, orient="vertical", command=canvas_amigos.yview)
        
        # 2. O frame interno onde os amigos vão de fato morar
        frame_lista_amigos = ttk.Frame(canvas_amigos)
        
        # 3. Lógica que atualiza o tamanho da rolagem quando adicionamos alguém
        frame_lista_amigos.bind(
            "<Configure>", 
            lambda e: canvas_amigos.configure(scrollregion=canvas_amigos.bbox("all"))
        )
        
        canvas_amigos.create_window((0, 0), window=frame_lista_amigos, anchor="nw")
        canvas_amigos.configure(yscrollcommand=scroll_amigos.set)

        canvas_amigos.pack(side="left", fill="both", expand=True)
        scroll_amigos.pack(side="right", fill="y")

    # --- LÓGICA DO SCROLL DOS AMIGOS (POR COORDENADAS) ---
        def rolar_amigos(event):
            try:
                # O winfo_ismapped garante que o scroll só tente rodar se a aba Perfil estiver aberta
                if canvas_amigos.winfo_ismapped():
                    # Coordenadas do mouse
                    x, y = event.x_root, event.y_root
                    
                    # Desenha um "quadrado virtual" do tamanho exato da caixa de amigos
                    x1 = canvas_amigos.winfo_rootx()
                    y1 = canvas_amigos.winfo_rooty()
                    x2 = x1 + canvas_amigos.winfo_width()
                    y2 = y1 + canvas_amigos.winfo_height()
                    
                    # Se o mouse estiver em qualquer lugar (mesmo no branco) dentro desse quadrado:
                    if x1 <= x <= x2 and y1 <= y <= y2:
                        canvas_amigos.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        self.root.bind_all("<MouseWheel>", rolar_amigos)
        # -----------------------------------------------------

        # Observa a bolinha do mouse o tempo todo, mas só rola se passar no teste acima
        self.root.bind_all("<MouseWheel>", rolar_amigos)


        # --- PREENCHENDO COM AMIGOS (Teste) ---
        for i in range(1, 16):
            # Usando uma caixinha para cada amigo para ficar alinhado
            f_amigo = ttk.Frame(frame_lista_amigos)
            f_amigo.pack(fill="x", pady=2)
            
            # (Futuramente você pode trocar o 👤 por self.carregar_icone)
            ttk.Label(f_amigo, text=f"👤 Amigo {i}", font=("Segoe UI", 9)).pack(side="left", padx=5)
            
            # Bolinha verde indicando "Online"
            tk.Label(f_amigo, text="●", fg="#4CAF50", bg="#F0F4F8", font=("Arial", 8)).pack(side="right", padx=5)

        # BLOCO 3: MURAL DE COMENTÁRIOS
        frame_comentarios = ttk.LabelFrame(frame_conteudo_perfil, text=" 💬 Mural de Recados ", padding=10)
        frame_comentarios.pack(fill="x", padx=15, pady=10)

        # Uma lista simulando os recados que virão do banco de dados no futuro
        recados_simulados = [
            ("xX_DarkSasuke_Xx", "Que perfil daora! Qual seu mangá favorito dessa lista?"),
            ("LeitoraVoraz", "Passando pra deixar um +rep. Ótimo gosto pra leitura!"),
            ("ChumbinhoFan", "Esse aplicativo tá ficando muito bom, parabéns pelo projeto!"),
            ("NoobMaster69", "Alguém sabe me dizer como passa de página? Brincadeira kkkk")
        ]

        # Desenhando cada recado na tela
        for autor, mensagem in recados_simulados:
            # A caixinha individual do recado
            box_recado = ttk.Frame(frame_comentarios, relief="groove", padding=8)
            box_recado.pack(fill="x", pady=5)

            # Nome do autor (em negrito e azul estilo link)
            lbl_autor = ttk.Label(
                box_recado, 
                text=autor, 
                font=("Segoe UI", 9, "bold"), 
                foreground="#005A9E"
            )
            lbl_autor.pack(anchor="w")

            # A mensagem logo abaixo (com wraplength para não vazar da tela)
            lbl_texto = ttk.Label(box_recado, text=mensagem, wraplength=820)
            lbl_texto.pack(anchor="w", pady=(3, 0))

    # ==========================================
    # ⭐ REVIEWS E PERFIS LOCAIS
    # ==========================================
    def carregar_dados_reviews(self):
        if os.path.exists(self.arquivo_reviews):
            try:
                with open(self.arquivo_reviews, "r", encoding="utf-8") as arquivo:
                    dados = json.load(arquivo)
                    if isinstance(dados, dict):
                        dados.setdefault("perfis", ["Leitor"])
                        dados.setdefault("reviews", [])
                        dados.setdefault("perfil_ativo", "Leitor")
                        return dados
            except (OSError, json.JSONDecodeError):
                pass
        return {"perfis": ["Leitor"], "perfil_ativo": "Leitor", "reviews": []}

    def salvar_dados_reviews(self):
        try:
            with open(self.arquivo_reviews, "w", encoding="utf-8") as arquivo:
                json.dump(self.dados_reviews, arquivo, ensure_ascii=False, indent=4)
        except OSError as erro:
            messagebox.showerror("Erro ao salvar", f"Não foi possível salvar as reviews:\n{erro}")

    def abrir_tela_reviews(self):
        for tela in (self.frame_inicio, self.frame_obras, self.frame_volumes, self.frame_leitor, self.frame_perfil):
            tela.pack_forget()
        self.frame_reviews.pack(expand=True, fill="both")
        self.atualizar_tela_reviews()

    def atualizar_tela_reviews(self):
        for widget in self.frame_reviews.winfo_children():
            widget.destroy()

        topo = ttk.Frame(self.frame_reviews, padding=12)
        topo.pack(fill="x")
        ttk.Label(topo, text="Diário de Reviews", font=("Segoe UI", 16, "bold"), foreground="#003366").pack(side="left")
        ttk.Button(topo, text="+ Escrever Review", command=self.formulario_review).pack(side="right", padx=5)

        faixa = ttk.Frame(self.frame_reviews, padding=(12, 0, 12, 10))
        faixa.pack(fill="x")
        ttk.Label(faixa, text="Perfil ativo:", font=("Segoe UI", 9, "bold")).pack(side="left")
        self.var_perfil_reviews = tk.StringVar(value=self.perfil_ativo)
        combo = ttk.Combobox(faixa, textvariable=self.var_perfil_reviews, values=self.dados_reviews["perfis"], state="readonly", width=24)
        combo.pack(side="left", padx=6)
        combo.bind("<<ComboboxSelected>>", self.trocar_perfil_reviews)
        ttk.Button(faixa, text="+ Novo perfil", command=self.criar_perfil_review).pack(side="left", padx=5)

        lista = ttk.Frame(self.frame_reviews, padding=(12, 0, 12, 12))
        lista.pack(fill="both", expand=True)
        canvas = tk.Canvas(lista, bg="#E9EEF4", highlightthickness=0)
        barra = ttk.Scrollbar(lista, orient="vertical", command=canvas.yview)
        interior = ttk.Frame(canvas)
        interior.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=interior, anchor="nw", width=900, tags="interior")
        canvas.configure(yscrollcommand=barra.set)
        canvas.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure("interior", width=e.width))

        reviews = [r for r in self.dados_reviews["reviews"] if r.get("perfil") == self.perfil_ativo]
        if not reviews:
            ttk.Label(interior, text="Este perfil ainda não publicou nenhuma review.\nClique em '+ Escrever Review' para começar!", justify="center", font=("Segoe UI", 11), foreground="#555555").pack(pady=45, padx=20)
            return

        reviews.sort(key=lambda r: r.get("data", ""), reverse=True)
        for review in reviews:
            card = ttk.LabelFrame(interior, text=f"  {review.get('obra', 'Obra')}  ", padding=12)
            card.pack(fill="x", padx=12, pady=8)
            estrelas = "★" * int(review.get("nota", 0)) + "☆" * (5 - int(review.get("nota", 0)))
            ttk.Label(card, text=f"{estrelas}   {review.get('nota', 0)}/5", font=("Segoe UI", 12, "bold"), foreground="#B77900").pack(anchor="w")
            ttk.Label(card, text=f"Por {review.get('perfil', 'Leitor')}  •  {review.get('data', '')}", foreground="#555555").pack(anchor="w", pady=(2, 6))
            ttk.Label(card, text=review.get("texto", ""), wraplength=820, justify="left").pack(anchor="w", fill="x")
            botoes = ttk.Frame(card)
            botoes.pack(anchor="e", pady=(8, 0))
            ttk.Button(botoes, text="Editar", command=lambda rid=review["id"]: self.formulario_review(rid)).pack(side="left", padx=3)
            ttk.Button(botoes, text="Excluir", command=lambda rid=review["id"]: self.excluir_review(rid)).pack(side="left", padx=3)

    def trocar_perfil_reviews(self, _event=None):
        self.perfil_ativo = self.var_perfil_reviews.get()
        self.dados_reviews["perfil_ativo"] = self.perfil_ativo
        self.salvar_dados_reviews()
        self.atualizar_tela_reviews()

    def criar_perfil_review(self):
        nome = simpledialog.askstring("Novo perfil", "Digite o nome do novo perfil:", parent=self.root)
        if not nome:
            return
        nome = nome.strip()
        if not nome:
            return
        if any(p.casefold() == nome.casefold() for p in self.dados_reviews["perfis"]):
            messagebox.showwarning("Perfil existente", "Já existe um perfil com esse nome.")
            return
        self.dados_reviews["perfis"].append(nome)
        self.perfil_ativo = nome
        self.dados_reviews["perfil_ativo"] = nome
        self.salvar_dados_reviews()
        self.atualizar_tela_reviews()

    def formulario_review(self, review_id=None):
        obras = self.listar_obras_para_review()
        if not obras:
            messagebox.showinfo("Biblioteca vazia", "Adicione pelo menos uma obra com arquivos PDF na pasta pdf_padrao antes de escrever uma review.")
            return
        existente = next((r for r in self.dados_reviews["reviews"] if r.get("id") == review_id), None)
        janela = tk.Toplevel(self.root)
        janela.title("Editar Review" if existente else "Escrever Review")
        janela.geometry("520x440")
        janela.configure(bg="#F0F4F8")
        janela.transient(self.root)
        janela.grab_set()
        corpo = ttk.Frame(janela, padding=18)
        corpo.pack(fill="both", expand=True)
        ttk.Label(corpo, text="Nova avaliação", font=("Segoe UI", 15, "bold"), foreground="#003366").pack(anchor="w", pady=(0, 12))
        ttk.Label(corpo, text="Obra da biblioteca:").pack(anchor="w")
        var_obra = tk.StringVar(value=existente.get("obra") if existente else obras[0])
        combo_obra = ttk.Combobox(corpo, textvariable=var_obra, values=obras, state="readonly")
        combo_obra.pack(fill="x", pady=(3, 12))
        ttk.Label(corpo, text="Sua nota (1 a 5 estrelas):").pack(anchor="w")
        var_nota = tk.IntVar(value=int(existente.get("nota", 5)) if existente else 5)
        linha_estrelas = ttk.Frame(corpo)
        linha_estrelas.pack(anchor="w", pady=4)
        for n in range(1, 6):
            ttk.Radiobutton(linha_estrelas, text="★" * n, value=n, variable=var_nota).pack(side="left", padx=4)
        ttk.Label(corpo, text="Sua análise:").pack(anchor="w", pady=(10, 0))
        texto = tk.Text(corpo, height=9, wrap="word", font=("Segoe UI", 10), relief="sunken", bd=2)
        texto.pack(fill="both", expand=True, pady=5)
        if existente:
            texto.insert("1.0", existente.get("texto", ""))
        def salvar():
            conteudo = texto.get("1.0", "end-1c").strip()
            if not conteudo:
                messagebox.showwarning("Review vazia", "Escreva sua análise antes de salvar.", parent=janela)
                return
            agora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
            if existente:
                existente.update({"obra": var_obra.get(), "nota": var_nota.get(), "texto": conteudo, "editada_em": agora})
            else:
                import uuid
                self.dados_reviews["reviews"].append({"id": uuid.uuid4().hex, "perfil": self.perfil_ativo, "obra": var_obra.get(), "nota": var_nota.get(), "texto": conteudo, "data": agora})
            self.salvar_dados_reviews()
            janela.destroy()
            self.atualizar_tela_reviews()
        ttk.Button(corpo, text="Salvar Review", command=salvar).pack(anchor="e", pady=(8, 0))

    def listar_obras_para_review(self):
        pasta = os.path.join(os.path.dirname(__file__), "pdf_padrao")
        if not os.path.isdir(pasta):
            return []
        return sorted([nome for nome in os.listdir(pasta) if os.path.isdir(os.path.join(pasta, nome)) and any(arq.lower().endswith(".pdf") for arq in os.listdir(os.path.join(pasta, nome)))])

    def excluir_review(self, review_id):
        if not messagebox.askyesno("Excluir review", "Tem certeza de que deseja excluir esta avaliação?"):
            return
        self.dados_reviews["reviews"] = [r for r in self.dados_reviews["reviews"] if r.get("id") != review_id]
        self.salvar_dados_reviews()
        self.atualizar_tela_reviews()

    def abrir_tela_amigos(self):
        # Garantindo que o botão de amigos também não quebre!
        messagebox.showinfo("Amigos", "Em breve: Caderno e Lista de Amigos!")  


    # ==========================================
    # 🏠 TELA 0: PÁGINA PRINCIPAL (HOME / WELCOME)
    # ==========================================
    def mostrar_tela_inicio(self):
        self.frame_obras.pack_forget()
        self.frame_volumes.pack_forget()
        self.frame_leitor.pack_forget()
        self.frame_perfil.pack_forget()
        self.frame_reviews.pack_forget()
        self.frame_inicio.pack(expand=True, fill="both")

    # --- LÓGICA DO SCROLL DA TELA INICIAL (POR COORDENADAS) ---
        def rolar_inicio(event):
            try:
                # Só executa se a tela inicial estiver sendo exibida
                if canvas_info.winfo_ismapped():
                    x, y = event.x_root, event.y_root
                    
                    x1 = canvas_info.winfo_rootx()
                    y1 = canvas_info.winfo_rooty()
                    x2 = x1 + canvas_info.winfo_width()
                    y2 = y1 + canvas_info.winfo_height()
                    
                    if x1 <= x <= x2 and y1 <= y <= y2:
                        canvas_info.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        # Aqui mantemos o add="+" para ele conviver pacificamente com o scroll dos amigos
        self.root.bind_all("<MouseWheel>", rolar_inicio, add="+")
        # ----------------------------------------------------------    

        # O parâmetro add="+" é fundamental aqui. Ele soma essa rolagem à rolagem 
        # dos amigos, evitando que uma apague a outra da memória do aplicativo.
        self.root.bind_all("<MouseWheel>", rolar_inicio, add="+")


        for widget in self.frame_inicio.winfo_children():
            widget.destroy()

        # Lógica da Saudação Dinâmica
        hora_atual = datetime.datetime.now().hour
        if hora_atual < 12:
            saudacao = "Bom dia"
        elif hora_atual < 18:
            saudacao = "Boa tarde"
        else:
            saudacao = "Boa noite"

        # Banner Superior de Boas-Vindas
        frame_banner = ttk.Frame(self.frame_inicio, style="Banner.TFrame", padding=20)
        frame_banner.pack(fill="x", padx=15, pady=15)

        lbl_boas_vindas = tk.Label(
            frame_banner, 
            text=f"{saudacao}! 📖 MangaReader 2000 — Retrô Edition", 
            font=("Segoe UI", 16, "bold"), 
            fg="#FFFFFF", 
            bg="#003366"
        )
        lbl_boas_vindas.pack(anchor="w")

        lbl_subtitulo = tk.Label(
            frame_banner, 
            text="Seu leitor de mangás, quadrinhos e PDFs", 
            font=("Segoe UI", 10), 
            fg="#D0E3F7", 
            bg="#003366"
        )
        lbl_subtitulo.pack(anchor="w", pady=(5, 0))

        # Frase e Assinatura no Rodapé (Posicionado no fundo da tela)
        texto_rodape = (
            '"Só existem dois dias no ano que nada pode ser feito. Um se chama ontem e o outro se chama amanhã, '
            'portanto hoje é o dia certo para amar, acreditar, fazer e principalmente viver." - Dalai Lama\n\n'
            '~Programa feito por Chumbinho~'
        )
        lbl_rodape = ttk.Label(
            self.frame_inicio, 
            text=texto_rodape, 
            font=("Segoe UI", 9, "italic"), 
            justify="center", 
            foreground="#555555",
            background="#F0F4F8"
        )
        lbl_rodape.pack(side="bottom", pady=15)

        # Painel Central de Apresentação
        frame_main = ttk.Frame(self.frame_inicio, relief="ridge", padding=15)
        frame_main.pack(expand=True, fill="both", padx=15, pady=(0, 5))

        # Seção 1: Sobre o Projeto
        box_sobre = ttk.LabelFrame(frame_main, text=" 🎯 Sobre o Projeto ", padding=12)
        box_sobre.pack(fill="x", expand=False, padx=5, pady=(0, 10))

        lbl_txt_sobre = ttk.Label(
            box_sobre, 
            text="Esta aplicação foi desenvolvida em Python como um projeto de estudo e portfólio de Engenharia de Software.\n"
                 "Combina uma interface gráfica inspirada na era Windows XP (RETRÔ) com técnicas modernas de renderização "
                 "vetorial e gerenciamento de memória em tempo real.\n"
                 "Essa aplicação foi criada com o intuito de difundir obras e incentivar a leitura, além de oferecer "
                 "um ambiente agradável para que os usuários possam postar suas avaliações, se expressar e, principalmente, "
                 "se divertir! \n",
            wraplength=850,
            justify="left"
        )
        lbl_txt_sobre.pack(anchor="w", fill="x", expand=True)

        # Seção 2: Recursos Principais
        box_recursos = ttk.LabelFrame(frame_main, text=" ✨ Principais Funcionalidades ", padding=12)
        box_recursos.pack(fill="x", expand=False, padx=5, pady=5)

        box_recursos.columnconfigure(1, weight=1)

        recursos = [
            (" Interface Aero / Retrô:", "Design clássico com botões estilizados, sombras e paleta suave em Segoe UI."),
            (" Coleção em 3 Níveis:", "Organização automática por Obras, Seletor de Volumes e Leitor Canvas integrado."),
            (" High Performance Matrix:", "Renderização direta via PyMuPDF (fitz.Matrix), garantindo imagens ultra nítidas sem travamentos."),
            (" Memória de Leitura & Status:", "Salva a página exata onde você parou em arquivo JSON local e permite marcar volumes como lidos (✔)."),
            (" Navegação por Teclado:", "Passe as páginas usando as setas direcionais do teclado.")
        ]

        for row_idx, (titulo, desc) in enumerate(recursos):
            lbl_title = ttk.Label(box_recursos, text=titulo, font=("Segoe UI", 9, "bold"), foreground="#003366")
            lbl_title.grid(row=row_idx, column=0, sticky="w", padx=(0, 15), pady=6)

            lbl_desc = ttk.Label(box_recursos, text=desc, justify="left")
            lbl_desc.grid(row=row_idx, column=1, sticky="ew", pady=6)

    # ==========================================
    # 💾 GERENCIAMENTO DE PROGRESSO (JSON)
    # ==========================================
    def carregar_progresso(self):
        if os.path.exists(self.arquivo_progresso):
            try:
                with open(self.arquivo_progresso, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def salvar_progresso_json(self):
        try:
            with open(self.arquivo_progresso, "w", encoding="utf-8") as f:
                json.dump(self.progresso, f, indent=4)
        except Exception as e:
            print(f"Erro ao salvar progresso: {e}")

    def registrar_pagina_atual(self):
        if not self.caminho_pdf_atual:
            return

        e_ultima = (self.pagina_atual >= self.total_paginas - 1)
        concluido_anterior = self.progresso.get(self.caminho_pdf_atual, {}).get("concluido", False)

        self.progresso[self.caminho_pdf_atual] = {
            "ultima_pagina": self.pagina_atual,
            "concluido": concluido_anterior or e_ultima
        }
        self.salvar_progresso_json()

    def alternar_status_lido_manual(self, caminho_vol):
        dados_atuais = self.progresso.get(caminho_vol, {"ultima_pagina": 0, "concluido": False})
        status_novo = not dados_atuais.get("concluido", False)
        
        self.progresso[caminho_vol] = {
            "ultima_pagina": dados_atuais.get("ultima_pagina", 0),
            "concluido": status_novo
        }
        self.salvar_progresso_json()
        
        if self.obra_selecionada:
            self.mostrar_tela_volumes(self.obra_selecionada)

    # ==========================================
    # 📚 TELA 1: NÍVEL GERAL DE OBRAS (Grid Principal)
    # ==========================================
    def mostrar_tela_obras(self):
        self.frame_inicio.pack_forget()
        self.frame_leitor.pack_forget()
        self.frame_volumes.pack_forget()
        self.frame_obras.pack(expand=True, fill="both")

        for widget in self.frame_obras.winfo_children():
            widget.destroy()

        lbl_titulo = ttk.Label(self.frame_obras, text="Biblioteca de Obras", font=("Segoe UI", 12, "bold"), foreground="#003366")
        lbl_titulo.pack(anchor="w", padx=15, pady=10)

        frame_scroll = ttk.Frame(self.frame_obras, relief="ridge")
        frame_scroll.pack(expand=True, fill="both", padx=15, pady=5)

        canvas_grid = tk.Canvas(frame_scroll, bg="#E9EEF4", highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame_scroll, orient="vertical", command=canvas_grid.yview)
        frame_conteudo = ttk.Frame(canvas_grid)

        frame_conteudo.bind("<Configure>", lambda e: canvas_grid.configure(scrollregion=canvas_grid.bbox("all")))
        canvas_grid.create_window((0, 0), window=frame_conteudo, anchor="nw")
        canvas_grid.configure(yscrollcommand=scrollbar.set)

        canvas_grid.pack(side="left", expand=True, fill="both")
        scrollbar.pack(side="right", fill="y")

        self.capas_memoria.clear()
        pasta_raiz = os.path.join(os.path.dirname(__file__), "pdf_padrao")

        if not os.path.exists(pasta_raiz):
            ttk.Label(frame_conteudo, text="A pasta 'pdf_padrao' não foi encontrada.").pack(padx=20, pady=20)
            return

        obras = [d for d in os.listdir(pasta_raiz) if os.path.isdir(os.path.join(pasta_raiz, d))]

        if not obras:
            ttk.Label(frame_conteudo, text="Nenhuma obra encontrada.").pack(padx=20, pady=20)
            return

        coluna_max = 4
        i = 0
        for obra in obras:
            caminho_obra = os.path.join(pasta_raiz, obra)
            volumes = [f for f in os.listdir(caminho_obra) if f.lower().endswith(".pdf")]

            if not volumes:
                continue

            primeiro_vol = os.path.join(caminho_obra, volumes[0])
            tk_capa = self.gerar_capa_miniatura(primeiro_vol)

            linha = i // coluna_max
            coluna = i % coluna_max

            frame_card = ttk.Frame(frame_conteudo, padding=10, relief="solid")
            frame_card.grid(row=linha, column=coluna, padx=15, pady=15)

            if tk_capa:
                btn_capa = tk.Button(
                    frame_card, 
                    image=tk_capa, 
                    command=lambda o=obra: self.mostrar_tela_volumes(o),
                    relief="flat",
                    bd=1,
                    bg="#FFFFFF",
                    activebackground="#D0E3F7"
                )
                btn_capa.pack()

            lbl_obra = ttk.Label(frame_card, text=obra, font=("Segoe UI", 9, "bold"))
            lbl_obra.pack(pady=4)

            lbl_qtd = ttk.Label(frame_card, text=f"{len(volumes)} vol(s)", font=("Segoe UI", 8), foreground="#555555")
            lbl_qtd.pack()

            i += 1

    # ==========================================
    # 📖 TELA 2: VOLUMES DA OBRA SELECIONADA
    # ==========================================
    def mostrar_tela_volumes(self, nome_obra):
        self.obra_selecionada = nome_obra
        self.frame_inicio.pack_forget()
        self.frame_obras.pack_forget()
        self.frame_leitor.pack_forget()
        self.frame_perfil.pack_forget()
        self.frame_reviews.pack_forget()
        self.frame_volumes.pack(expand=True, fill="both")

        for widget in self.frame_volumes.winfo_children():
            widget.destroy()

        frame_topo = ttk.Frame(self.frame_volumes, padding=8)
        frame_topo.pack(fill="x")

        btn_voltar = ttk.Button(frame_topo, text="◄ Voltar para Obras", command=self.mostrar_tela_obras)
        btn_voltar.pack(side="left", padx=5)

        lbl_titulo = ttk.Label(frame_topo, text=f"Obra: {nome_obra}", font=("Segoe UI", 11, "bold"), foreground="#003366")
        lbl_titulo.pack(side="left", padx=15)

        frame_scroll = ttk.Frame(self.frame_volumes, relief="ridge")
        frame_scroll.pack(expand=True, fill="both", padx=15, pady=5)

        canvas_grid = tk.Canvas(frame_scroll, bg="#E9EEF4", highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame_scroll, orient="vertical", command=canvas_grid.yview)
        frame_conteudo = ttk.Frame(canvas_grid)

        frame_conteudo.bind("<Configure>", lambda e: canvas_grid.configure(scrollregion=canvas_grid.bbox("all")))
        canvas_grid.create_window((0, 0), window=frame_conteudo, anchor="nw")
        canvas_grid.configure(yscrollcommand=scrollbar.set)

        canvas_grid.pack(side="left", expand=True, fill="both")
        scrollbar.pack(side="right", fill="y")

        caminho_obra = os.path.join(os.path.dirname(__file__), "pdf_padrao", nome_obra)
        volumes = [f for f in os.listdir(caminho_obra) if f.lower().endswith(".pdf")]

        coluna_max = 4
        for idx, vol in enumerate(volumes):
            caminho_vol = os.path.join(caminho_obra, vol)
            tk_capa = self.gerar_capa_miniatura(caminho_vol)

            linha = idx // coluna_max
            coluna = idx % coluna_max

            frame_item = ttk.Frame(frame_conteudo, padding=8, relief="solid")
            frame_item.grid(row=linha, column=coluna, padx=12, pady=12)

            if tk_capa:
                btn = tk.Button(
                    frame_item, 
                    image=tk_capa, 
                    command=lambda p=caminho_vol: self.abrir_manga_da_biblioteca(p),
                    relief="flat", 
                    bd=1,
                    bg="#FFFFFF",
                    activebackground="#D0E3F7"
                )
                btn.pack()
                btn.bind("<Button-3>", lambda e, p=caminho_vol: self.exibir_menu_contexto(e, p))

            nome_vol = os.path.splitext(vol)[0]
            lbl_vol = ttk.Label(frame_item, text=nome_vol, font=("Segoe UI", 8))
            lbl_vol.pack(pady=2)

            dados_vol = self.progresso.get(caminho_vol, {})
            if dados_vol.get("concluido", False):
                lbl_check = tk.Label(frame_item, text="✔ LIDO", font=("Segoe UI", 8, "bold"), fg="#008000", bg="#E9EEF4")
                lbl_check.pack()

    # ==========================================
    # 🎨 TELA 3: LEITOR DE PDF
    # ==========================================
    def montar_tela_leitor(self):
        frame_controles = ttk.Frame(self.frame_leitor, padding=6, relief="groove")
        frame_controles.pack(side="top", fill="x")

        btn_voltar = ttk.Button(frame_controles, text="◄ Voltar aos Volumes", command=self.voltar_para_volumes)
        btn_voltar.pack(side="left", padx=5)

        ttk.Separator(frame_controles, orient="vertical").pack(side="left", fill="y", padx=8)

        btn_anterior = ttk.Button(frame_controles, text="◄ Anterior", command=self.pagina_anterior)
        btn_anterior.pack(side="left", padx=5)

        self.lbl_status_pagina = ttk.Label(frame_controles, text="Página: 0 / 0", font=("Segoe UI", 9, "bold"))
        self.lbl_status_pagina.pack(side="left", padx=10)

        btn_proxima = ttk.Button(frame_controles, text="Próxima ►", command=self.proxima_pagina)
        btn_proxima.pack(side="left", padx=5)

        frame_canvas = ttk.Frame(self.frame_leitor, relief="sunken")
        frame_canvas.pack(expand=True, fill="both", padx=8, pady=8)

        self.canvas = tk.Canvas(frame_canvas, bg="#50555A", highlightthickness=0)
        self.canvas.pack(expand=True, fill="both")

    def voltar_para_volumes(self):
        if self.obra_selecionada:
            self.mostrar_tela_volumes(self.obra_selecionada)
        else:
            self.mostrar_tela_obras()

    def exibir_menu_contexto(self, event, caminho_vol):
        menu = tk.Menu(self.root, tearoff=0)
        esta_concluido = self.progresso.get(caminho_vol, {}).get("concluido", False)

        if esta_concluido:
            menu.add_command(label="Desmarcar como lido", command=lambda: self.alternar_status_lido_manual(caminho_vol))
        else:
            menu.add_command(label="Marcar como lido", command=lambda: self.alternar_status_lido_manual(caminho_vol))

        menu.tk_popup(event.x_root, event.y_root)

    def gerar_capa_miniatura(self, caminho_pdf):
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

    def abrir_manga_da_biblioteca(self, caminho_pdf):
        self.carregar_documento(caminho_pdf)
        self.frame_inicio.pack_forget()
        self.frame_obras.pack_forget()
        self.frame_volumes.pack_forget()
        self.frame_leitor.pack(expand=True, fill="both")

    def abrir_pdf_externo(self):
        caminho = filedialog.askopenfilename(title="Selecione o PDF", filetypes=[("Arquivos PDF", "*.pdf")])
        if caminho:
            self.carregar_documento(caminho)
            self.frame_inicio.pack_forget()
            self.frame_obras.pack_forget()
            self.frame_volumes.pack_forget()
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

    def carregar_documento(self, caminho):
        try:
            if self.doc:
                self.doc.close()

            self.doc = fitz.open(caminho)
            self.caminho_pdf_atual = caminho
            self.total_paginas = len(self.doc)

            dados_salvos = self.progresso.get(caminho, {})
            self.pagina_atual = dados_salvos.get("ultima_pagina", 0)

            if self.pagina_atual >= self.total_paginas:
                self.pagina_atual = 0

            gc.collect()
            self.exibir_pagina()
        except Exception as e:
            messagebox.showerror("Erro", f"Não foi possível abrir o arquivo:\n{e}")

    def exibir_pagina(self):
        if not self.doc:
            return

        self.root.update_idletasks()
        page = self.doc.load_page(self.pagina_atual)

        largura_canvas = self.canvas.winfo_width()
        altura_canvas = self.canvas.winfo_height()

        if largura_canvas > 10 and altura_canvas > 10:
            retangulo_pagina = page.rect
            zoom = (altura_canvas - 20) / retangulo_pagina.height
            matriz = fitz.Matrix(zoom, zoom)

            pix = page.get_pixmap(matrix=matriz)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        else:
            pix = page.get_pixmap(dpi=100)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        self.tk_img = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        
        pos_x = max(largura_canvas // 2, 470)
        self.canvas.create_image(pos_x, 10, anchor="n", image=self.tk_img)

        self.lbl_status_pagina.config(text=f"Página: {self.pagina_atual + 1} / {self.total_paginas}")

# --- EXECUÇÃO DO APLICATIVO ---
if __name__ == "__main__":
    root = tk.Tk()
    app = MangaReaderRetro(root)
    root.mainloop()