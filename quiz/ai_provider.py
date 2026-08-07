"""
Camada unificada de IA com múltiplos providers + fallback automático.

Ordem padrão (configurável via AI_PROVIDER_ORDER no .env):
  1. Groq      — Llama 3.3 70B, 30 req/min grátis, MUITO rápido
  2. Gemini    — Google, 1500 req/dia grátis
  3. (futuro)  — OpenRouter, Mistral, etc.

Uso simples:
    from quiz.ai_provider import gerar_conteudo
    texto = gerar_conteudo('Explique a Lei 9.503/97')
    dados = gerar_conteudo('Liste 3 capitais', json_mode=True)

Recursos:
  - Fallback automático (se Groq quebra, tenta Gemini)
  - Cache de quotaResourceExhausted: pula provider por 60s
  - Logs detalhados (uso de tokens, latência)
  - JSON mode robusto
"""
import json as _json
import logging
import time
import urllib.error
import urllib.request
from typing import Optional

from django.conf import settings


logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────
# Exceções
# ──────────────────────────────────────────────────────────────────────────
class AIError(Exception):
    """Erro genérico de provider de IA."""


class AIQuotaExceeded(AIError):
    """Quota do provider esgotada — tenta o próximo."""


class AIBadResponse(AIError):
    """Resposta veio mas não consegui interpretar."""


# ──────────────────────────────────────────────────────────────────────────
# Providers
# ──────────────────────────────────────────────────────────────────────────
class BaseProvider:
    name = 'base'
    _last_quota_error = 0  # timestamp pra cooldown

    @classmethod
    def disponivel(cls) -> bool:
        """True se este provider está pronto pra usar."""
        return False

    @classmethod
    def em_cooldown(cls) -> bool:
        """True se acabou de tomar 429 — espera 60s pra tentar de novo."""
        return (time.time() - cls._last_quota_error) < 60

    @classmethod
    def marcar_quota_excedida(cls):
        cls._last_quota_error = time.time()

    @classmethod
    def gerar(cls, prompt: str, json_mode: bool = False,
              max_tokens: int = 2048, temperature: float = 0.7) -> str:
        raise NotImplementedError


# ─── Groq ────────────────────────────────────────────────────────────────
class GroqProvider(BaseProvider):
    name = 'groq'
    URL = 'https://api.groq.com/openai/v1/chat/completions'
    DEFAULT_MODEL = 'llama-3.3-70b-versatile'

    @classmethod
    def disponivel(cls) -> bool:
        return bool(getattr(settings, 'GROQ_API_KEY', '')) and not cls.em_cooldown()

    @classmethod
    def gerar(cls, prompt, json_mode=False, max_tokens=2048, temperature=0.7):
        api_key = settings.GROQ_API_KEY
        modelo = getattr(settings, 'GROQ_MODEL', cls.DEFAULT_MODEL)
        # Timeout global: em web request, 30s. Em management command (backend),
        # settings.AI_TIMEOUT_LONGO permite 120s pra batchs.
        timeout_s = int(getattr(settings, 'AI_TIMEOUT_SECONDS', 30))
        if json_mode:
            prompt = prompt + '\n\nResponda APENAS em JSON válido.'
        payload = {
            'model': modelo,
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': temperature,
            'max_tokens': max_tokens,
        }
        if json_mode:
            payload['response_format'] = {'type': 'json_object'}

        req = urllib.request.Request(
            cls.URL,
            data=_json.dumps(payload).encode('utf-8'),
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
                'User-Agent': 'SantuarioEdu/1.0 (Python urllib)',  # evita 1010 Cloudflare
            },
        )
        from .ai_metrics import registrar as _mregistrar

        inicio = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                data = _json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='replace')[:300]
            if e.code == 429:
                cls.marcar_quota_excedida()
                _mregistrar('groq', ok=False, quota=True)
                raise AIQuotaExceeded(f'Groq 429: {body}')
            _mregistrar('groq', ok=False)
            raise AIError(f'Groq HTTP {e.code}: {body}')
        except Exception as e:
            _mregistrar('groq', ok=False)
            raise AIError(f'Groq erro: {e}')

        latencia = (time.time() - inicio) * 1000
        try:
            texto = data['choices'][0]['message']['content']
            uso = data.get('usage', {})
            tokens_usados = int(uso.get('total_tokens') or 0)
            _mregistrar('groq', ok=True, tokens=tokens_usados)
            logger.info(f'[Groq] {tokens_usados or "?"} tokens · {latencia:.0f}ms')
            _alerta_se_lento('groq', latencia)
            return texto
        except (KeyError, IndexError) as e:
            _mregistrar('groq', ok=False)
            raise AIBadResponse(f'Groq resposta inesperada: {e}')


