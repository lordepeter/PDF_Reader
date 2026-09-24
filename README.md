# PDF_Reader
Software optimized for PDF reading and encouraging literacy.
# 📖 PDF_Reader (MangaReader 2000 - Retrô Edition)

> *Software optimized for PDF reading and encouraging literacy.* 📚✨

Bem-vindo(a) ao **PDF_Reader**! Esta aplicação desktop foi desenvolvida em Python como um projeto prático de Engenharia de Software. O objetivo principal é difundir obras, incentivar o hábito da leitura e oferecer um ambiente de leitura agradável, fluido e nostálgico.

---

## ✨ Principais Funcionalidades

* **🖼️ Interface Aero / Retrô:** Design clássico com botões estilizados, sombras e paleta suave inspirada na era Windows XP / 7.
* **📚 Coleção em 3 Níveis:** Organização automática de arquivos locais dividida de forma limpa por Obras, Seletor de Volumes e Leitor Canvas integrado.
* **⚡ High Performance Matrix:** Renderização direta via `PyMuPDF` (`fitz.Matrix`), garantindo textos e imagens ultra nítidos sem travamentos ou alto consumo de memória.
* **💾 Memória de Leitura & Status:** O leitor salva a página exata onde você parou em um arquivo JSON local e permite marcar volumes como lidos (✔).
* **⌨️ Navegação por Teclado:** Passe as páginas de forma rápida e prática usando as setas direcionais (⬅️ / ➡️).
* **🕰️ Saudação Dinâmica:** A tela inicial do aplicativo reconhece o horário do seu sistema para lhe dar as boas-vindas adequadamente.

---

## 🛠️ Tecnologias Utilizadas

* **Python 3.x**
* **Tkinter / ttk:** Framework nativo para construção da interface gráfica.
* **PyMuPDF (`pymupdf`):** Motor principal para manipulação e renderização vetorial dos PDFs.
* **Pillow (`PIL`):** Para o processamento das capas miniaturas e ícones do sistema.
* **JSON:** Para persistência local do banco de dados do usuário (progresso de leitura).

---

## 🚀 Como Executar o Projeto Localmente

### 1. Pré-requisitos
Certifique-se de ter o Python instalado na sua máquina.

### 2. Instalação das Bibliotecas
Abra o terminal na pasta do projeto e instale as dependências executando:
```bash
pip install pymupdf pillow
