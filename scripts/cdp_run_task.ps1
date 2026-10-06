<#
CDP — Cabra da Peste: executa uma skill do plugin `cdp` sem interface (`claude -p`).

Alternativa às tarefas agendadas do app desktop, para o Agendador de Tarefas do Windows.
Uso:
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\cdp_run_task.ps1 diario
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\cdp_run_task.ps1 diario 2026-10-05
Variáveis de ambiente opcionais:
  CDP_PERMISSION_MODE   modo de permissão do claude -p (padrão: acceptEdits)
  CDP_CLAUDE_ARGS       flags extras do claude (ex.: "--permission-prompts none")
  CDP_CLAUDE_BIN        caminho do executável claude (padrão: o do PATH)
  CDP_LOCK_WAIT_MIN     minutos esperando outra rotina terminar (padrão: 60 para semanal,
                        diario e cobertura, 0 para as demais)

Log: logs\cdp\<tarefa>_<AAAAmmdd_HHMMSS>.log. A trava logs\cdp\.lock impede duas rotinas ao mesmo
tempo (o livro é encadeado por hash); se continuar ocupada depois da espera, a rotina não roda e o
script sai com código 75 (o Agendador mostra a execução como não concluída). Na calibração, o
backtest roda aqui antes da skill (no modo -p, uma tarefa em segundo plano morre quando a resposta
termina). Permissões: .claude\settings.json (no modo -p, o que não estiver liberado é negado e a
skill relata o bloqueio no resumo).
#>
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("semanal", "diario", "cobertura", "risco", "status", "calibracao")]
    [string]$Task,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$SkillArgs
)
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
# Saída UTF-8 dos comandos nativos (claude, uv) lida como UTF-8, não pela página de código OEM.
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"

$logDir = Join-Path $Root "logs\cdp"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = Join-Path $logDir "${Task}_$stamp.log"
$lock = Join-Path $logDir ".lock"
function Log([string]$msg) { $msg | Out-File -FilePath $log -Append -Encoding utf8 }

$waitMin = 0
if ($env:CDP_LOCK_WAIT_MIN) { $waitMin = [int]$env:CDP_LOCK_WAIT_MIN }
elseif ($Task -in @("semanal", "diario", "cobertura")) { $waitMin = 60 }

# Trava órfã (processo morto) com mais de 6 horas é removida.
if ((Test-Path $lock) -and ((Get-Item $lock).LastWriteTime -lt (Get-Date).AddHours(-6))) {
    Remove-Item $lock -Recurse -Force -ErrorAction SilentlyContinue
}
$deadline = (Get-Date).AddMinutes($waitMin)
$locked = $false
while (-not $locked) {
    try {
        New-Item -ItemType Directory -Path $lock -ErrorAction Stop | Out-Null
        $locked = $true
    } catch {
        if ((Get-Date) -ge $deadline) { break }
        Start-Sleep -Seconds 30
    }
}
if (-not $locked) {
    Log "$(Get-Date -Format s) outra rotina do CDP em execução ($lock) após $waitMin min de espera: $Task não iniciada."
    exit 75
}

$rc = 1
try {
    Log "== CDP — rotina $Task — início $(Get-Date -Format o)"
    if ($Task -eq "calibracao") {
        $today = $null
        try {
            $today = (& uv run python -c "from datetime import datetime; from zoneinfo import ZoneInfo; print(datetime.now(ZoneInfo('America/Sao_Paulo')).date())" 2>$null |
                Select-Object -Last 1)
        } catch { Log "== uv indisponível: $($_.Exception.Message)" }
        $out = "reports/backtest/$today/mensal"
        if (-not $today) {
            Log "== não foi possível obter a data de Brasília: a skill decide sobre o backtest"
        } elseif ((Test-Path "reports/backtest/$today/CALIBRACAO_MENSAL.md") -or (Test-Path "$out/metrics.json")) {
            Log "== backtest mensal de $today já existe em $out"
        } else {
            Log "== backtest mensal (antes da skill) em $out — início $(Get-Date -Format o)"
            try {
                & uv run python -m cdp backtest --start 2021-01-04 --out $out 2>&1 |
                    Out-File -FilePath $log -Append -Encoding utf8
                Log "== backtest — fim $(Get-Date -Format o) — código $LASTEXITCODE"
            } catch { Log "== backtest falhou: $($_.Exception.Message)" }
        }
    }
    $claude = if ($env:CDP_CLAUDE_BIN) { $env:CDP_CLAUDE_BIN } else { "claude" }
    $mode = if ($env:CDP_PERMISSION_MODE) { $env:CDP_PERMISSION_MODE } else { "acceptEdits" }
    $prompt = ("/cdp:$Task " + ($SkillArgs -join " ")).Trim()
    $extra = @()
    if ($env:CDP_CLAUDE_ARGS) { $extra = @($env:CDP_CLAUDE_ARGS -split "\s+" | Where-Object { $_ }) }
    try {
        & $claude -p $prompt --permission-mode $mode --output-format text @extra 2>&1 |
            Out-File -FilePath $log -Append -Encoding utf8
        $rc = $LASTEXITCODE
    } catch {
        # Ex.: claude fora do PATH (CommandNotFoundException) — vai para o log, não para o console.
        Log "== erro ao executar '$claude': $($_.Exception.Message)"
        $rc = 1
    }
    Log "== fim $(Get-Date -Format o) — código $rc"
} finally {
    Remove-Item $lock -Recurse -Force -ErrorAction SilentlyContinue
}
exit $rc