# ─── Gemini ──────────────────────────────────────────────────────────────
class GeminiProvider(BaseProvider):
    name = 'gemini'
    DEFAULT_MODEL = 'gemini-3.1-flash-lite'

    @classmethod
    def disponivel(cls) -> bool:
        return bool(getattr(settings, 'GEMINI_API_KEY', '')) and not cls.em_cooldown()

    @classmethod
    def gerar(cls, prompt, json_mode=False, max_tokens=2048, temperature=0.7):
        # SDK novo (google-genai) — o antigo (google.generativeai) foi
        # deprecated em 2024 e nao recebe mais updates. Fallback pra
        # garantir compat em ambiente ainda com pacote antigo.
        try:
            from google import genai as _genai_new
            from google.genai import types as _genai_types
            _sdk = 'new'
        except ImportError:
            try:
                import google.generativeai as _genai_old  # noqa: F401
                _sdk = 'old'
            except Exception as e:
                raise AIError(f'Gemini SDK não disponível: {e}')

        api_key = settings.GEMINI_API_KEY
        modelo = getattr(settings, 'GEMINI_MODEL', cls.DEFAULT_MODEL)

        if json_mode:
            prompt = prompt + '\n\nResponda APENAS em JSON válido, sem markdown.'

        from .ai_metrics import registrar as _mregistrar

        inicio = time.time()
        try:
            if _sdk == 'new':
                client = _genai_new.Client(api_key=api_key)
                resp = client.models.generate_content(
                    model=modelo,
                    contents=prompt,
                    config=_genai_types.GenerateContentConfig(
                        temperature=temperature,
                        max_output_tokens=max_tokens,
                    ),
                )
            else:
                # Fallback SDK antigo (deprecated)
                _genai_old.configure(api_key=api_key)
                _model = _genai_old.GenerativeModel(modelo)
                resp = _model.generate_content(
                    prompt,
                    generation_config={
                        'temperature': temperature,
                        'max_output_tokens': max_tokens,
                    },
                )
        except Exception as e:
            tipo = type(e).__name__
            if 'ResourceExhausted' in tipo or '429' in str(e):
                cls.marcar_quota_excedida()
                _mregistrar('gemini', ok=False, quota=True)
                raise AIQuotaExceeded(f'Gemini quota esgotada')
            _mregistrar('gemini', ok=False)
            raise AIError(f'Gemini erro {tipo}: {str(e)[:200]}')

        latencia = (time.time() - inicio) * 1000
        try:
            texto = resp.text or ''
            # Gemini não retorna tokens na resposta padrão — estimamos ~4 chars/token
            tokens_est = max(1, (len(prompt) + len(texto)) // 4)
            _mregistrar('gemini', ok=True, tokens=tokens_est)
            logger.info(f'[Gemini] ~{tokens_est} tokens · {latencia:.0f}ms')
            _alerta_se_lento('gemini', latencia)
            return texto
        except Exception as e:
            _mregistrar('gemini', ok=False)
            raise AIBadResponse(f'Gemini resposta inesperada: {e}')


# ─── Alerta de latência ──────────────────────────────────────────────────
def _alerta_se_lento(provider: str, latencia_ms: float):
    """Se IA passou de X ms, notifica admin (dedup por 30min).
    Threshold configurável via settings.AI_LATENCIA_ALERTA_MS (default 15000)."""
    threshold = int(getattr(settings, 'AI_LATENCIA_ALERTA_MS', 15000))
    if latencia_ms < threshold:
        return
    try:
        from django.core.cache import cache
        key = f'ia_lento:{provider}'
        if cache.get(key):
            return
        cache.set(key, 1, 1800)  # 30 min dedup
        from .notifications import notificar_admin
        notificar_admin(
            'media',
            titulo=f'IA {provider} lenta',
            corpo=f'Última chamada demorou {latencia_ms/1000:.1f}s (threshold: {threshold/1000:.0f}s). '
                  'Se persistir, considere upgrade de tier ou fallback.',
            meta=f'provider={provider}',
        )
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────────
# Orquestrador
# ──────────────────────────────────────────────────────────────────────────
PROVIDERS = {
    'groq':   GroqProvider,
    'gemini': GeminiProvider,
}


def _ordem_providers():
    return getattr(settings, 'AI_PROVIDER_ORDER', ['groq', 'gemini'])


def _cap_diario_atingido(usuario) -> bool:
    """Verifica se usuário estourou o cap diário TOTAL de chamadas IA (defesa em profundidade)."""
    if not usuario or not usuario.is_authenticated:
        return False
    try:
        from django.core.cache import cache
        from django.conf import settings
        # Cap generoso pra não incomodar user real, mas trava abuso extremo
        cap_free = int(getattr(settings, 'IA_CAP_DIARIO_FREE', 50))
        cap_pro  = int(getattr(settings, 'IA_CAP_DIARIO_PRO', 200))

        # Descobre plano
        try:
            from quiz.limits import get_plano
            plano = get_plano(usuario)
        except Exception:
            plano = 'gratuito'
        cap = cap_pro if plano in ('pro', 'premium') else cap_free

        # Contador diário em cache
        from datetime import datetime
        hoje = datetime.now().strftime('%Y%m%d')
        key = f'ia_diario:{usuario.id}:{hoje}'
        atual = cache.get(key, 0)
        if atual >= cap:
            return True
        cache.set(key, atual + 1, 86400)  # expira em 24h
        return False
    except Exception:
        return False


def gerar_conteudo(prompt: str, json_mode: bool = False,
                   max_tokens: int = 2048, temperature: float = 0.7,
                   provider: Optional[str] = None,
                   usuario=None) -> str:
    """
    Função principal: tenta cada provider em ordem até funcionar.

    Args:
        prompt: texto da pergunta/comando
        json_mode: se True, pede saída em JSON
        max_tokens: limite de tokens da resposta
        temperature: 0.0 = determinístico, 1.0 = criativo
        provider: forçar um provider específico ('groq' ou 'gemini')

    Returns:
        Texto gerado pela IA

    Raises:
        AIError: nenhum provider funcionou
    """
    # ── Defesa contra prompt injection óbvio ──
    _PATTERNS_SUSPEITOS = [
        'ignore previous', 'ignore all previous', 'disregard',
        'ignore anterior', 'esqueça as instruções', 'esqueça tudo',
        'you are now', 'você agora é', 'act as', 'jailbreak',
        'system prompt', 'reveal your prompt', 'dev mode',
    ]
    prompt_lower = prompt.lower()
    for pat in _PATTERNS_SUSPEITOS:
        if pat in prompt_lower:
            logger.warning(f'Prompt suspeito bloqueado: contém "{pat}"')
            raise AIError('Prompt contém padrão suspeito. Se for uso legítimo, reformule.')
    if len(prompt) > 15000:
        raise AIError('Prompt muito longo. Limite: 15000 caracteres.')

    # ── Cap financeiro: se usuário estourou o limite diário, bloqueia ──
    if usuario and _cap_diario_atingido(usuario):
        raise AIQuotaExceeded(
            f'Você atingiu o limite diário de uso de IA. '
            f'Tente novamente amanhã ou faça upgrade para PRO.'
        )

    ordem = [provider] if provider else _ordem_providers()
    erros = []

    for nome in ordem:
        cls = PROVIDERS.get(nome)
        if not cls or not cls.disponivel():
            erros.append(f'{nome}: indisponível')
            continue
        try:
            return cls.gerar(prompt, json_mode=json_mode,
                             max_tokens=max_tokens, temperature=temperature)
        except AIQuotaExceeded as e:
            erros.append(f'{nome}: quota esgotada')
            logger.warning(f'Provider {nome} sem quota, tentando próximo: {e}')
            continue
        except AIError as e:
            erros.append(f'{nome}: {e}')
            logger.warning(f'Provider {nome} falhou: {e}')
            continue

    raise AIError(f'Todos os providers falharam: {" | ".join(erros)}')


def gerar_json(prompt: str, **kwargs) -> dict:
    """Atalho que retorna dict já parseado (em vez de string)."""
    import re
    texto = gerar_conteudo(prompt, json_mode=True, **kwargs)
    # Limpa markdown fences se vierem
    texto = re.sub(r'^```(?:json)?\s*', '', texto.strip())
    texto = re.sub(r'\s*```$', '', texto)
    try:
        return _json.loads(texto)
    except _json.JSONDecodeError as e:
        raise AIBadResponse(f'JSON inválido: {e}\nRecebido: {texto[:300]}')


def listar_providers_disponiveis() -> list:
    """Diagnostico — quais providers estão prontos pra usar."""
    return [
        {'nome': nome, 'disponivel': cls.disponivel(),
         'em_cooldown': cls.em_cooldown()}
        for nome, cls in PROVIDERS.items()
    ]
