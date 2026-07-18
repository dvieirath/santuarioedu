"""
Métricas de uso de IA por provider (armazenadas em cache Django).

Contadores por dia:
  ia:{provider}:ok:{YYYYMMDD}      → chamadas bem-sucedidas
  ia:{provider}:tokens:{YYYYMMDD}  → total de tokens consumidos
  ia:{provider}:quota:{YYYYMMDD}   → vezes que estourou quota (429)
  ia:{provider}:err:{YYYYMMDD}     → outros erros

TTL 25h (garante cobertura da janela do dia mesmo em edge cases de fuso).

Uso na leitura (view metricas_negocio):
    from quiz.ai_metrics import stats_do_dia
    stats = stats_do_dia()  # dict {'groq': {ok, tokens, quota, err}, 'gemini': {...}}
"""
from datetime import datetime, timedelta

from django.core.cache import cache


PROVIDERS = ('groq', 'gemini')
METRICAS = ('ok', 'tokens', 'quota', 'err')

# Cap teórico free tier (para semáforo)
CAP_DIARIO_TOKENS = {
    'groq':   100_000,
    'gemini': 1_000_000,  # aproximado, gemini-flash-lite tem cap generoso
}
CAP_DIARIO_REQ = {
    'groq':   6_000,
    'gemini': 1_500,
}


def _hoje():
    return datetime.now().strftime('%Y%m%d')


def _key(provider, tipo, dia=None):
    return f'ia:{provider}:{tipo}:{dia or _hoje()}'


def registrar(provider: str, ok: bool, tokens: int = 0, quota: bool = False):
    """Chamado dentro do gerar() de cada provider após cada tentativa."""
    dia = _hoje()
    try:
        if ok:
            cache.set(_key(provider, 'ok', dia),
                      (cache.get(_key(provider, 'ok', dia)) or 0) + 1, 60 * 60 * 25)
            if tokens:
                cache.set(_key(provider, 'tokens', dia),
                          (cache.get(_key(provider, 'tokens', dia)) or 0) + tokens, 60 * 60 * 25)
        elif quota:
            cache.set(_key(provider, 'quota', dia),
                      (cache.get(_key(provider, 'quota', dia)) or 0) + 1, 60 * 60 * 25)
        else:
            cache.set(_key(provider, 'err', dia),
                      (cache.get(_key(provider, 'err', dia)) or 0) + 1, 60 * 60 * 25)
    except Exception:
        # Nunca falha o pipeline de IA por causa de métrica
        pass


def stats_do_dia(dia=None):
    """Retorna dict {provider: {ok, tokens, quota, err, pct_tokens, pct_req}}."""
    dia = dia or _hoje()
    out = {}
    for p in PROVIDERS:
        vals = {m: (cache.get(_key(p, m, dia)) or 0) for m in METRICAS}
        cap_t = CAP_DIARIO_TOKENS.get(p, 1)
        cap_r = CAP_DIARIO_REQ.get(p, 1)
        vals['pct_tokens'] = min(100, round(vals['tokens'] / cap_t * 100, 1))
        vals['pct_req']    = min(100, round(vals['ok']     / cap_r * 100, 1))
        vals['cap_tokens'] = cap_t
        vals['cap_req']    = cap_r
        # Semáforo visual
        max_pct = max(vals['pct_tokens'], vals['pct_req'])
        if max_pct >= 90:
            vals['status'] = 'critico'
        elif max_pct >= 70:
            vals['status'] = 'atencao'
        else:
            vals['status'] = 'ok'
        out[p] = vals
    return out


def stats_ultimos_dias(n=7):
    """Retorna série dos últimos n dias — útil para gráfico de tendência."""
    hoje = datetime.now().date()
    dias = []
    for i in range(n - 1, -1, -1):
        d = (hoje - timedelta(days=i)).strftime('%Y%m%d')
        dias.append({'dia': d, 'stats': stats_do_dia(d)})
    return dias
