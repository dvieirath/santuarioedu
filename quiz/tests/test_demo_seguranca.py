from unittest.mock import patch
from django.test import TestCase, SimpleTestCase
from django.urls import reverse
from quiz.models import Categoria, Questao, Alternativa
from quiz.views.guest import _assinatura
from quiz.templatetags.quiz_extras import markdown


class MarkdownSeguroTests(SimpleTestCase):
    def test_remove_html_ativo_e_urls_perigosas(self):
        for ataque in ['<script>alert(1)</script>', '<img src=x onerror=alert(1)>',
                       '<svg onload=alert(1)>', '[abrir](javascript:alert%281%29)',
                       '<a href="&#106;avascript:alert(1)">abrir</a>']:
            with self.subTest(ataque=ataque):
                resultado = markdown(ataque)
                for proibido in ['<script', '<img', '<svg', 'onerror=', 'onload=', 'javascript:']:
                    self.assertNotIn(proibido, resultado)

    def test_preserva_formatacao_e_link_https(self):
        resultado = markdown('## Conceito\n\n**Resposta** [fonte](https://example.com)')
        self.assertIn('<h2>Conceito</h2>', resultado)
        self.assertIn('<strong>Resposta</strong>', resultado)
        self.assertIn('href="https://example.com"', resultado)


class DemoSeguroTests(TestCase):
    def setUp(self):
        categoria = Categoria.objects.create(nome='Matemática')
        self.questoes = []
        for numero in range(3):
            q = Questao.objects.create(categoria=categoria, texto=f'{numero} = {numero}',
                tipo='CE', revisada=True, justificativa='**Explicação existente**')
            Alternativa.objects.create(questao=q, texto='Certo', correta=True)
            Alternativa.objects.create(questao=q, texto='Errado', correta=False)
            self.questoes.append(q)
        self.manifesto = [{'texto': q.texto, 'sha256': _assinatura(q)} for q in self.questoes]
        self.patcher = patch('quiz.views.guest.DEMO_CURADORIA', self.manifesto)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def responder(self, q):
        return self.client.post(reverse('guest_quiz_responder'), {
            'questao_id': q.id, 'alternativa_id': q.alternativa_set.get(correta=True).id})

    def test_reload_preserva_questao(self):
        self.client.get(reverse('guest_quiz'))
        atual = self.client.session['guest_atual']
        self.client.get(reverse('guest_quiz'))
        self.assertEqual(atual, self.client.session['guest_atual'])

    def test_recusa_resposta_nao_apresentada(self):
        self.responder(self.questoes[0])
        self.assertNotIn('guest_respondidas', self.client.session)
        self.client.get(reverse('guest_quiz'))
        self.responder(self.questoes[1])
        self.assertNotIn('guest_respondidas', self.client.session)

    def test_fluxo_completo_com_explicacao_e_sem_pontuar_repeticao(self):
        for q in self.questoes:
            self.client.get(reverse('guest_quiz'))
            resposta = self.responder(q)
            self.assertContains(resposta, '<strong>Explicação existente</strong>')
            self.responder(q)
        self.assertEqual(self.client.session['guest_acertos'], 3)
        self.assertEqual(len(self.client.session['guest_respondidas']), 3)
        self.assertTemplateUsed(self.client.get(reverse('guest_quiz')), 'quiz/guest_quiz_final.html')

    def test_conteudo_alterado_nao_entra_na_demo(self):
        q = self.questoes[0]
        q.justificativa = 'Alterada após a conferência'
        q.save()
        self.assertTemplateUsed(self.client.get(reverse('guest_quiz')), 'quiz/guest_indisponivel.html')

    def test_rejeicao_apos_exibicao_impede_resposta(self):
        self.client.get(reverse('guest_quiz'))
        q = self.questoes[0]
        q.rejeitada_definitiva = True
        q.save()
        self.responder(q)
        self.assertNotIn('guest_respondidas', self.client.session)

    def test_sem_curadoria_nao_usa_questoes_aleatorias(self):
        with patch('quiz.views.guest.DEMO_CURADORIA', []):
            self.assertTemplateUsed(self.client.get(reverse('guest_quiz')), 'quiz/guest_indisponivel.html')
