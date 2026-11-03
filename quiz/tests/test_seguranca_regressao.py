"""Regressões de conta, partidas, conteúdo não confiável e cache privado."""
from datetime import timedelta
from io import BytesIO

from PIL import Image
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from quiz.models import (
    Alternativa, Categoria, DesafioResultado, Duelo, NivelUsuario,
    ParticipanteColetivo, Questao, RespostaColetivo, RespostaDuelo,
    RespostaSimulado, RespostaUsuario, RevisaoEspacada, Simulado,
    SimuladoColetivo, TentativaDesafio,
)


@override_settings(
    RATELIMIT_ENABLE=False,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.InMemoryStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    },
)
class SecurityRegressionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            'seguranca', email='original@example.com', password='Original-forte-739!')
        self.other = get_user_model().objects.create_user('outro')
        self.email = EmailAddress.objects.create(
            user=self.user, email=self.user.email, verified=True, primary=True)
        self.client.force_login(self.user)
        cat = Categoria.objects.create(nome='Segurança')
        self.questions = []
        self.answers = []
        for i in range(5):
            q = Questao.objects.create(categoria=cat, texto=f'Questão {i}', revisada=True)
            self.questions.append(q)
            self.answers.append(Alternativa.objects.create(questao=q, texto='Sim', correta=True))
            Alternativa.objects.create(questao=q, texto='Não', correta=False)

    def test_profile_rejects_html_upload(self):
        response = self.client.post('/perfil/', {
            'first_name': 'Não salvar',
            'foto': SimpleUploadedFile('foto.html', b'<html>conteudo</html>', 'text/html'),
        })
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertFalse(self.user.perfil.foto)
        self.assertEqual(self.user.first_name, '')

    def test_profile_reencodes_image_and_removes_trailing_data(self):
        output = BytesIO()
        Image.new('RGB', (12, 12), 'blue').save(output, 'PNG')
        upload = SimpleUploadedFile('foto.png', output.getvalue() + b'<script>bad</script>', 'image/png')
        self.client.post('/perfil/', {'first_name': 'Ana', 'foto': upload})
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Ana')
        self.assertTrue(self.user.perfil.foto.name.endswith('.jpg'))
        content = self.user.perfil.foto.read()
        self.assertNotIn(b'<script>', content)
        self.assertEqual(Image.open(BytesIO(content)).format, 'JPEG')

    def test_profile_rejects_oversize_image(self):
        output = BytesIO()
        Image.new('RGB', (2, 2)).save(output, 'PNG')
        upload = SimpleUploadedFile('foto.png', output.getvalue() + b'x' * (5 * 1024 * 1024), 'image/png')
        self.client.post('/perfil/', {'foto': upload})
        self.assertFalse(self.user.perfil.foto)

    def test_password_requires_current_password(self):
        self.client.post('/perfil/', {'senha': 'Nova-forte-845!', 'confirmacao_senha': 'Nova-forte-845!'})
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Original-forte-739!'))

    def test_password_validators_run_and_invalid_form_is_atomic(self):
        self.client.post('/perfil/', {
            'first_name': 'Não salvar', 'senha_atual': 'Original-forte-739!',
            'senha': '1', 'confirmacao_senha': '1',
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, '')
        self.assertTrue(self.user.check_password('Original-forte-739!'))

    def test_valid_password_change_preserves_session(self):
        self.client.post('/perfil/', {
            'senha_atual': 'Original-forte-739!',
            'senha': 'Nova-forte-845!', 'confirmacao_senha': 'Nova-forte-845!',
        })
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Nova-forte-845!'))
        self.assertEqual(self.client.get('/perfil/').status_code, 200)

    def test_profile_cannot_change_email(self):
        self.client.post('/perfil/', {'email': 'novo@example.com'})
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, self.email.email)

    def test_email_management_page_and_unverified_primary_rejected(self):
        new = EmailAddress.objects.create(user=self.user, email='novo@example.com')
        self.assertContains(self.client.get('/accounts/email/'), 'Gerenciar e-mail')
        self.client.post('/accounts/email/', {'email': new.email, 'action_primary': ''})
        self.user.refresh_from_db()
        self.email.refresh_from_db()
        self.assertTrue(self.email.primary)
        self.assertEqual(self.user.email, self.email.email)

    def attempt(self):
        return TentativaDesafio.objects.create(
            usuario=self.user, questoes_ids=[q.pk for q in self.questions], segundos_por_questao=30)

    def action(self, attempt, action, **kwargs):
        return self.client.post('/modo-desafio/', {
            'tentativa_id': str(attempt.pk), 'acao': action, **kwargs,
        }, content_type='application/json')

    def test_challenge_rejects_legacy_forged_score(self):
        r = self.client.post('/modo-desafio/', {'respostas': [
            {'alternativa_id': self.answers[0].pk, 'tempo_seg': -300}] * 2},
            content_type='application/json')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(DesafioResultado.objects.exists())
        self.assertFalse(RespostaUsuario.objects.exists())

    def test_challenge_payload_does_not_expose_answer_key_or_script(self):
        self.questions[0].texto = '</script><script>window.injected=1</script>'
        self.questions[0].save()
        response = self.client.get('/modo-desafio/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.questions[0].texto)
        for question in response.context['questoes_data']:
            self.assertNotIn('texto', question)
            self.assertNotIn('alternativas', question)
        attempt = TentativaDesafio.objects.get(pk=response.context['tentativa_id'])
        opened = self.action(attempt, 'abrir', indice=0)
        for alternative in opened.json()['questao']['alternativas']:
            self.assertNotIn('correta', alternative)

    def test_challenge_owner_and_order(self):
        attempt = self.attempt()
        self.assertEqual(self.action(attempt, 'abrir', indice=-1).status_code, 400)
        self.assertEqual(self.action(attempt, 'abrir', indice=1).status_code, 409)
        self.client.force_login(self.other)
        self.assertEqual(self.action(attempt, 'abrir', indice=0).status_code, 404)

    def test_challenge_wrong_question_and_early_finish_rejected(self):
        attempt = self.attempt()
        self.action(attempt, 'abrir', indice=0)
        self.assertEqual(self.action(attempt, 'responder', indice=0,
                                    alternativa_id=self.answers[1].pk).status_code, 400)
        self.assertEqual(self.action(attempt, 'finalizar').status_code, 409)
        attempt.refresh_from_db()
        self.assertEqual(attempt.respostas, [])

    def test_challenge_server_clock_cannot_be_reset_or_forged(self):
        attempt = self.attempt()
        past = timezone.now() - timedelta(seconds=35)
        attempt.aberta_em = past
        attempt.save()
        self.action(attempt, 'abrir', indice=0)
        attempt.refresh_from_db()
        self.assertEqual(attempt.aberta_em, past)
        response = self.action(attempt, 'responder', indice=0,
                               alternativa_id=self.answers[0].pk, tempo_seg=-300)
        self.assertTrue(response.json()['expirou'])
        self.assertFalse(response.json()['acertou'])
        self.assertEqual(response.json()['pontos'], 0)

    def test_challenge_retries_do_not_duplicate_answers_results_or_xp(self):
        attempt = self.attempt()
        for i, alt in enumerate(self.answers):
            self.action(attempt, 'abrir', indice=i)
            first = self.action(attempt, 'responder', indice=i, alternativa_id=alt.pk)
            retry = self.action(attempt, 'responder', indice=i, alternativa_id=None)
            self.assertEqual(first.json(), retry.json())
        first = self.action(attempt, 'finalizar')
        self.assertEqual(first.status_code, 200)
        xp = NivelUsuario.objects.get(usuario=self.user).xp_total
        retry = self.action(attempt, 'finalizar')
        self.assertEqual(first.json(), retry.json())
        self.assertEqual(DesafioResultado.objects.count(), 1)
        self.assertEqual(RespostaUsuario.objects.count(), 5)
        self.assertEqual(NivelUsuario.objects.get(usuario=self.user).xp_total, xp)
        self.assertLessEqual(first.json()['pontos'], 75)

    def test_simulado_updates_srs_and_xp_once(self):
        sim = Simulado.objects.create(usuario=self.user)
        RespostaSimulado.objects.create(simulado=sim, questao=self.questions[0], ordem=1)
        url = f'/simulado/{sim.pk}/questao/1/'
        for _ in range(2):
            self.assertEqual(self.client.post(url, {'alternativa_id': self.answers[0].pk}).status_code, 302)
        self.assertTrue(RevisaoEspacada.objects.filter(usuario=self.user, questao=self.questions[0]).exists())
        self.assertEqual(NivelUsuario.objects.get(usuario=self.user).xp_total, 10)

    def test_multiplayer_order_and_duplicate_protection(self):
        duel = Duelo.objects.create(criador=self.user, adversario=self.other,
                                   status='em_andamento', n_questoes=5)
        group = SimuladoColetivo.objects.create(criador=self.user, status='em_andamento', n_questoes=5)
        for user in (self.user, self.other):
            ParticipanteColetivo.objects.create(simulado=group, usuario=user)
        for game, url, answers in (
            (duel, f'/api/duelo/{duel.pk}/responder/', RespostaDuelo),
            (group, f'/api/coletivo/{group.pk}/responder/', RespostaColetivo),
        ):
            game.questoes.set(self.questions)
            for index, status in [(-1, 400), (1, 409), (999, 400)]:
                self.assertEqual(self.client.post(url, {'questao_index': index,
                    'alternativa_id': self.answers[-1].pk}, content_type='application/json').status_code, status)
            self.assertEqual(self.client.post(url, {'questao_index': 0, 'tempo_ms': -1},
                                             content_type='application/json').status_code, 400)
            for _ in range(2):
                self.assertEqual(self.client.post(url, {'questao_index': 0,
                    'alternativa_id': self.answers[0].pk}, content_type='application/json').status_code, 200)
            self.assertEqual(answers.objects.count(), 1)
        self.assertEqual(ParticipanteColetivo.objects.get(simulado=group, usuario=self.user).pontos, 1)

    def test_private_page_cache_headers_and_real_service_worker(self):
        self.assertIn('no-store', self.client.get('/perfil/')['Cache-Control'])
        self.client.logout()
        sw = self.client.get('/sw.js')
        self.assertContains(sw, 'santuario-v9')
        self.assertIn('no-cache', sw['Cache-Control'])
        self.assertNotEqual(self.client.get('/manifest.json').json(), {})

    def test_multiplayer_uses_server_time_and_hides_answer_key(self):
        past = timezone.now() - timedelta(minutes=2)
        duel = Duelo.objects.create(criador=self.user, adversario=self.other,
                                   status='em_andamento', n_questoes=5, iniciado_em=past)
        group = SimuladoColetivo.objects.create(criador=self.user,
                                    status='em_andamento', n_questoes=5, iniciado_em=past)
        ParticipanteColetivo.objects.create(simulado=group, usuario=self.user)
        for game, prefix in [(duel, 'duelo'), (group, 'coletivo')]:
            game.questoes.set(self.questions)
            page = self.client.get(f'/{prefix}/{game.pk}/jogar/')
            self.assertEqual(page.status_code, 200)
            self.assertNotContains(page, 'data-correta')
            response = self.client.post(f'/api/{prefix}/{game.pk}/responder/', {
                'questao_index': 0, 'alternativa_id': self.answers[0].pk, 'tempo_ms': 0,
            }, content_type='application/json')
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json()['acertou'])

    def test_multiplayer_retry_after_last_response_does_not_get_stuck(self):
        duel = Duelo.objects.create(criador=self.user, status='em_andamento', n_questoes=1)
        group = SimuladoColetivo.objects.create(criador=self.user, status='em_andamento', n_questoes=1)
        ParticipanteColetivo.objects.create(simulado=group, usuario=self.user)
        for game, prefix in [(duel, 'duelo'), (group, 'coletivo')]:
            game.questoes.set([self.questions[0]])
            url = f'/api/{prefix}/{game.pk}/responder/'
            data = {'questao_index': 0, 'alternativa_id': self.answers[0].pk}
            first = self.client.post(url, data, content_type='application/json')
            retry = self.client.post(url, data, content_type='application/json')
            self.assertEqual(first.status_code, 200)
            self.assertEqual(retry.status_code, 200)
            self.assertTrue(retry.json()['duplicado'])
            self.assertEqual(first.json()['acertou'], retry.json()['acertou'])
