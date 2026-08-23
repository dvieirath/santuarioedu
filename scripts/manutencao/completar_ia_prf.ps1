# Completa a bateria IA PRF que ficou parcial por quota Gemini esgotada.
#
# Sequencia:
#   1. Rodar gerar_justificativas_ia ate 800 chamadas (ate quota estourar de novo)
#   2. Aprovar em lote as IA que ganharem justificativa (via aprovar_ia_com_just.py)
#
# Uso manual (opcional):
#   powershell -ExecutionPolicy Bypass -File scripts/manutencao/completar_ia_prf.ps1
#
# Agendado no Windows Task Scheduler pra rodar 24h apos a bateria original
# (quota Gemini free-tier reseta 1x/dia).

$ErrorActionPreference = 'Continue'
$PROJECT_ROOT = 'c:\Users\USER\Downloads\projeto_prf'
$PYTHON = Join-Path $PROJECT_ROOT 'venv\Scripts\python.exe'

# Log em diretorio dedicado
$LOG_DIR = Join-Path $PROJECT_ROOT 'logs'
if (-not (Test-Path $LOG_DIR)) {
    New-Item -ItemType Directory -Path $LOG_DIR | Out-Null
}
$STAMP = Get-Date -Format 'yyyy-MM-dd_HHmm'
$LOG = Join-Path $LOG_DIR "completar_ia_prf_$STAMP.log"

function Write-Log {
    param([string]$msg)
    $t = Get-Date -Format 'HH:mm:ss'
    "[$t] $msg" | Tee-Object -FilePath $LOG -Append
}

Set-Location $PROJECT_ROOT

Write-Log '=== Inicio: completar bateria IA PRF ==='
Write-Log "Python:  $PYTHON"
Write-Log "Log:     $LOG"

# Sanity check
if (-not (Test-Path $PYTHON)) {
    Write-Log "ERRO: venv nao encontrado em $PYTHON"
    exit 1
}

# 1. Justificativas
Write-Log ''
Write-Log '--- Etapa 1/2: gerar_justificativas_ia (limit=800) ---'
try {
    & $PYTHON manage.py gerar_justificativas_ia --somente_pendentes --somente_ia --limit 800 --delay 1.5 2>&1 | Tee-Object -FilePath $LOG -Append
    if ($LASTEXITCODE -ne 0) {
        Write-Log "gerar_justificativas_ia terminou com exit $LASTEXITCODE (nao fatal, seguindo)"
    }
} catch {
    Write-Log "EXCEPTION em gerar_justificativas_ia: $_"
}

# 2. Aprovar em lote
Write-Log ''
Write-Log '--- Etapa 2/2: aprovar em lote as IA com justificativa ---'
try {
    & $PYTHON scripts/manutencao/aprovar_ia_com_just.py 2>&1 | Tee-Object -FilePath $LOG -Append
    if ($LASTEXITCODE -ne 0) {
        Write-Log "aprovar_ia_com_just.py terminou com exit $LASTEXITCODE"
    }
} catch {
    Write-Log "EXCEPTION em aprovar_ia_com_just: $_"
}

Write-Log ''
Write-Log '=== Fim ==='
