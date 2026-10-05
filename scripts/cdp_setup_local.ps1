<#
CDP — Cabra da Peste: preparação do PC local (Windows PowerShell 5.1+ ou PowerShell 7).

Uso (na raiz do clone):
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\cdp_setup_local.ps1
Opções:
  -SkipPlugin   não registra o marketplace nem instala o plugin `cdp` no Claude Code
  -SkipTests    pula o teste rápido offline

O que faz: confere git, instala o uv (instalador oficial) se faltar, sincroniza o ambiente, roda
`cdp status`, `cdp agenda` e `cdp verify`, um teste offline (DADOS SIMULADOS), registra o
marketplace do repositório e instala o plugin `cdp` (se o Claude Code CLI estiver no PATH) e
imprime os próximos passos. Não altera o livro, a trilha nem os dados.
#>
param(
    [switch]$SkipPlugin,
    [switch]$SkipTests
)
# "Continue": no Windows PowerShell 5.1, stderr de comandos nativos (git/uv) redirecionado
# vira erro terminante com "Stop". As falhas são checadas por $LASTEXITCODE e `throw`.
$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

function Step([string]$msg) { Write-Host ""; Write-Host "== $msg" -ForegroundColor Cyan }
function Warn([string]$msg) { Write-Warning $msg }
function Run([string]$label, [scriptblock]$cmd) {
    & $cmd
    if ($LASTEXITCODE -ne 0) { throw "$label falhou (código $LASTEXITCODE)." }
}

Step "CDP — Cabra da Peste: preparação local em $Root"
if (-not (Test-Path "pyproject.toml") -or -not (Test-Path "src\cdp")) {
    throw "Pasta inesperada: rode a partir do clone do repositório."
}

Step "git"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "git não encontrado: instale o Git for Windows (inclui o Git Bash usado pelo Claude Code)."
}
git --version
Write-Host ("branch: " + (git branch --show-current))
$autocrlf = git config --get core.autocrlf
if ($autocrlf) { Write-Host "core.autocrlf=$autocrlf (book/, data/ e reports/ ficam sem conversão via .gitattributes)" }

Step "uv"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv não encontrado: instalando pelo instalador oficial (https://astral.sh/uv)..."
    powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
Run "uv --version" { uv --version }

Step "Dependências (uv sync --extra dev --extra ai)"
Run "uv sync" { uv sync --extra dev --extra ai }

Step "Estado do fundo"
Run "cdp status" { uv run python -m cdp status }
Run "cdp agenda" { uv run python -m cdp agenda }
uv run python -m cdp verify
if ($LASTEXITCODE -ne 0) {
    Warn "cdp verify não confirmou a integridade. Não ligue as rotinas antes de entender o motivo (veja fins de linha em docs/cdp/LOCAL.md)."
}

if (-not $SkipTests) {
    Step "Teste rápido offline (DADOS SIMULADOS)"
    Run "pytest" { uv run pytest tests/cdp/test_demo_runtime.py -q -W ignore }
}

Step "Acesso de escrita ao GitHub (git push --dry-run)"
git push --dry-run 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Warn "git push --dry-run falhou: configure a autenticação (Git Credential Manager, gh auth login ou SSH) e um upstream (git push -u origin main)."
} else { Write-Host "ok" }

Step "Claude Code"
if (Get-Command claude -ErrorAction SilentlyContinue) {
    claude --version
    if (-not $SkipPlugin) {
        claude plugin marketplace add "$Root"
        if ($LASTEXITCODE -ne 0) { Warn "não foi possível registrar o marketplace (veja docs/cdp/LOCAL.md)." }
        claude plugin install cdp@cdp-cabra-da-peste
        if ($LASTEXITCODE -ne 0) { Warn "não foi possível instalar o plugin cdp (veja docs/cdp/LOCAL.md)." }
        claude plugin list
    }
} else {
    Warn "Claude Code CLI não encontrado no PATH. Instale o app desktop/CLI e rode:"
    Write-Host "  claude plugin marketplace add `"$Root`""
    Write-Host "  claude plugin install cdp@cdp-cabra-da-peste"
}

Step "Próximos passos (docs/cdp/LOCAL.md)"
@"
1. Desative as rotinas do CDP na nuvem, se existirem (duas mentes não podem gravar o mesmo livro).
2. No app desktop do Claude: Code -> Routines -> New routine -> Local, pasta = $Root,
   worktree DESLIGADO, modo de permissão "Aceitar edições", e crie:
     cdp-semanal     dias úteis 11:07   instruções: /cdp:semanal
     cdp-risco-1330  dias úteis 13:30   instruções: /cdp:risco
     cdp-risco-1600  dias úteis 16:00   instruções: /cdp:risco
     cdp-diario      dias úteis 19:22   instruções: /cdp:diario
     cdp-status      segundas 08:30     instruções: /cdp:status
     cdp-calibracao  mensal (dia 1)     instruções: /cdp:calibracao
   Horários de Brasília: se o PC estiver em outro fuso, converta (campo
   pc_menos_brasilia_horas de 'uv run python -m cdp agenda').
3. Clique em "Run now" em cdp-status para conferir permissões; ative "Keep computer awake".
4. Sem o app aberto? Use scripts\cdp_run_task.ps1 com o Agendador de Tarefas (exemplos em docs/cdp/LOCAL.md).
"@ | Write-Host
