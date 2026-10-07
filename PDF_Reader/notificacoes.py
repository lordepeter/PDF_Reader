"""Notificações estilo MSN — janelinhas animadas no canto inferior direito.

Duas classes:
- `Notificacao` — a janelinha individual (Toplevel sem decoração, com
  animação de entrada/saída)
- `GerenciadorNotificacoes` — cria e empilha múltiplas notificações,
  reposicionando quando uma fecha

Uso típico no `main.py`:
    self.notificacoes = GerenciadorNotificacoes(root)
    self.notificacoes.on_click_global = self._on_notificacao_click
    self.notificacoes.notificar(
        titulo="Nova mensagem de chumbinho",
        mensagem="oi, tudo bem?",
        icone="💬",
        tipo="chat",
        dado={"amigo": "chumbinho"},
    )
"""
from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional


# ============================================================
# NOTIFICAÇÃO INDIVIDUAL
# ============================================================
class Notificacao:
    """Uma janelinha de notificação animada."""

    LARGURA = 340
    ALTURA = 100
    DURACAO_VISIVEL = 5000          # 5s
    DURACAO_ANIMACAO = 250          # ms
    PASSO_ANIMACAO = 16             # ~60fps
    MARGEM_BORDA = 12
    MARGEM_INFERIOR = 55            # deixa espaço para a barra de tarefas
    ESPACO_ENTRE = 8                # espaço entre notificações empilhadas

    def __init__(
        self,
        root: tk.Tk,
        titulo: str,
        mensagem: str,
        icone: str = "💬",
        on_click: Optional[Callable[[], None]] = None,
        gerenciador: Optional["GerenciadorNotificacoes"] = None,
        pos_y_final: int = 0,
    ):
        self.root = root
        self.on_click = on_click
        self.gerenciador = gerenciador
        self._fechando = False
        self._pos_y_final = pos_y_final

        # ---------- Janela ----------
        self.janela = tk.Toplevel(root)
        self.janela.overrideredirect(True)  # remove barra de título
        try:
            self.janela.attributes("-topmost", True)  # fica acima de tudo
        except tk.TclError:
            pass
        try:
            self.janela.attributes("-alpha", 0.0)  # começa invisível
        except tk.TclError:
            pass

        # Borda decorativa (2px azul escuro)
        moldura = tk.Frame(self.janela, bg="#003366")
        moldura.pack(fill="both", expand=True)

        conteudo = tk.Frame(moldura, bg="#F0F4F8")
        conteudo.pack(fill="both", expand=True, padx=2, pady=2)

        # Ícone (esquerda)
        lbl_icone = tk.Label(
            conteudo, text=icone, bg="#F0F4F8", fg="#003366",
            font=("Segoe UI", 22),
        )
        lbl_icone.pack(side="left", padx=(12, 10), pady=12)

        # Textos (centro)
        textos = tk.Frame(conteudo, bg="#F0F4F8")
        textos.pack(side="left", fill="both", expand=True, pady=12)

        lbl_titulo = tk.Label(
            textos, text=titulo, bg="#F0F4F8", fg="#003366",
            font=("Segoe UI", 10, "bold"),
            anchor="w", justify="left",
        )
        lbl_titulo.pack(fill="x")

        lbl_mensagem = tk.Label(
            textos, text=mensagem, bg="#F0F4F8", fg="#333333",
            font=("Segoe UI", 9),
            anchor="w", justify="left", wraplength=230,
        )
        lbl_mensagem.pack(fill="x", pady=(2, 0))

        # Botão X (direita)
        btn_x = tk.Button(
            conteudo, text="✖", bg="#F0F4F8", fg="#888888",
            relief="flat", bd=0, cursor="hand2",
            font=("Segoe UI", 9),
            command=self._clicar_botao_fechar,
        )
        btn_x.pack(side="right", anchor="n", padx=(0, 6), pady=6)

        # ---------- Cliques (só nas áreas de conteúdo, não no X) ----------
        for w in (conteudo, moldura, textos, lbl_icone, lbl_titulo, lbl_mensagem):
            w.bind("<Button-1>", self._clicar_corpo)

        # ---------- Posição inicial (fora da tela, abaixo) ----------
        self._pos_x = self.janela.winfo_screenwidth() - self.LARGURA - self.MARGEM_BORDA
        self._inicio_y = self.janela.winfo_screenheight()

        self.janela.geometry(
            f"{self.LARGURA}x{self.ALTURA}+{self._pos_x}+{self._inicio_y}"
        )

        # ---------- Animações ----------
        self._animar_entrada()
        self._timer_fechar = self.janela.after(self.DURACAO_VISIVEL, self.fechar)

        # Se o app fechar, destruir junto
        try:
            self.root.bind("<Destroy>", self._on_root_destroy, add="+")
        except tk.TclError:
            pass

    # ---------- Eventos ----------
    def _clicar_corpo(self, event=None):
        """Clique no corpo da notificação: chama o callback e fecha."""
        if self.on_click:
            try:
                self.on_click()
            except Exception as e:
                print(f"[notificação] erro no callback: {e}")
        self.fechar()

    def _clicar_botao_fechar(self):
        """Clique no X: só fecha, sem callback."""
        self.fechar()

    def _on_root_destroy(self, event=None):
        """Se o root for destruído, fecha tudo."""
        try:
            self.janela.destroy()
        except tk.TclError:
            pass

    # ---------- Posicionamento ----------
    def definir_posicao_y(self, y_final: int):
        """Chamado pelo gerenciador — define a posição Y final."""
        self._pos_y_final = y_final

    def animar_para_y(self, y_final: int):
        """Anima suavemente para uma nova posição vertical."""
        self._pos_y_final = y_final
        try:
            y_atual = self.janela.winfo_y()
        except tk.TclError:
            return

        passos = 8
        delta = (y_final - y_atual) / passos

        def passo(atual, restantes):
            if self._fechando:
                return
            if restantes <= 0:
                try:
                    self.janela.geometry(
                        f"{self.LARGURA}x{self.ALTURA}+{self._pos_x}+{y_final}"
                    )
                except tk.TclError:
                    pass
                return
            atual += delta
            try:
                self.janela.geometry(
                    f"{self.LARGURA}x{self.ALTURA}+{self._pos_x}+{int(atual)}"
                )
                self.janela.after(15, lambda: passo(atual, restantes - 1))
            except tk.TclError:
                pass

        passo(y_atual, passos)

    # ---------- Animações de entrada/saída ----------
    def _animar_entrada(self):
        """Desliza de baixo para cima + fade in."""
        passos = max(1, self.DURACAO_ANIMACAO // self.PASSO_ANIMACAO)
        delta = (self._pos_y_final - self._inicio_y) / passos

        def passo(atual, restantes):
            if self._fechando:
                return
            if restantes <= 0:
                try:
                    self.janela.geometry(
                        f"{self.LARGURA}x{self.ALTURA}+{self._pos_x}+{self._pos_y_final}"
                    )
                    self.janela.attributes("-alpha", 1.0)
                except tk.TclError:
                    pass
                return
            atual += delta
            try:
                self.janela.geometry(
                    f"{self.LARGURA}x{self.ALTURA}+{self._pos_x}+{int(atual)}"
                )
                alpha = min(1.0, 1.0 - (restantes / passos))
                self.janela.attributes("-alpha", alpha)
                self.janela.after(self.PASSO_ANIMACAO, lambda: passo(atual, restantes - 1))
            except tk.TclError:
                pass

        passo(self._inicio_y, passos)

    def fechar(self):
        """Inicia a animação de saída."""
        if self._fechando:
            return
        self._fechando = True

        try:
            self.janela.after_cancel(self._timer_fechar)
        except (tk.TclError, AttributeError):
            pass

        try:
            pos_y_atual = self.janela.winfo_y()
        except tk.TclError:
            self._destruir()
            return

        altura_saida = self.janela.winfo_screenheight()
        passos = max(1, self.DURACAO_ANIMACAO // self.PASSO_ANIMACAO)
        delta = (altura_saida - pos_y_atual) / passos

        def passo(atual, restantes):
            if restantes <= 0:
                self._destruir()
                return
            atual += delta
            try:
                self.janela.geometry(
                    f"{self.LARGURA}x{self.ALTURA}+{self._pos_x}+{int(atual)}"
                )
                alpha = max(0.0, restantes / passos)
                self.janela.attributes("-alpha", alpha)
                self.janela.after(self.PASSO_ANIMACAO, lambda: passo(atual, restantes - 1))
            except tk.TclError:
                self._destruir()

        passo(pos_y_atual, passos)

    def _destruir(self):
        try:
            self.janela.destroy()
        except tk.TclError:
            pass
        if self.gerenciador is not None:
            self.gerenciador._remover(self)


# ============================================================
# GERENCIADOR (empilhamento)
# ============================================================
class GerenciadorNotificacoes:
    """Cria e gerencia múltiplas notificações empilhadas no canto inferior direito."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.ativas: list[Notificacao] = []
        self.on_click_global: Optional[Callable[[str, dict], None]] = None

    def notificar(
        self,
        titulo: str,
        mensagem: str,
        icone: str = "💬",
        tipo: str = "geral",
        dado: Optional[dict] = None,
    ):
        """Cria uma nova notificação e reposiciona as existentes."""
        dado = dado or {}

        def on_click():
            if self.on_click_global is not None:
                try:
                    self.on_click_global(tipo, dado)
                except Exception as e:
                    print(f"[notificação] erro no callback global: {e}")

        # Calcula a posição Y final (a nova fica embaixo, as antigas sobem)
        pos_y = self._calcular_pos_y_para_nova()

        notif = Notificacao(
            self.root,
            titulo=titulo,
            mensagem=mensagem,
            icone=icone,
            on_click=on_click,
            gerenciador=self,
            pos_y_final=pos_y,
        )
        self.ativas.append(notif)

        # As antigas sobem uma posição
        self._reposicionar_todas(exceto=notif)
        return notif

    def _calcular_pos_y_para_nova(self) -> int:
        """A nova notificação sempre aparece na base (embaixo)."""
        altura_tela = self.root.winfo_screenheight()
        return altura_tela - Notificacao.MARGEM_INFERIOR - Notificacao.ALTURA

    def _remover(self, notif: Notificacao):
        if notif in self.ativas:
            self.ativas.remove(notif)
        self._reposicionar_todas()

    def _reposicionar_todas(self, exceto: Optional[Notificacao] = None):
        """Reposiciona todas as notificações empilhadas (mais nova embaixo)."""
        altura_tela = self.root.winfo_screenheight()
        y_base = altura_tela - Notificacao.MARGEM_INFERIOR - Notificacao.ALTURA
        altura_com_espaco = Notificacao.ALTURA + Notificacao.ESPACO_ENTRE

        # Ordem: [mais antiga, ..., mais nova]
        # Mais nova fica em y_base, as antigas sobem
        for i, notif in enumerate(reversed(self.ativas)):
            y_final = y_base - i * altura_com_espaco
            notif.definir_posicao_y(y_final)
            if notif is not exceto and not notif._fechando:
                notif.animar_para_y(y_final)