<#
CDP — Cabra da Peste: executor universal de uma rotina em qualquer harness (Claude Code, Codex,
Gemini CLI, Antigravity ou outro), para o Agendador de Tarefas do Windows ou à mão.

Uso:
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\cdp_rotina.ps1 cdp-diario -Harness claude
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\cdp_rotina.ps1 cdp-status -Harness codex -Seco
Parâmetros: -Harness claude|codex|gemini|agy|custom (aceita claude-code, antigravity, outro) ·
  -ModoPrompt neutro|skill|plugin · -Publicacao agente|executor · -Ensaio · -Manual · -SemGate · -Seco
Mesma lógica e mesmos códigos de scripts/cdp_rotina.sh:
  agente   (padrão; Claude Code, Gemini CLI, Antigravity, custom): prévia do gate sem a trava; a
           mente segue o prompt inteiro (gate --adquirir → sincronizar → roteiro → publicar).
  executor (padrão no Codex, cujo sandbox deixa .git só de leitura): este script roda o gate com a
           trava, `cdp sincronizar`, o roteiro pela mente, `cdp publicar` e libera a trava.
Códigos: 0 ok ou nada a fazer · 1 falha do harness · 2 uso · 3 sincronização parou ou publicação
sem push · 4 sem progresso · 75 trava local ocupada · 78 configuração.
#>
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidatePattern("^cdp-[a-z0-9-]+$")]
    [string]$Tarefa,
    [ValidateSet("claude", "claude-code", "codex", "gemini", "agy", "antigravity", "custom", "outro", "")]
    [string]$Harness = "",
    [ValidateSet("neutro", "skill", "plugin")]
    [string]$ModoPrompt = "neutro",
    [ValidateSet("agente", "executor", "")]
    [string]$Publicacao = "",
    [switch]$Ensaio,
    [switch]$Manual,
    [switch]$SemGate,
    [switch]$Seco
)
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:Path = "$env:USERPROFILE\.local\bin;$env:APPDATA\npm;$env:Path"

function Normaliza([string]$h) {
    switch ($h) {
        { $_ -in @("claude", "claude-code") } { return "claude" }
        "codex" { return "codex" }
        "gemini" { return "gemini" }
        { $_ -in @("agy", "antigravity") } { return "agy" }
        { $_ -in @("custom", "outro") } { return "custom" }
        default { return "" }
    }
}
if (-not $Harness) {
    $Harness = Normaliza $(if ($env:CDP_HARNESS) { $env:CDP_HARNESS } else { "claude-code" })
    if (-not $Harness) { $Harness = "custom" }
} else { $Harness = Normaliza $Harness }
if (-not $env:CDP_HARNESS) {
    $env:CDP_HARNESS = @{ claude = "claude-code"; codex = "codex"; gemini = "gemini";
                          agy = "antigravity"; custom = "outro" }[$Harness]
}
if (-not $Publicacao) { $Publicacao = if ($Harness -eq "codex") { "executor" } else { "agente" } }
if ($SemGate -and $Publicacao -ne "executor") { Write-Error "-SemGate exige -Publicacao executor"; exit 2 }
if ($Publicacao -eq "executor" -and $ModoPrompt -ne "neutro") { Write-Error "-Publicacao executor exige -ModoPrompt neutro"; exit 2 }

$logDir = Join-Path $Root "logs\cdp"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$run = "${Tarefa}_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
$log = Join-Path $logDir "$run.log"
$promptFile = Join-Path $logDir "$run.prompt.md"
$gateFile = Join-Path $logDir "$run.gate.json"
$lock = Join-Path $logDir ".lock"
function Log([string]$msg) {
    $linha = "== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz') $msg"
    Write-Output $linha
    $linha | Out-File -FilePath $log -Append -Encoding utf8
}
function LerJson([string]$arquivo) {
    try { return Get-Content $arquivo -Raw -Encoding utf8 | ConvertFrom-Json } catch { return $null }
}

$waitMin = 0
if ($env:CDP_LOCK_WAIT_MIN) { $waitMin = [int]$env:CDP_LOCK_WAIT_MIN }
elseif ($Tarefa -match "^cdp-(semanal|diario|cobertura)") { $waitMin = 60 }

