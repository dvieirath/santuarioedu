"""
Smoke tests — percorrem as principais rotas autenticadas e verificam:
- Retornam 200 (ou 302 legítimo, no caso de fluxos que redirecionam)
- Rotas removidas (revisao_inteligente, revisao_por_voz) devolvem 404
- Nenhum vestígio de strings legacy no HTML renderizado

Objetivo: detectar regressões silenciosas em templates após migrações de design
ou remoção de features, sem precisar clicar página por página.

Rodar:
    python manage.py test quiz.tests.test_smoke
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import NoReverseMatch, reverse

User = get_user_model()


# Nomes de URLs (reverse) que devem responder 200/302 para usuário autenticado.
# Se algum nome for renomeado/deletado, o teste falha imediatamente.
ROTAS_AUTENTICADAS = [
    'dashboard',
    'analytics',
    'perfil',
    'escolher_tema',
    'iniciar_quiz',
    'modo_desafio',
    'flashcards',
    'caderno_erros',
    'favoritas',
    'questoes_marcadas',
    'questao_do_dia',
    'estudar_por_assunto',
    'simulado_edital',
    'simulado_personalizado',
    'simulado_preditivo',
    'modo_prova_real',
    'coletivo_home',
    'duelo_home',
    'historico_simulados',
    'ranking',
    'grupos_lista',
    'resumos_lista',
    'analise_banca',
    'analise_erros',
    'analise_subtemas',
    'previsao_topicos',
    'plano_estudos',
    'plano_dinamico',
    'plano_estudos_ia',
    'metas_avancadas',
    'metas_semanais',
    'progresso_edital',
    'mapa_conhecimento',
    'painel_xp',
    'performance_comparativa',
    'relatorio_semanal',
    'relatorio_pdf',
    'central_notificacoes',
    'preferencias_notificacao',
    'suporte_lista',
    'faq',
    'card_progresso',
    'quiz_favoritas',
]

# Strings que NÃO devem aparecer em nenhum HTML renderizado (features removidas).
STRINGS_LEGACY_PROIBIDAS = [
    b'revisao_inteligente',
    b'revisao_por_voz',
    b'Revis\xc3\xa3o Inteligente',
    b'Revis\xc3\xa3o por Voz',
    b'api_voz_responder',
]

# Rotas antigas que devem ser 404 agora.
ROTAS_REMOVIDAS = [
    '/revisao-inteligente/',
    '/revisao-voz/',
    '/api/voz/responder/',
]


class TestSmokeRotasAutenticadas(TestCase):
    """Cada rota principal deve responder 200 ou 302 para usuário logado."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('smokeuser', password='senha123')

    def setUp(self):
        self.c = Client()
        self.c.force_login(self.user)

    def test_rotas_autenticadas_respondem(self):
        """Percorre todas as rotas e coleta falhas em batch para relatório único."""
        falhas = []
        for nome in ROTAS_AUTENTICADAS:
            try:
                url = reverse(nome)
            except NoReverseMatch:
                falhas.append(f'{nome}: URL não existe (NoReverseMatch)')
                continue
            try:
                r = self.c.get(url, follow=False)
            except Exception as e:
                falhas.append(f'{nome} ({url}): raised {type(e).__name__}: {e}')
                continue
            # 429 é rate-limit hit — aceitavel no smoke (endpoints IA tem limites baixos)
            if r.status_code not in (200, 302, 429):
                falhas.append(f'{nome} ({url}): HTTP {r.status_code}')

        self.assertEqual(
            falhas, [],
            msg=f'\n{len(falhas)} rota(s) falharam:\n  - ' + '\n  - '.join(falhas)
        )


class TestSmokeSemStringsLegacy(TestCase):
    """Nenhuma página renderizada deve conter strings de features removidas."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('legacyuser', password='senha123')

    def setUp(self):
        self.c = Client()
        self.c.force_login(self.user)

    def test_dashboard_sem_strings_legacy(self):
        r = self.c.get(reverse('dashboard'))
        for s in STRINGS_LEGACY_PROIBIDAS:
            self.assertNotIn(
                s, r.content,
                msg=f'Dashboard contém string legacy proibida: {s!r}'
            )

    def test_analytics_sem_strings_legacy(self):
        r = self.c.get(reverse('analytics'))
        for s in STRINGS_LEGACY_PROIBIDAS:
            self.assertNotIn(s, r.content, msg=f'analytics contém {s!r}')

    def test_analise_erros_sem_strings_legacy(self):
        r = self.c.get(reverse('analise_erros'))
        for s in STRINGS_LEGACY_PROIBIDAS:
            self.assertNotIn(s, r.content, msg=f'analise_erros contém {s!r}')

    def test_sidebar_sem_strings_legacy(self):
        # Sidebar é incluído no dashboard — se aparecer, quebra aqui.
        r = self.c.get(reverse('dashboard'))
        self.assertNotIn(b'ATALHOS', r.content, 'Sidebar antigo detectado (ATALHOS)')
        self.assertNotIn(b'>Disciplinas<', r.content, 'Item legacy do sidebar (Disciplinas)')


class TestSmokeRotasRemovidas(TestCase):
    """As rotas removidas devem 404 (não devem responder mais)."""

    def test_rotas_deletadas_retornam_404(self):
        c = Client()
        for path in ROTAS_REMOVIDAS:
            r = c.get(path, follow=False)
            self.assertEqual(
                r.status_code, 404,
                msg=f'{path} deveria ser 404, retornou {r.status_code}'
            )


class TestSmokeSidebarConsistente(TestCase):
    """Sidebar novo (com data-nav-key) deve estar presente em todas as páginas
    autenticadas — garante que nenhuma migração acidental substituiu o include."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('sidebaruser', password='senha123')
        # ConcursoPreferido eh necessario — sem ele, dashboard redireciona
        # pra /onboarding/ (que nao usa sidebar). Simula user ja onboardado.
        from quiz.models import ConcursoPreferido
        ConcursoPreferido.objects.create(usuario=cls.user, concurso='prf')

    def setUp(self):
        self.c = Client()
        self.c.force_login(self.user)

    def test_dashboard_usa_sidebar_novo(self):
        # follow=True: user com onboarding feito (0 respostas) e redirecionado
        # pra /estudar/ que tambem usa o sidebar.
        r = self.c.get(reverse('dashboard'), follow=True)
        self.assertIn(
            b'data-nav-key', r.content,
            'Dashboard/redirect não está usando o sidebar novo (falta data-nav-key)'
        )

    def test_analytics_usa_sidebar_novo(self):
        r = self.c.get(reverse('analytics'))
        self.assertIn(b'data-nav-key', r.content, 'analytics não usa sidebar novo')


class TestSmokePaginasErro(TestCase):
    """Páginas de erro customizadas devem usar o novo design."""

    def test_404_renderiza_pagina_customizada(self):
        c = Client()
        r = c.get('/url-inexistente-para-teste/')
        self.assertEqual(r.status_code, 404)
        # Confirma template customizado (não é a 404 padrão do Django)
        self.assertIn(b'SantuarioEdu', r.content)

