<#
CDP — Cabra da Peste: atalho do Claude Code com o plugin `cdp` para o Agendador de Tarefas do
Windows.

Uso:
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\cdp_run_task.ps1 diario cdp-diario-reforco
Equivale a:
  scripts\cdp_rotina.ps1 <tarefa> -Harness claude -ModoPrompt plugin [opções]
O script de rotina faz tudo: trava local com espera em CDP_LOCK_WAIT_MIN (saída 75 se continuar
ocupada), uv sync, prévia do gate sem chamar o modelo, backtest da calibração antes da skill,
`claude -p "/cdp:<skill> <tarefa>"`, liberação da trava distribuída e log em logs\cdp\. Prefira
passar a tarefa: sem ela, este atalho escolhe a da família pelo horário de Brasília (agendas
antigas, de uma linha por skill). Opções repassadas: -Ensaio, -Manual, -Seco.
#>
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("semanal", "diario", "cobertura", "risco", "status", "calibracao")]
    [string]$Skill,
    [Parameter(Position = 1)]
    [string]$Tarefa = "",
    [switch]$Ensaio,
    [switch]$Manual,
    [switch]$Seco
)
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$OutputEncoding = [System.Text.Encoding]::UTF8

if (-not $Tarefa) {
    $agora = [System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTime]::UtcNow, "E. South America Standard Time")
    $hhmm = [int]$agora.ToString("HHmm")
    switch ($Skill) {
        "semanal" {
            if ($hhmm -lt 1207) { $Tarefa = "cdp-semanal" }
            elseif ($hhmm -lt 1307) { $Tarefa = "cdp-semanal-b" }
            elseif ($hhmm -lt 1407) { $Tarefa = "cdp-semanal-c" }
            else { $Tarefa = "cdp-semanal-d" }
        }
        "diario" {
            if ($agora.DayOfWeek -eq [DayOfWeek]::Saturday) { $Tarefa = "cdp-diario-sabado" }
            elseif ($hhmm -ge 2107 -or $hhmm -lt 1000) { $Tarefa = "cdp-diario-reforco" }
            else { $Tarefa = "cdp-diario" }
        }
        "risco" { $Tarefa = if ($hhmm -ge 1603) { "cdp-risco-1603" } else { "cdp-risco-1330" } }
        default { $Tarefa = "cdp-$Skill" }
    }
}
if ($Tarefa -ne "cdp-$Skill" -and -not $Tarefa.StartsWith("cdp-$Skill-")) {
    Write-Error "a tarefa $Tarefa não é da skill $Skill"
    exit 2
}

$extra = @{}   # splatting por tabela: os switches chegam como switches
if ($Ensaio) { $extra["Ensaio"] = $true }
if ($Manual) { $extra["Manual"] = $true }
if ($Seco) { $extra["Seco"] = $true }
$rotina = Join-Path $PSScriptRoot "cdp_rotina.ps1"
& $rotina $Tarefa -Harness claude -ModoPrompt plugin @extra
exit $LASTEXITCODE
