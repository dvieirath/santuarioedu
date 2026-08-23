"""
Testes dos 4 providers de IA (Groq, Gemini, Cerebras, OpenRouter).

Nao chamam APIs reais — mockam urllib.request.urlopen + google.genai.Client
pra validar:
  1. Estrutura do payload enviado (params corretos por provider)
  2. Parsing da resposta OK
  3. Tratamento de 429 (quota) e outros erros
  4. Fallback entre providers do orquestrador `gerar_conteudo`
  5. Fallback interno do OpenRouter (nemotron -> gemma -> super)
  6. Retry TPM inteligente do Groq (parseia "try again in Xs")
  7. Reasoning models: envia max_completion_tokens + reasoning_effort
"""
import json
from io import BytesIO
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError

from django.test import TestCase, override_settings


def _mock_http_response(payload_dict):
    """Cria mock de urlopen context manager que retorna payload_dict."""
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload_dict).encode('utf-8')
    ctx = MagicMock()
    ctx.__enter__.return_value = resp
    ctx.__exit__.return_value = None
    return ctx


def _mock_http_error(code, body_dict=None):
    body = json.dumps(body_dict or {'error': {'message': 'x'}}).encode()
    return HTTPError('http://x', code, 'err', {}, BytesIO(body))


# ─── GROQ ────────────────────────────────────────────────────────────────
@override_settings(GROQ_API_KEY='fake-groq-key', GROQ_MODEL='openai/gpt-oss-120b')
class GroqProviderTests(TestCase):
    def setUp(self):
        from quiz.ai_provider import GroqProvider
        GroqProvider._last_quota_error = 0  # limpa cooldown entre testes

    def test_disponivel_com_key(self):
        from quiz.ai_provider import GroqProvider
        self.assertTrue(GroqProvider.disponivel())

    def test_reasoning_model_envia_params_corretos(self):
        """gpt-oss-* precisa de max_completion_tokens + reasoning_effort."""
        from quiz.ai_provider import GroqProvider
        payload_capturado = {}

        def fake_urlopen(req, timeout=None):
            payload_capturado.update(json.loads(req.data))
            return _mock_http_response({
                'choices': [{'message': {'content': 'resposta OK'}}],
                'usage': {'total_tokens': 42},
            })

        with patch('urllib.request.urlopen', side_effect=fake_urlopen):
            r = GroqProvider.gerar('teste', max_tokens=500)
        self.assertEqual(r, 'resposta OK')
        # Verifica que enviou os params certos
        self.assertIn('max_completion_tokens', payload_capturado)
        self.assertEqual(payload_capturado['max_completion_tokens'], 800)  # 500 + 300
        self.assertEqual(payload_capturado['reasoning_effort'], 'low')
        self.assertNotIn('max_tokens', payload_capturado)

    @override_settings(GROQ_MODEL='llama-3.3-70b')
    def test_modelo_normal_usa_max_tokens(self):
        from quiz.ai_provider import GroqProvider
        payload_capturado = {}

        def fake_urlopen(req, timeout=None):
            payload_capturado.update(json.loads(req.data))
            return _mock_http_response({
                'choices': [{'message': {'content': 'ok'}}],
                'usage': {'total_tokens': 10},
            })

        with patch('urllib.request.urlopen', side_effect=fake_urlopen):
            GroqProvider.gerar('teste', max_tokens=500)
        self.assertIn('max_tokens', payload_capturado)
        self.assertEqual(payload_capturado['max_tokens'], 500)
        self.assertNotIn('max_completion_tokens', payload_capturado)
        self.assertNotIn('reasoning_effort', payload_capturado)

    def test_retry_inteligente_tpm(self):
        """Se 429 diz 'try again in Xs', aguarda e reenvia (max 2 retries)."""
        from quiz.ai_provider import GroqProvider
        chamadas = [0]

        def fake_urlopen(req, timeout=None):
            chamadas[0] += 1
            if chamadas[0] < 2:
                raise _mock_http_error(429, {
                    'error': {'message': 'Rate limit. Please try again in 2.5s'},
                })
            return _mock_http_response({
                'choices': [{'message': {'content': 'ok'}}],
                'usage': {'total_tokens': 10},
            })

        with patch('urllib.request.urlopen', side_effect=fake_urlopen), \
             patch('time.sleep') as mock_sleep:
            r = GroqProvider.gerar('teste', max_tokens=100)
        self.assertEqual(r, 'ok')
        self.assertEqual(chamadas[0], 2)  # 1 falha + 1 sucesso
        # sleep chamado com ~3.0s (2.5 + 0.5 folga)
        mock_sleep.assert_called_once()
        wait = mock_sleep.call_args[0][0]
        self.assertAlmostEqual(wait, 3.0, delta=0.6)

    def test_quota_esgotada_apos_retries(self):
        """Apos 2 retries com 429, levanta AIQuotaExceeded."""
        from quiz.ai_provider import GroqProvider, AIQuotaExceeded

        def fake_urlopen(req, timeout=None):
            raise _mock_http_error(429, {
                'error': {'message': 'try again in 1.0s'},
            })

        with patch('urllib.request.urlopen', side_effect=fake_urlopen), \
             patch('time.sleep'):
            with self.assertRaises(AIQuotaExceeded):
                GroqProvider.gerar('teste', max_tokens=100)


