# 📖 MangaReader 2000 — Retro Edition

> Leitor de mangás e PDFs com interface inspirada na era Windows XP / 7 — projetado para incentivar o hábito da leitura com uma experiência nostálgica e fluida.

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![Tkinter](https://img.shields.io/badge/UI-Tkinter%20%2F%20ttk-FF6F00)
![PyMuPDF](https://img.shields.io/badge/Render-PyMuPDF-1B6B4A)
![Status](https://img.shields.io/badge/status-em%20desenvolvimento-yellow)

---

## 🎯 Sobre o Projeto

**MangaReader 2000** é uma aplicação desktop desenvolvida em **Python** como projeto de estudo e portfólio de Engenharia de Software. O objetivo é oferecer um leitor de mangás/PDFs completo, com interface retrô, gerenciamento de biblioteca, catálogo de obras para download e funcionalidades sociais simuladas (perfis, reviews e chat).

O projeto foi construído com foco em **arquitetura limpa**, **separação de responsabilidades** e **padrões profissionais** aplicados a um domínio real.

---

## ✨ Funcionalidades

### Leitura
- **Leitor PDF com zoom adaptativo** via `PyMuPDF` (fitz.Matrix), sem travamentos
- **Navegação por teclado** (setas ⬅️ / ➡️)
- **Retomada automática** — salva a página onde você parou
- **Marcação de volumes como lidos** (✔) via menu de contexto

### Biblioteca
- **Organização em 3 níveis**: Obras → Volumes → Leitor
- **Detecção automática** de obras na pasta `pdf_padrao/`
- **Capas geradas** em miniatura a partir da 1ª página de cada PDF
- **Abertura de PDFs externos** via menu

### Catálogo & Downloads
- **Catálogo de obras** disponíveis para download
- **Downloads assíncronos** com barra de progresso em tempo real (thread + `queue.Queue`)
- **Escrita atômica** — arquivos gravados como `.parcial` e renomeados só ao concluir
- **Estados por card**: Disponível → Baixando… → Já na biblioteca

### Perfil & Social
- **Perfis editáveis** com bio, foto e favoritos
- **Múltiplos perfis** coexistindo no mesmo app
- **Reviews com CRUD completo** — nota, texto, edição e exclusão
- **ChatoChat** — chat local com preview da última mensagem por contato

---

## 🏗️ Arquitetura

O projeto segue uma divisão em **3 camadas**, com dependências apontando em uma única direção:

| Camada | Arquivo | Responsabilidade |
|---|---|---|
| **Interface** | `main.py` | Toda a UI Tkinter, navegação entre telas, eventos |
| **Aplicação** | `gerenciador_downloads.py` | Downloads assíncronos com progresso (thread + queue) |
| **Persistência** | `repositories.py` | Repository Pattern + Protocols + escrita atômica |
| **Domínio** | `models.py` | Dataclasses puras (`Review`, `Mensagem`, `Perfil`, `CatalogoItem`...) |

---

## 🧠 Padrões e Decisões Técnicas

Este projeto aplica conscientemente os seguintes padrões:

### 1. **Repository Pattern**
Cada tipo de dado (`Progresso`, `Perfis`, `Reviews`, `Chat`, `Catálogo`) tem seu próprio repositório. A UI **nunca** acessa arquivos ou rede diretamente — ela só chama métodos dos repositórios. Isso permite trocar JSON local por uma **API REST** mudando apenas o *composition root*, sem tocar em nenhuma tela.

### 2. **Injeção de Dependência**
`MangaReaderRetro` recebe os repositórios pelo construtor em vez de criá-los internamente. Quem decide qual implementação usar é o bloco `if __name__ == "__main__":` — o único ponto do projeto que sabe que os dados vivem em JSON.

### 3. **Protocol (PEP 544)**
Cada repositório cumpre um `Protocol` que descreve os métodos esperados. Isso é **tipagem estrutural** — mais flexível que herança para permitir que implementações de terceiros (ex: `RepositorioReviewsAPI`) funcionem sem herdar de nada.

### 4. **Escrita Atômica de JSON**
Todo salvamento grava em `.tmp` e depois usa `os.replace()`. Se o app travar no meio da escrita, o arquivo original permanece intacto — nunca fica corrompido.

### 5. **Concorrência segura com Tkinter**
Downloads rodam em threads separadas que **nunca tocam em widgets**. Elas comunicam via `queue.Queue`, e a thread principal lê a fila a cada 100ms via `root.after()`. É o padrão produtor/consumidor aplicado a GUIs.

### 6. **Dataclasses para Domínio**
Entidades como `Review` e `Perfil` são `@dataclass` puras, sem dependência de Tkinter, JSON ou rede. Isso as torna testáveis em isolamento e prontas para serialização em qualquer formato.

---

## 🛠️ Stack Tecnológica

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3.11+ |
| Interface | Tkinter / ttk |
| Renderização de PDF | PyMuPDF (`pymupdf`) |
| Processamento de imagem | Pillow (`PIL`) |
| HTTP (downloads) | `urllib.request` (stdlib) |
| Concorrência | `threading` + `queue.Queue` |
| Persistência | JSON local (com escrita atômica) |

---

## 🚀 Como Executar

### Pré-requisitos
- Python 3.11 ou superior
- pip

### Instalação

```bash
# 1. Clone o repositório
git clone https://github.com/SEU_USUARIO/PDF_Reader.git
cd PDF_Reader

# 2. Instale as dependências
pip install pymupdf pillow

# 3. Execute
python main.py