$temTrava = $false
$trava = ""
function LiberarTrava {
    if ($script:trava) { & uv run python -m cdp trava liberar --id $script:trava | Out-Null; $script:trava = "" }
}
if (-not $Seco) {
    if ((Test-Path $lock) -and ((Get-Item $lock).LastWriteTime -lt (Get-Date).AddHours(-6))) {
        Remove-Item $lock -Force -Recurse -ErrorAction SilentlyContinue   # trava órfã (> 6 h)
    }
    $deadline = (Get-Date).AddMinutes($waitMin)
    while ($true) {
        try { New-Item -ItemType Directory -Path $lock -ErrorAction Stop | Out-Null; $temTrava = $true; break }
        catch {
            if ((Get-Date) -ge $deadline) {
                Log "outra rotina do CDP em execução ($lock) após $waitMin min: $Tarefa não iniciada"
                exit 75
            }
            Start-Sleep -Seconds 30
        }
    }
}
try {
    if (-not $Seco) {
        Log "rotina $Tarefa — harness $Harness — publicação $Publicacao — início"
        & uv sync --frozen --extra dev --extra ai -q
        if ($LASTEXITCODE -ne 0) { Log "uv sync falhou"; exit 78 }
    }
    $extra = @()
    if ($Manual) { $extra += "--manual" }
    if ($Ensaio) { $extra += "--ensaio" }
    $grava = $false
    $timeoutMin = ""
    $execucao = ""
    $antes = @()
    if (Test-Path ".cdp\execucoes") { $antes = @(Get-ChildItem ".cdp\execucoes\*.json" | ForEach-Object { $_.Name }) }
    if (-not $SemGate -and -not $Seco) {
        $modoGate = if ($Publicacao -eq "executor") { "--adquirir" } else { "--previa" }
        & uv run python -m cdp rotinas gate --tarefa $Tarefa $modoGate @extra | Out-File -FilePath $gateFile -Encoding utf8
        $rc = $LASTEXITCODE
        $gate = LerJson $gateFile
        if ($rc -eq 10) { Log "sem execução: $($gate.motivo)"; exit 0 }
        elseif ($rc -ne 0) { Log "gate com erro de configuração (código $rc)"; exit 78 }
        Log "gate: executar — $($gate.motivo)"
        $grava = [bool]$gate.grava
        $timeoutMin = "$($gate.timeout_min)"
        if ($Publicacao -eq "executor") {
            if ($gate.trava -and $gate.trava.id) { $trava = "$($gate.trava.id)" }
            $env:CDP_TRAVA_ID = $trava
            $execucao = "$($gate.execucao)"
            $env:CDP_EXECUCAO = $execucao
            if ($grava) {
                $sincFile = Join-Path $logDir "$run.sincronizar.json"
                & uv run python -m cdp sincronizar --executar | Out-File -FilePath $sincFile -Encoding utf8
                if ($LASTEXITCODE -ne 0) { Log "sincronização parou: $((LerJson $sincFile).motivo)"; exit 3 }
            }
        }
    }
    $pre = (& uv run python -m cdp rotinas pre --tarefa $Tarefa | Select-Object -Last 1)
    if ($pre -and -not $Seco) {
        if ($pre -like "uv run python -m cdp *") {
            Log "pré-comando: $pre"
            $partes = $pre.Split(" ")
            & $partes[0] $partes[1..($partes.Length - 1)]
        } else { Log "pré-comando recusado (não é um comando do cdp): $pre" }
    }
    & uv run python -m cdp rotinas prompt --tarefa $Tarefa --harness $Harness --modo $ModoPrompt --publicacao $Publicacao @extra |
        Out-File -FilePath $promptFile -Encoding utf8
    if ($LASTEXITCODE -ne 0) { Log "prompt falhou"; exit 78 }
    $texto = Get-Content $promptFile -Raw -Encoding utf8
    $final = Join-Path $logDir "$run.final.md"
    if ($Harness -eq "agy" -and -not $timeoutMin) {
        $lista = & uv run python -m cdp rotinas listar --formato json | Out-String | ConvertFrom-Json
        $timeoutMin = "$(($lista | Where-Object { $_.id -eq $Tarefa }).timeout_min)"
    }
    switch ($Harness) {
        "claude" {
            $exe = if ($env:CDP_CLAUDE_BIN) { $env:CDP_CLAUDE_BIN } else { "claude" }
            $mode = if ($env:CDP_PERMISSION_MODE) { $env:CDP_PERMISSION_MODE } else { "acceptEdits" }
            $args2 = @("-p", $texto, "--permission-mode", $mode, "--output-format", "text")
            if ($env:CDP_CLAUDE_ARGS) { $args2 += $env:CDP_CLAUDE_ARGS.Split(" ") }
        }
        "codex" {
            $exe = "codex"
            $sb = if ($env:CDP_CODEX_SANDBOX) { $env:CDP_CODEX_SANDBOX } else { "workspace-write" }
            $args2 = @("exec", "--sandbox", $sb, "-c", "sandbox_workspace_write.network_access=true",
                       "--skip-git-repo-check", "-o", $final, $texto)
        }
        "gemini" { $exe = "gemini"; $args2 = @("-p", $texto, "--approval-mode", "yolo", "--output-format", "text") }
        "agy" {
            # Experimental: confira as opções com `agy --help` (padrão do --print-timeout: 5 min).
            $exe = "agy"
            $to = if ($env:CDP_AGY_TIMEOUT) { $env:CDP_AGY_TIMEOUT } elseif ($timeoutMin) { "${timeoutMin}m" } else { "60m" }
            $args2 = @("-p", $texto, "--dangerously-skip-permissions", "--print-timeout", $to)
        }
        "custom" {
            if (-not $env:CDP_HARNESS_CMD) { Log "defina CDP_HARNESS_CMD para o harness custom"; exit 78 }
            $exe = "powershell"; $args2 = @("-NoProfile", "-Command", $env:CDP_HARNESS_CMD.Replace("{prompt_file}", $promptFile))
        }
    }
    if ($Seco) {
        Write-Output "harness: $exe"
        Write-Output "publicacao: $Publicacao"
        Write-Output "prompt: $promptFile"
        exit 0
    }
    Log "harness: $exe (prompt em $promptFile)"
    try { & $exe @args2 2>&1 | Out-File -FilePath $log -Append -Encoding utf8; $hrc = $LASTEXITCODE }
    catch [System.Management.Automation.CommandNotFoundException] { Log "harness não encontrado: $exe"; exit 78 }
    Log "harness terminou — código $hrc"

    $pubrc = 0
    if ($Publicacao -eq "executor") {
        if ($SemGate) {
            if ($hrc -ne 0) { exit 1 }
            Log "fim (publicação pelo workflow)"
            exit 0
        }
        if ($grava -and -not $Ensaio) {
            $pubFile = Join-Path $logDir "$run.publicar.json"
            $pubArgs = @("--tarefa", $Tarefa, "--mensagem-automatica", "--execucao", $execucao)
            if ($trava) { $pubArgs += @("--trava", $trava) }
            & uv run python -m cdp publicar @pubArgs | Out-File -FilePath $pubFile -Encoding utf8
            $pubrc = $LASTEXITCODE
            Log "publicação (código $pubrc): $((LerJson $pubFile).motivo)"
        }
        LiberarTrava
        $eid = $execucao
    } else {
        # A trava distribuída é da mente (gate --adquirir); se ela não liberou, este script libera.
        $regs = @()
        if (Test-Path ".cdp\execucoes") {
            foreach ($f in Get-ChildItem ".cdp\execucoes\*.json") {
                if ($antes -contains $f.Name) { continue }
                $d = LerJson $f.FullName
                if ($d -and $d.tarefa -eq $Tarefa) { $regs += [pscustomobject]@{ inicio = "$($d.inicio)"; id = $f.BaseName; trava = "$($d.trava)" } }
            }
        }
        $ult = $regs | Sort-Object inicio | Select-Object -Last 1
        $eid = ""
        if ($ult) { $eid = $ult.id; $trava = $ult.trava; LiberarTrava }
    }
    if ($hrc -ne 0) { exit 1 }
    if ($pubrc -ne 0 -and $pubrc -ne 6) { exit 3 }
    if ($eid -and (Test-Path ".cdp\execucoes\$eid.json")) {
        & uv run python -m cdp rotinas conferir --tarefa $Tarefa --execucao $eid | Out-Null
        if ($LASTEXITCODE -eq 4) { Log "sem progresso: as mesmas pendências continuam e nenhum commit novo"; exit 4 }
    }
    Log "fim"
    exit 0
}
finally {
    LiberarTrava
    if ($temTrava) { Remove-Item $lock -Force -Recurse -ErrorAction SilentlyContinue }
}