# ─── CEREBRAS ────────────────────────────────────────────────────────────
@override_settings(CEREBRAS_API_KEY='fake-cerebras', CEREBRAS_MODEL='llama-3.3-70b')
class CerebrasProviderTests(TestCase):
    def setUp(self):
        from quiz.ai_provider import CerebrasProvider
        CerebrasProvider._last_quota_error = 0

    def test_402_payment_required_vira_quota_exceeded(self):
        """Conta sem billing retorna 402 — deve virar cooldown, nao AIError generico."""
        from quiz.ai_provider import CerebrasProvider, AIQuotaExceeded

        def fake_urlopen(req, timeout=None):
            raise _mock_http_error(402, {
                'message': 'Payment required', 'code': 'payment_required_error',
            })

        with patch('urllib.request.urlopen', side_effect=fake_urlopen):
            with self.assertRaises(AIQuotaExceeded):
                CerebrasProvider.gerar('teste')

    def test_sucesso_envia_authorization(self):
        from quiz.ai_provider import CerebrasProvider
        headers_capturados = {}

        def fake_urlopen(req, timeout=None):
            headers_capturados.update(req.headers)
            return _mock_http_response({
                'choices': [{'message': {'content': 'resp cerebras'}}],
                'usage': {'total_tokens': 20},
            })

        with patch('urllib.request.urlopen', side_effect=fake_urlopen):
            r = CerebrasProvider.gerar('teste')
        self.assertEqual(r, 'resp cerebras')
        # header keys são normalizados pelo urllib (title case)
        auth_val = headers_capturados.get('Authorization') or headers_capturados.get('authorization')
        self.assertTrue(auth_val and 'fake-cerebras' in auth_val)


# ─── OPENROUTER ──────────────────────────────────────────────────────────
@override_settings(
    OPENROUTER_API_KEY='fake-or',
    OPENROUTER_MODEL='nvidia/nemotron-3-ultra-550b-a55b:free',
)
class OpenRouterProviderTests(TestCase):
    def setUp(self):
        from quiz.ai_provider import OpenRouterProvider
        OpenRouterProvider._last_quota_error = 0

    def test_fallback_interno_entre_modelos(self):
        """Se principal retorna 404, tenta proximo modelo automaticamente."""
        from quiz.ai_provider import OpenRouterProvider
        chamadas_modelos = []

        def fake_urlopen(req, timeout=None):
            payload = json.loads(req.data)
            chamadas_modelos.append(payload['model'])
            # 1o modelo (nemotron): 404. 2o (gemma): sucesso.
            if len(chamadas_modelos) == 1:
                raise _mock_http_error(404, {'error': {'message': 'not found'}})
            return _mock_http_response({
                'choices': [{'message': {'content': 'ok gemma'}}],
                'usage': {'total_tokens': 15},
            })

        with patch('urllib.request.urlopen', side_effect=fake_urlopen):
            r = OpenRouterProvider.gerar('teste')
        self.assertEqual(r, 'ok gemma')
        self.assertEqual(len(chamadas_modelos), 2)
        self.assertIn('nemotron', chamadas_modelos[0])
        self.assertIn('gemma', chamadas_modelos[1])

    def test_headers_openrouter(self):
        from quiz.ai_provider import OpenRouterProvider
        headers_cap = {}

        def fake_urlopen(req, timeout=None):
            headers_cap.update(req.headers)
            return _mock_http_response({
                'choices': [{'message': {'content': 'ok'}}],
                'usage': {'total_tokens': 5},
            })

        with patch('urllib.request.urlopen', side_effect=fake_urlopen):
            OpenRouterProvider.gerar('teste')
        # HTTP-Referer e X-Title enviados (recomendação openrouter)
        keys_lower = {k.lower(): v for k, v in headers_cap.items()}
        self.assertIn('http-referer', keys_lower)
        self.assertIn('x-title', keys_lower)


# ─── ORQUESTRADOR gerar_conteudo ─────────────────────────────────────────
@override_settings(
    AI_PROVIDER_ORDER=['groq', 'openrouter', 'gemini'],
    GROQ_API_KEY='fake', OPENROUTER_API_KEY='fake', GEMINI_API_KEY='fake',
)
class OrquestradorTests(TestCase):
    def setUp(self):
        from quiz.ai_provider import GroqProvider, OpenRouterProvider, GeminiProvider
        for cls in (GroqProvider, OpenRouterProvider, GeminiProvider):
            cls._last_quota_error = 0

    def test_fallback_groq_para_openrouter(self):
        """Se groq levanta AIQuotaExceeded, tenta openrouter."""
        from quiz.ai_provider import gerar_conteudo, AIQuotaExceeded

        def fake_groq(*a, **kw):
            raise AIQuotaExceeded('esgotou')

        def fake_or(*a, **kw):
            return 'resp openrouter'

        with patch('quiz.ai_provider.GroqProvider.gerar', side_effect=fake_groq), \
             patch('quiz.ai_provider.OpenRouterProvider.gerar', side_effect=fake_or):
            r = gerar_conteudo('teste')
        self.assertEqual(r, 'resp openrouter')

    def test_todos_falharam_levanta_erro(self):
        from quiz.ai_provider import gerar_conteudo, AIError, AIQuotaExceeded

        def falha(*a, **kw):
            raise AIQuotaExceeded('esgotou')

        with patch('quiz.ai_provider.GroqProvider.gerar', side_effect=falha), \
             patch('quiz.ai_provider.OpenRouterProvider.gerar', side_effect=falha), \
             patch('quiz.ai_provider.GeminiProvider.gerar', side_effect=falha):
            with self.assertRaises(AIError):
                gerar_conteudo('teste')
