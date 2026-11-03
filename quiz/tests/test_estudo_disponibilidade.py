from django.test import TestCase
from django.contrib.auth import get_user_model
from quiz.models import Categoria, Questao, Alternativa, RespostaUsuario


class DisponibilidadeEstudoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username='disponibilidade')
        cls.raiz = Categoria.objects.create(nome='Raiz estudo')
        cls.filha = Categoria.objects.create(nome='Filha estudo', parent=cls.raiz)
        cls.publica = Questao.objects.create(categoria=cls.filha, texto='Questão pública para estudo', revisada=True)
        cls.pendente = Questao.objects.create(categoria=cls.filha, texto='Questão pendente para estudo')
        cls.rejeitada = Questao.objects.create(categoria=cls.filha, texto='Questão rejeitada para estudo', revisada=True, rejeitada_definitiva=True)
        for q in [cls.publica, cls.pendente, cls.rejeitada]:
            Alternativa.objects.create(questao=q, texto='Certo', correta=True)
            Alternativa.objects.create(questao=q, texto='Errado', correta=False)

    def setUp(self):
        self.client.force_login(self.user)

    def test_contagem_usa_apenas_liberadas(self):
        r = self.client.get('/estudar/')
        cat = next(c for c in r.context['categorias'] if c['id'] == self.raiz.id)
        self.assertEqual(cat['total'], 1)

    def test_categoria_pai_entrega_questoes_dos_filhos(self):
        r = self.client.get(f'/quiz/{self.raiz.id}/')
        self.assertEqual(r.context['questao'], self.publica)
        self.assertEqual(r.context['total_categoria'], 1)

    def test_post_recusa_pendentes_e_rejeitadas(self):
        for q in [self.pendente, self.rejeitada]:
            with self.subTest(q=q.id):
                r = self.client.post('/quiz/', {'alternativa_id': q.alternativa_set.first().id})
                self.assertEqual(r.status_code, 404)
        self.assertFalse(RespostaUsuario.objects.filter(usuario=self.user).exists())

    def test_payloads_invalidos_nao_causam_500(self):
        for valor in ['abc', '²', '9' * 5000]:
            with self.subTest(valor=valor[:10]):
                self.assertEqual(self.client.post('/quiz/', {'alternativa_id': valor}).status_code, 302)
                self.assertEqual(self.client.get('/quiz/', {'ano': valor}).status_code, 302)
                self.assertEqual(self.client.get('/estudar/', {'parent': valor}).status_code, 200)

    def test_resultado_sem_justificativa_nao_dispara_geracao(self):
        r = self.client.post('/quiz/', {'alternativa_id': self.publica.alternativa_set.first().id})
        self.assertContains(r, 'ainda não tem uma explicação revisada')
        self.assertNotContains(r, 'Gerando análise com IA')
        self.assertNotContains(r, '/api/justificativa/')

    def test_subarvore_nao_trava_em_ciclo(self):
        Categoria.objects.filter(pk=self.raiz.pk).update(parent=self.filha)
        self.assertEqual(set(self.raiz.subarvore_ids()), {self.raiz.id, self.filha.id})
        self.assertEqual(self.client.get('/estudar/', {'parent': self.raiz.id}).status_code, 200)

    def test_simulado_recusa_resposta_invalida_sem_avancar_ou_finalizar(self):
        from quiz.models import Simulado, RespostaSimulado
        simulado = Simulado.objects.create(usuario=self.user)
        resposta = RespostaSimulado.objects.create(simulado=simulado, questao=self.publica, ordem=1)
        url = f'/simulado/{simulado.pk}/questao/1/'
        outra = self.pendente.alternativa_set.first().pk
        for valor in ['abc', '²', '9' * 5000, '9' * 18, str(outra)]:
            with self.subTest(valor=valor[:20]):
                r = self.client.post(url, {'alternativa_id': valor, 'acao': 'finalizar'})
                self.assertRedirects(r, url, fetch_redirect_response=False)
                resposta.refresh_from_db()
                simulado.refresh_from_db()
                self.assertIsNone(resposta.alternativa_escolhida_id)
                self.assertFalse(simulado.finalizado)

    def test_simulado_permite_finalizar_com_questao_em_branco(self):
        from quiz.models import Simulado, RespostaSimulado
        simulado = Simulado.objects.create(usuario=self.user)
        resposta = RespostaSimulado.objects.create(simulado=simulado, questao=self.publica, ordem=1)
        r = self.client.post(f'/simulado/{simulado.pk}/questao/1/', {'acao': 'finalizar'})
        self.assertEqual(r.status_code, 302)
        simulado.refresh_from_db()
        resposta.refresh_from_db()
        self.assertTrue(simulado.finalizado)
        self.assertIsNone(resposta.alternativa_escolhida_id)
