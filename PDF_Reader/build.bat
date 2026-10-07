@echo off
REM ============================================================
REM  build.bat — Compila o app Sophia em .exe
REM
REM  Requisitos:
REM    pip install pyinstaller
REM
REM  Saída:
REM    dist\Sophia\Sophia.exe   (executável)
REM    dist\Sophia\_internal\   (bibliotecas — NÃO apagar)
REM ============================================================

setlocal

echo.
echo ============================================================
echo   Sophia - Build de EXE
echo ============================================================
echo.

REM ---------- 1. Verifica o PyInstaller ----------
pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] PyInstaller nao esta instalado.
    echo.
    echo Rode primeiro:
    echo     pip install pyinstaller
    echo.
    pause
    exit /b 1
)

REM ---------- 2. Limpa builds antigos ----------
echo [1/4] Limpando builds antigos...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM ---------- 3. Roda o PyInstaller ----------
echo.
echo [2/4] Rodando PyInstaller...
pyinstaller Sophia.spec --clean --noconfirm
if errorlevel 1 (
    echo.
    echo [ERRO] Build falhou. Veja as mensagens acima.
    pause
    exit /b 1
)

REM ---------- 4. Prepara pastas de dados (vazias) ----------
echo.
echo [3/4] Preparando pastas de dados...

REM catalogo ja foi embutido pelo .spec, mas garantimos por via das duvidas
if exist catalogo xcopy /E /I /Y catalogo dist\Sophia\catalogo >nul

REM Cria pasta vazia de pdfs caso nao exista
if not exist dist\Sophia\pdf_padrao mkdir dist\Sophia\pdf_padrao

REM Cria pasta vazia de cache de capas
if not exist dist\Sophia\assets\cache_capas mkdir dist\Sophia\assets\cache_capas

echo.
echo [4/4] Build concluido!
echo.
echo ============================================================
echo   Executavel:  dist\Sophia\Sophia.exe
echo ============================================================
echo.
echo IMPORTANTE — antes de zipar e distribuir:
echo   Verifique que NAO existem estes arquivos em dist\Sophia\:
echo     session.json, progresso.json, chatochat.json,
echo     perfis.json, reviews.json, .env
echo.
echo Para rodar, de dois cliques em dist\Sophia\Sophia.exe
echo Para distribuir, mande a pasta dist\Sophia INTEIRA.
echo.
pause
endlocal