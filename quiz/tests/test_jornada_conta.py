import re
from urllib.parse import urlsplit
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core import mail
from allauth.account.models import EmailAddress


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class JornadaContaTests(TestCase):
    def test_cadastro_codigo_errado_e_confirmacao(self):
        with patch('allauth.account.adapter.DefaultAccountAdapter.generate_email_verification_code', return_value='ABCD1234'):
            resposta = self.client.post(reverse('account_signup'), {
                'username': 'aluno_jornada', 'email': 'aluno@example.com',
                'password1': 'Teste-local!9472', 'password2': 'Teste-local!9472',
            })
        self.assertEqual(resposta.status_code, 302)
        usuario = get_user_model().objects.get(username='aluno_jornada')
        self.assertFalse(EmailAddress.objects.get(user=usuario).verified)
        self.assertTrue(any('ABCD' in m.body for m in mail.outbox))
        confirmar = reverse('account_email_verification_sent')
        erro = self.client.post(confirmar, {'code': 'ERRADO99'})
        self.assertEqual(erro.status_code, 200)
        self.assertFalse(EmailAddress.objects.get(user=usuario).verified)
        sucesso = self.client.post(confirmar, {'code': 'ABCD1234'})
        self.assertEqual(sucesso.status_code, 302)
        self.assertTrue(EmailAddress.objects.get(user=usuario).verified)
        self.assertEqual(int(self.client.session['_auth_user_id']), usuario.pk)

    def test_recuperacao_troca_senha_e_invalida_link(self):
        usuario = get_user_model().objects.create_user('recuperar', email='recuperar@example.com', password='Anterior!9472')
        EmailAddress.objects.create(user=usuario, email=usuario.email, verified=True, primary=True)
        r = self.client.post(reverse('account_reset_password'), {'email': usuario.email})
        self.assertEqual(r.status_code, 302)
        links = re.findall(r'https?://[^\s<>]+/accounts/password/reset/key/[^\s<>]+', mail.outbox[-1].body)
        self.assertTrue(links)
        caminho = urlsplit(links[0]).path
        formulario = self.client.get(caminho, follow=True)
        self.assertEqual(formulario.status_code, 200)
        destino = formulario.context['action_url']
        r = self.client.post(destino, {'password1': 'Nova-local!9472', 'password2': 'Nova-local!9472'})
        self.assertEqual(r.status_code, 302)
        usuario.refresh_from_db()
        self.assertTrue(usuario.check_password('Nova-local!9472'))
        self.assertFalse(usuario.check_password('Anterior!9472'))
        self.assertContains(self.client.get(caminho, follow=True), 'Link inválido')

    def test_email_inexistente_nao_revela_cadastro(self):
        r = self.client.post(reverse('account_reset_password'), {'email': 'ausente@example.com'})
        self.assertRedirects(r, reverse('account_reset_password_done'), fetch_redirect_response=False)

    def test_senhas_diferentes_preservam_dados_nao_criam_conta(self):
        r = self.client.post(reverse('account_signup'), {'username':'rascunho', 'email':'rascunho@example.com',
            'password1':'Teste-local!9472', 'password2':'Diferente!9472'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'value="rascunho"')
        self.assertFalse(get_user_model().objects.filter(username='rascunho').exists())
