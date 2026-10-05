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

Log: logs\cdp\<tarefa>_<AAAAmmdd_HHMMSS>.log. A trava logs\cdp\.lock impede duas rotinas ao mesmo
tempo (o livro é encadeado por hash). Permissões: .claude\settings.json (no modo -p, o que não
estiver liberado é negado e a skill relata o bloqueio no resumo).
#>
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("semanal", "diario", "risco", "status", "calibracao")]
    [string]$Task,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$SkillArgs
)
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"

$logDir = Join-Path $Root "logs\cdp"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = Join-Path $logDir "${Task}_$stamp.log"
$lock = Join-Path $logDir ".lock"

# Trava órfã (processo morto) com mais de 6 horas é removida.
if ((Test-Path $lock) -and ((Get-Item $lock).LastWriteTime -lt (Get-Date).AddHours(-6))) {
    Remove-Item $lock -Recurse -Force -ErrorAction SilentlyContinue
}
try {
    New-Item -ItemType Directory -Path $lock -ErrorAction Stop | Out-Null
} catch {
    "$(Get-Date -Format s) outra rotina do CDP em execução ($lock): $Task não iniciada." |
        Out-File -FilePath $log -Append -Encoding utf8
    exit 0
}

$rc = 1
try {
    $claude = if ($env:CDP_CLAUDE_BIN) { $env:CDP_CLAUDE_BIN } else { "claude" }
    $mode = if ($env:CDP_PERMISSION_MODE) { $env:CDP_PERMISSION_MODE } else { "acceptEdits" }
    $prompt = ("/cdp:$Task " + ($SkillArgs -join " ")).Trim()
    $extra = @()
    if ($env:CDP_CLAUDE_ARGS) { $extra = @($env:CDP_CLAUDE_ARGS -split "\s+" | Where-Object { $_ }) }
    "== CDP — rotina $Task — início $(Get-Date -Format o)" | Out-File -FilePath $log -Append -Encoding utf8
    & $claude -p $prompt --permission-mode $mode --output-format text @extra 2>&1 |
        Out-File -FilePath $log -Append -Encoding utf8
    $rc = $LASTEXITCODE
    "== fim $(Get-Date -Format o) — código $rc" | Out-File -FilePath $log -Append -Encoding utf8
} finally {
    Remove-Item $lock -Recurse -Force -ErrorAction SilentlyContinue
}
exit $rc
