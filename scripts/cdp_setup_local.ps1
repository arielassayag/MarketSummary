<#
CDP — Cabra da Peste: preparação do clone dedicado às rotinas no PC local (Windows PowerShell
5.1+ ou PowerShell 7).

Uso (na raiz do clone):
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\cdp_setup_local.ps1
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\cdp_setup_local.ps1 -Harness codex
Opções:
  -Harness      app que vai rodar as rotinas neste clone: claude-code (padrão), codex,
                antigravity ou gemini (identidade gravada em .cdp\local.yaml)
  -SkipPlugin   não registra o marketplace nem instala o plugin `cdp` no Claude Code
  -SkipTests    pula o teste rápido offline
  -SkipTravaTeste  não testa o push no ramo cdp-trava (só lê a trava)

O que faz: confere git, instala o uv (instalador oficial) se faltar, sincroniza o ambiente, roda
`cdp status`, `cdp agenda` e `cdp verify`, um teste offline (DADOS SIMULADOS), testa o push em
main (--dry-run) e o push real no ramo cdp-trava (adquire a trava distribuída por 1 minuto, em
nome da tarefa só de leitura cdp-status, e a libera em seguida; rode fora dos horários das
rotinas), registra a identidade do clone (`cdp executor registrar --como local-pc`), registra o
marketplace e instala o plugin `cdp` (Claude Code) e imprime os próximos passos. Não altera o
livro, a trilha nem os dados; no GitHub, só o ramo cdp-trava recebe os dois commits do teste da
trava.
#>
param(
    [ValidateSet("claude-code", "codex", "antigravity", "gemini")]
    [string]$Harness = "claude-code",
    [switch]$SkipPlugin,
    [switch]$SkipTests,
    [switch]$SkipTravaTeste
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

Step "CDP — Cabra da Peste: preparação local em $Root (app: $Harness)"
if (-not (Test-Path "pyproject.toml") -or -not (Test-Path "src\cdp")) {
    throw "Pasta inesperada: rode a partir do clone do repositório."
}

Step "git"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "git não encontrado: instale o Git for Windows (inclui o Git Bash usado pelo Claude Code)."
}
git --version
Write-Host ("ramo: " + (git branch --show-current))
$autocrlf = git config --get core.autocrlf
if ($autocrlf) { Write-Host "core.autocrlf=$autocrlf (book/, data/ e reports/ ficam sem conversão via .gitattributes)" }

Step "uv"
$uvInstalled = $false
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv não encontrado: instalando pelo instalador oficial (https://astral.sh/uv)..."
    powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    $uvInstalled = $true
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

Step "Acesso de escrita ao GitHub: push em main e no ramo cdp-trava (trava distribuída)"
git push --dry-run 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Warn "git push --dry-run falhou: configure a autenticação (Git Credential Manager, gh auth login ou SSH) e um upstream (git push -u origin main). As rotinas também precisam fazer push no ramo cdp-trava (a trava falha fechada)."
} else { Write-Host "push em main (--dry-run): ok" }
if ($SkipTravaTeste) {
    uv run python -m cdp trava ver
    if ($LASTEXITCODE -ne 0) { Warn "não foi possível ler a trava (ramo cdp-trava): confira a rede e a credencial do Git." }
} else {
    # Push real no ramo cdp-trava: adquire a trava por 1 minuto (tarefa só de leitura cdp-status)
    # e a libera. Uma rotina que dispare neste instante encontra a trava ocupada e é pulada: rode
    # fora dos horários das rotinas.
    $travaTexto = (uv run python -m cdp trava adquirir --tarefa cdp-status --ttl 1 2>$null) -join "`n"
    $travaRc = $LASTEXITCODE
    $travaId = ""
    try { $travaId = "$(($travaTexto | ConvertFrom-Json).id)" } catch { }
    if ($travaRc -eq 0) {
        uv run python -m cdp trava liberar --id $travaId 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { Write-Host "push no ramo cdp-trava: ok (trava adquirida e liberada)" }
        else { Warn "a trava foi adquirida, mas não liberada: ela expira sozinha em 1 minuto." }
    } elseif ($travaRc -eq 10) {
        Warn "outra rotina segura a trava agora: o push no ramo cdp-trava não foi testado. Rode o script de novo fora dos horários das rotinas."
    } else {
        Warn "o push no ramo cdp-trava falhou (rede, credencial ou regra do repositório): sem ele, a montagem, o fechamento e as notas não rodam. Confira com 'uv run python -m cdp trava ver'."
    }
}

Step "Identidade deste clone (executor local)"
if (Test-Path ".cdp\local.yaml") {
    Write-Host "já registrada (.cdp\local.yaml):"
    Get-Content ".cdp\local.yaml" | Write-Host
} else {
    uv run python -m cdp executor registrar --como local-pc --harness $Harness
    if ($LASTEXITCODE -ne 0) { Warn "registro recusado: use um clone dedicado às rotinas, no ramo main e fora de worktree." }
}
uv run python -m cdp executor mostrar

if ($Harness -eq "claude-code") {
    Step "Claude Code (plugin cdp)"
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
}

Step "Próximos passos (docs/cdp/LOCAL.md e docs/cdp/ROTINAS.md)"
if ($uvInstalled) {
    Warn "o uv acabou de ser instalado: feche e reabra o app do Claude (ou do Codex/Antigravity): o PATH novo só vale para processos novos."
}
@"
1. Uma mente por vez: desligue as rotinas do CDP em qualquer outro app (nuvem do Claude Code,
   Codex, Antigravity). Este clone é só das rotinas (na main), separado do de desenvolvimento.
   O executor designado em configs/cdp/executor.yaml precisa ser local-pc.
2. Tarefas agendadas, uma por tarefa da agenda, com o id da tarefa na instrução:
     cdp-status          segundas 08:30
     cdp-semanal         dias úteis 11:07   (reservas cdp-semanal-b 12:07, cdp-semanal-c 13:07,
                                             cdp-semanal-d 14:07)
     cdp-risco-1330      dias úteis 13:30   (e cdp-risco-1603 às 16:03)
     cdp-diario          dias úteis 19:22   (reforço cdp-diario-reforco 21:07;
                                             repescagem cdp-diario-sabado sábados 10:07)
     cdp-cobertura       segunda a quinta 22:37
     cdp-calibracao      dia 1 de cada mês 09:15
   - Claude Code (app desktop): Code -> Routines -> New routine -> Local, pasta = $Root,
     worktree DESLIGADO, modo "Aceitar edições", instrução = /cdp:<skill> <tarefa> (ex.:
     /cdp:diario cdp-diario-reforco). Tabela pronta:
     uv run python -m cdp rotinas exportar --alvo claude-desktop
   - Codex: uv run python -m cdp rotinas exportar --alvo codex --formato md
   - Antigravity: uv run python -m cdp rotinas exportar --alvo windows --harness agy
   Horários de Brasília: se o PC estiver em outro fuso, converta (campo pc_menos_brasilia_horas
   de 'uv run python -m cdp agenda').
3. "Run now" em cdp-status para conferir; mantenha o computador acordado nos horários.
4. Sem o app aberto: scripts\cdp_rotina.ps1 <tarefa> -Harness <app> pelo Agendador de Tarefas
   (uv run python -m cdp rotinas exportar --alvo windows --harness <app>).
"@ | Write-Host
