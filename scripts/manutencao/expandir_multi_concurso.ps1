# Expandir banco multi-concurso — rodada agendada.
# Gera lote menor (~150 quest) 3x ao dia respeitando quotas de free tier.
#
# Cronograma sugerido no Task Scheduler:
#   06:00 (bateria matinal, quota Groq/Gemini limpa)
#   14:00 (meio da tarde, apos reset intermediario)
#   22:00 (noturno)

$ErrorActionPreference = 'Continue'
$PROJECT_ROOT = 'c:\Users\USER\Downloads\projeto_prf'
$PYTHON = Join-Path $PROJECT_ROOT 'venv\Scripts\python.exe'

$LOG_DIR = Join-Path $PROJECT_ROOT 'logs'
if (-not (Test-Path $LOG_DIR)) {
    New-Item -ItemType Directory -Path $LOG_DIR | Out-Null
}
$STAMP = Get-Date -Format 'yyyy-MM-dd_HHmm'
$LOG = Join-Path $LOG_DIR "expandir_multi_$STAMP.log"

function Write-Log {
    param([string]$msg)
    $t = Get-Date -Format 'HH:mm:ss'
    "[$t] $msg" | Tee-Object -FilePath $LOG -Append
}

Set-Location $PROJECT_ROOT

Write-Log '=== Inicio: expandir multi-concurso ==='
Write-Log "Log: $LOG"

if (-not (Test-Path $PYTHON)) {
    Write-Log "ERRO: venv nao encontrado em $PYTHON"
    exit 1
}

# 1. Gerar quest\u00f5es (rodada pequena — respeita quota)
Write-Log ''
Write-Log '--- Etapa 1/3: gerar quest\u00f5es multi-concurso (qtd=10/disc) ---'
try {
    & $PYTHON manage.py gerar_bateria_multi_concurso --qtd 10 --batch 5 --delay 2 2>&1 | Tee-Object -FilePath $LOG -Append
} catch {
    Write-Log "EXCEPTION gerar_bateria_multi_concurso: $_"
}

# 2. Gerar justificativas
Write-Log ''
Write-Log '--- Etapa 2/3: gerar justificativas (limit=200) ---'
try {
    & $PYTHON manage.py gerar_justificativas_ia --somente_pendentes --somente_ia --limit 200 --delay 2 2>&1 | Tee-Object -FilePath $LOG -Append
} catch {
    Write-Log "EXCEPTION gerar_justificativas_ia: $_"
}

# 3. Aprovar em lote as com justificativa
Write-Log ''
Write-Log '--- Etapa 3/3: aprovar em lote ---'
try {
    & $PYTHON scripts/manutencao/aprovar_ia_com_just.py 2>&1 | Tee-Object -FilePath $LOG -Append
} catch {
    Write-Log "EXCEPTION aprovar_ia_com_just: $_"
}

Write-Log ''
Write-Log '=== Fim ==='
