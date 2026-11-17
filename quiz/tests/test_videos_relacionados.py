"""
Vídeos relacionados ao tema da questão.

Nenhum teste fala com o YouTube: oEmbed e Data API são trocados por respostas
de mentira.
"""
import io
import json
import tempfile
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.template import Context, Template
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from quiz import videos as v
from quiz.models import (Alternativa, Categoria, Questao, RespostaSimulado, Simulado,
                         VideoAula)

ID_A, ID_B, ID_C, ID_D = 'aaaaaaaaaaa', 'bbbbbbbbbbb', 'ccccccccccc', 'dQw4w9WgXcQ'


class LinkEDuracaoTests(SimpleTestCase):
    def test_extrai_id_dos_formatos_de_link(self):
        for texto in (ID_D,
                      f'https://www.youtube.com/watch?v={ID_D}',
                      f'https://youtube.com/watch?feature=share&v={ID_D}&t=42',
                      f'https://m.youtube.com/watch?v={ID_D}',
                      f'https://youtu.be/{ID_D}?si=abc',
                      f'https://www.youtube.com/shorts/{ID_D}',
                      f'https://www.youtube.com/embed/{ID_D}?start=10',
                      f'https://www.youtube-nocookie.com/embed/{ID_D}',
                      f'https://www.youtube.com/live/{ID_D}',
                      f'  {ID_D}  '):
            with self.subTest(texto=texto):
                self.assertEqual(v.extrair_id(texto), ID_D)

    def test_recusa_o_que_nao_e_video(self):
        for texto in ('', 'curto', 'https://vimeo.com/123456789', 'https://www.youtube.com/@canal',
                      f'https://www.youtube.com/watch?v={ID_D}X', 'javascript:alert(1)'):
            with self.subTest(texto=texto):
                self.assertIsNone(v.extrair_id(texto))

    def test_duracao(self):
        self.assertEqual(v.segundos_iso8601('PT1H2M3S'), 3723)
        self.assertEqual(v.segundos_iso8601('PT15M'), 900)
        self.assertEqual(v.segundos_iso8601('P1DT1S'), 86401)
        self.assertIsNone(v.segundos_iso8601('PT'))
        self.assertIsNone(v.segundos_iso8601('lixo'))
        self.assertEqual(v.duracao_texto(3723), '1:02:03')
        self.assertEqual(v.duracao_texto(605), '10:05')
        self.assertEqual(v.duracao_texto(None), '')

    def test_link_de_busca(self):
        self.assertEqual(v.link_busca('Responsabilidade  civil'),
                         'https://www.youtube.com/results?search_query=Responsabilidade+civil+aula')


def video(cat, assunto='', yid=ID_A, i=0):
    return SimpleNamespace(id=i, categoria_id=cat, assunto_norm=v.normalizar(assunto), youtube_id=yid)


class EscolhaTests(SimpleTestCase):
    """Regra pura de escolha: categoria 3 (folha) < 2 < 1 (raiz)."""
    cadeia = [3, 2, 1]

    def test_assunto_primeiro_e_palavra_mais_longa_antes(self):
        curto = video(2, 'responsabilidade civil', 'aaaaaaaaaa1', 1)
        longo = video(1, 'responsabilidade civil do estado', 'aaaaaaaaaa2', 2)
        geral = video(3, '', 'aaaaaaaaaa3', 3)
        r = v.escolher([geral, curto, longo], self.cadeia,
                       v.normalizar('Responsabilidade civil do Estado — risco administrativo'))
        self.assertEqual([x.youtube_id for x in r], ['aaaaaaaaaa2', 'aaaaaaaaaa1', 'aaaaaaaaaa3'])

    def test_geral_da_categoria_mais_proxima_primeiro(self):
        raiz, folha = video(1, '', 'aaaaaaaaaa1', 1), video(3, '', 'aaaaaaaaaa2', 2)
        self.assertEqual([x.youtube_id for x in v.escolher([raiz, folha], self.cadeia, '')],
                         ['aaaaaaaaaa2', 'aaaaaaaaaa1'])

    def test_ignora_outra_categoria_e_assunto_que_nao_casa(self):
        fora = video(99, '', 'aaaaaaaaaa1')
        outro_assunto = video(3, 'nacionalidade', 'aaaaaaaaaa2')
        self.assertEqual(v.escolher([fora, outro_assunto], self.cadeia, v.normalizar('Remédios')), [])
        self.assertEqual(v.escolher([outro_assunto], self.cadeia, ''), [])

    def test_sem_repetir_video_e_com_limite(self):
        vids = [video(3, '', ID_A, 1), video(2, '', ID_A, 2)] + [video(3, '', f'x{n:010d}', n + 3) for n in range(5)]
        r = v.escolher(vids, self.cadeia, '', limite=3)
        self.assertEqual(len(r), 3)
        self.assertEqual(len({x.youtube_id for x in r}), 3)


class BaseComDados(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.direito = Categoria.objects.create(nome='Direito')
        cls.adm = Categoria.objects.create(nome='Direito Administrativo', parent=cls.direito)
        cls.port = Categoria.objects.create(nome='Português')
        cls.q = Questao.objects.create(categoria=cls.adm, tipo='CE', revisada=True,
                                       assunto='Responsabilidade civil do Estado',
                                       texto='A União responde objetivamente pelos danos de seus agentes.')
        Alternativa.objects.create(questao=cls.q, texto='Certo', correta=True)
        cls.errada = Alternativa.objects.create(questao=cls.q, texto='Errado', correta=False)
        cls.sem_assunto = Questao.objects.create(categoria=cls.port, tipo='CE', revisada=True,
                                                 texto='A crase é facultativa antes de pronome possessivo.')
        Alternativa.objects.create(questao=cls.sem_assunto, texto='Certo', correta=True)
        Alternativa.objects.create(questao=cls.sem_assunto, texto='Errado', correta=False)

        cls.especifico = VideoAula.objects.create(
            youtube_id=ID_A, titulo='Responsabilidade civil em 15 minutos', canal='Canal A',
            duracao_segundos=905, categoria=cls.adm, assunto='  responsabilidade   civil ', aprovado=True)
        cls.geral = VideoAula.objects.create(youtube_id=ID_B, titulo='Direito: visão geral',
                                             categoria=cls.direito, aprovado=True)
        cls.pendente = VideoAula.objects.create(youtube_id=ID_C, titulo='Candidato <b>não aprovado</b>',
                                                categoria=cls.adm, origem=VideoAula.ORIGEM_YOUTUBE)


class ModeloEEscolhaNoBancoTests(BaseComDados):
    def test_salvar_normaliza_assunto_e_marca_aprovacao(self):
        self.assertEqual(self.especifico.assunto, 'responsabilidade civil')
        self.assertEqual(self.especifico.assunto_norm, 'responsabilidade civil')
        self.assertIsNotNone(self.especifico.aprovado_em)
        self.assertIsNone(self.pendente.aprovado_em)
        self.assertEqual(self.especifico.duracao, '15:05')
        self.assertEqual(self.especifico.miniatura, f'https://i.ytimg.com/vi/{ID_A}/mqdefault.jpg')

    def test_videos_para_questao(self):
        self.assertEqual([x.youtube_id for x in v.videos_para(self.q)], [ID_A, ID_B])
        self.assertEqual(v.videos_para(self.sem_assunto), [])

    def test_tag_tolera_falha_sem_derrubar_a_tela(self):
        with mock.patch('quiz.videos.videos_para', side_effect=RuntimeError('banco fora')), \
                self.assertLogs('quiz.templatetags.quiz_extras', level='ERROR'):
            html = Template('{% load quiz_extras %}{% videos_relacionados q as rel %}{{ rel.videos|length }}'
                            ).render(Context({'q': self.q}))
        self.assertEqual(html, '0')


class BlocoNaTelaTests(BaseComDados):
    def _render(self, questao, staff=False):
        user = get_user_model()(username='x', is_staff=staff)
        return Template('{% include "quiz/includes/videos_relacionados.html" with questao=q %}').render(
            Context({'q': questao, 'user': user}))

    def test_mostra_aprovados_e_esconde_candidato(self):
        html = self._render(self.q)
        self.assertIn(f'data-video-id="{ID_A}"', html)
        self.assertIn(f'data-video-id="{ID_B}"', html)
        self.assertIn('Responsabilidade civil em 15 minutos', html)
        self.assertIn('15:05', html)
        self.assertNotIn(ID_C, html)
        self.assertNotIn('não aprovado', html)
        self.assertIn('youtube-nocookie.com/embed/', html)
        self.assertNotIn('<iframe', html)   # nada do YouTube carrega antes do clique

    def test_sem_video_oferece_busca_com_o_tema(self):
        html = self._render(self.sem_assunto)
        self.assertNotIn('data-video-id', html)
        self.assertIn('https://www.youtube.com/results?search_query=Portugu%C3%AAs+aula', html)
        self.assertIn('Buscar “Português” no YouTube', html)

    def test_atalho_de_cadastro_so_para_equipe(self):
        self.assertNotIn('Adicionar vídeo', self._render(self.q))
        html = self._render(self.q, staff=True)
        self.assertIn('/admin/quiz/videoaula/add/?categoria=', html)
        self.assertIn('assunto=Responsabilidade%20civil%20do%20Estado', html)


class TelasDoAlunoTests(BaseComDados):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='aluno_video', password='x')
        self.client.force_login(self.user)

    def test_resultado_da_questao_mostra_videos(self):
        r = self.client.post('/quiz/', {'alternativa_id': self.errada.id})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Vídeos sobre o tema')
        self.assertContains(r, f'data-video-id="{ID_A}"')
        self.assertNotContains(r, ID_C)

    def test_revisao_do_simulado_mostra_videos(self):
        simulado = Simulado.objects.create(usuario=self.user, finalizado=True)
        RespostaSimulado.objects.create(simulado=simulado, questao=self.q, ordem=1,
                                        alternativa_escolhida=self.errada, acertou=False)
        r = self.client.get(f'/simulado/{simulado.id}/revisao/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, f'data-video-id="{ID_B}"')

    def test_cabecalhos_liberam_so_o_player_sem_cookies(self):
        r = self.client.post('/quiz/', {'alternativa_id': self.errada.id})
        csp = r['Content-Security-Policy']
        self.assertIn('frame-src https://www.youtube-nocookie.com', csp)
        self.assertIn('https://i.ytimg.com', csp)
        self.assertNotIn('frame-src https://www.youtube.com', csp)
        politica = r['Permissions-Policy']
        self.assertIn('autoplay=("https://www.youtube-nocookie.com")', politica)
        self.assertIn('fullscreen=(self "https://www.youtube-nocookie.com")', politica)
        self.assertIn('camera=()', politica)


class AdminTests(BaseComDados):
    def setUp(self):
        self.staff = get_user_model().objects.create_superuser('equipe', 'e@exemplo.test', 'x')
        self.client.force_login(self.staff)

    def _post(self, **dados):
        base = {'link': '', 'titulo': '', 'canal': '', 'duracao_segundos': '',
                'categoria': self.port.id, 'assunto': '', 'aprovado': 'on'}
        return self.client.post('/admin/quiz/videoaula/add/', {**base, **dados})

    def test_cadastro_pelo_link_busca_titulo_e_canal(self):
        with mock.patch('quiz.videos.buscar_oembed',
                        return_value={'titulo': 'Crase sem mistério', 'canal': 'Prof. X'}) as oembed:
            r = self._post(link=f'https://youtu.be/{ID_D}?si=x', assunto='Crase')
        self.assertEqual(r.status_code, 302, r.content[:2000])
        oembed.assert_called_once_with(ID_D)
        criado = VideoAula.objects.get(youtube_id=ID_D)
        self.assertEqual((criado.titulo, criado.canal, criado.assunto_norm), ('Crase sem mistério', 'Prof. X', 'crase'))
        self.assertTrue(criado.aprovado)

    def test_video_que_nao_pode_ser_incorporado_e_recusado(self):
        with mock.patch('quiz.videos.buscar_oembed',
                        side_effect=v.VideoIndisponivel('O dono deste vídeo não permite exibi-lo em outros sites.')):
            r = self._post(link=ID_D)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'não permite exibi-lo')
        self.assertFalse(VideoAula.objects.filter(youtube_id=ID_D).exists())

    def test_sem_rede_pede_titulo_e_aceita_quando_preenchido(self):
        falha = mock.patch('quiz.videos.buscar_oembed', side_effect=v.ErroYouTube('Não consegui consultar o YouTube agora.'))
        with falha:
            self.assertContains(self._post(link=ID_D), 'Preencha o título à mão')
        with falha:
            self.assertEqual(self._post(link=ID_D, titulo='Título manual').status_code, 302)
        self.assertEqual(VideoAula.objects.get(youtube_id=ID_D).titulo, 'Título manual')

    def test_link_invalido_e_duplicado(self):
        self.assertContains(self._post(link='https://vimeo.com/123'), 'Não reconheci')
        r = self._post(link=ID_A, categoria=self.adm.id, assunto='Responsabilidade Civil')
        self.assertContains(r, 'já está cadastrado')

    def test_formulario_vem_preenchido_pelo_atalho_da_questao(self):
        r = self.client.get(f'/admin/quiz/videoaula/add/?categoria={self.adm.id}&assunto=Atos+administrativos')
        self.assertContains(r, 'value="Atos administrativos"')
        self.assertContains(r, f'<option value="{self.adm.id}" selected>')

    def test_acoes_aprovar_e_desaprovar(self):
        url = '/admin/quiz/videoaula/'
        self.client.post(url, {'action': 'aprovar', '_selected_action': [self.pendente.id]})
        self.pendente.refresh_from_db()
        self.assertTrue(self.pendente.aprovado)
        self.assertIsNotNone(self.pendente.aprovado_em)
        self.client.post(url, {'action': 'desaprovar', '_selected_action': [self.pendente.id]})
        self.pendente.refresh_from_db()
        self.assertFalse(self.pendente.aprovado)
        self.assertEqual(self.client.get(url).status_code, 200)


class OembedTests(SimpleTestCase):
    def _http(self, codigo):
        return urllib.error.HTTPError('u', codigo, 'x', {}, io.BytesIO(b''))

    def test_respostas(self):
        with mock.patch('quiz.videos._get_json', return_value={'title': ' Aula ', 'author_name': 'Canal'}):
            self.assertEqual(v.buscar_oembed(ID_D), {'titulo': 'Aula', 'canal': 'Canal'})
        for codigo in (401, 404):
            with mock.patch('quiz.videos._get_json', side_effect=self._http(codigo)), \
                    self.assertRaises(v.VideoIndisponivel):
                v.buscar_oembed(ID_D)
        with mock.patch('quiz.videos._get_json', side_effect=urllib.error.URLError('sem rede')), \
                self.assertRaises(v.ErroYouTube) as erro:
            v.buscar_oembed(ID_D)
        self.assertNotIsInstance(erro.exception, v.VideoIndisponivel)


def resposta_api(url, timeout=20):
    """Data API de mentira: a busca devolve 5 ids; os detalhes filtram 3 deles."""
    if '/search?' in url:
        return {'items': [{'id': {'videoId': i}} for i in
                          ('bom00000001', 'curto000001', 'aovivo00001', 'bloqueado01', 'bom00000002')]}
    detalhe = lambda i, dur, emb=True, live='none', titulo='Aula': {  # noqa: E731
        'id': i, 'contentDetails': {'duration': dur},
        'status': {'embeddable': emb, 'privacyStatus': 'public'},
        'snippet': {'title': titulo, 'channelTitle': 'Canal', 'liveBroadcastContent': live}}
    return {'items': [detalhe('bom00000001', 'PT12M'), detalhe('curto000001', 'PT45S', titulo='x #shorts'),
                      detalhe('aovivo00001', 'PT30M', live='live'), detalhe('bloqueado01', 'PT20M', emb=False),
                      detalhe('bom00000002', 'PT1H5M')]}


class ComandoBuscaTests(BaseComDados):
    def _rodar(self, pasta, *args):
        saida = io.StringIO()
        with override_settings(BASE_DIR=Path(pasta), YOUTUBE_API_KEY='chave-de-teste'):
            call_command('buscar_videos_youtube', *args, stdout=saida)
        return saida.getvalue()

    def test_simulacao_nao_chama_a_api(self):
        with tempfile.TemporaryDirectory() as pasta, \
                mock.patch('quiz.videos._get_json', side_effect=AssertionError('não devia chamar')):
            saida = self._rodar(pasta, '--minimo_questoes', '1')
        self.assertIn('Simulação', saida)
        self.assertIn('Português aula concurso', saida)
        self.assertNotIn('Direito Administrativo aula concurso', saida)  # já tem vídeo geral acima
        self.assertFalse(VideoAula.objects.filter(origem=VideoAula.ORIGEM_YOUTUBE).exclude(pk=self.pendente.pk).exists())

    def test_aplicar_cria_candidatos_filtrados_e_nao_aprovados(self):
        with tempfile.TemporaryDirectory() as pasta, mock.patch('quiz.videos._get_json', side_effect=resposta_api):
            saida = self._rodar(pasta, '--aplicar', '--so', 'categorias')
            buscas = json.loads(Path(pasta, 'output', 'videos_youtube', 'buscas.json').read_text(encoding='utf-8'))
            relatorio = json.loads(next(Path(pasta, 'output', 'videos_youtube').glob('relatorio_*.json'))
                                   .read_text(encoding='utf-8'))
        novos = VideoAula.objects.filter(busca='Português aula concurso')
        self.assertEqual(sorted(novos.values_list('youtube_id', flat=True)), ['bom00000001', 'bom00000002'])
        self.assertFalse(novos.filter(aprovado=True).exists())
        self.assertEqual(set(novos.values_list('categoria_id', flat=True)), {self.port.id})
        self.assertIn('portugues aula concurso', buscas)
        self.assertEqual(relatorio['buscas_feitas'], 1)
        self.assertIn('2 candidatos novos', saida)
        # o aluno continua sem ver nada
        self.assertEqual(v.videos_para(self.sem_assunto), [])

    def test_nao_repete_termo_buscado_recentemente(self):
        with tempfile.TemporaryDirectory() as pasta, mock.patch('quiz.videos._get_json', side_effect=resposta_api) as api:
            self._rodar(pasta, '--aplicar', '--so', 'categorias')
            chamadas = api.call_count
            saida = self._rodar(pasta, '--aplicar', '--so', 'categorias')
        self.assertEqual(api.call_count, chamadas)
        self.assertIn('0 buscas', saida)

    def test_cota_esgotada_para_sem_erro(self):
        corpo = io.BytesIO(b'{"error": {"errors": [{"reason": "quotaExceeded"}]}}')
        erro = urllib.error.HTTPError('u', 403, 'x', {}, corpo)
        with tempfile.TemporaryDirectory() as pasta, mock.patch('quiz.videos._get_json', side_effect=erro):
            saida = self._rodar(pasta, '--aplicar', '--minimo_questoes', '1')
        self.assertIn('cota diária gratuita', saida)

    def test_sem_chave_explica(self):
        with tempfile.TemporaryDirectory() as pasta, override_settings(BASE_DIR=Path(pasta), YOUTUBE_API_KEY=''), \
                self.assertRaises(CommandError) as erro:
            call_command('buscar_videos_youtube', '--aplicar', stdout=io.StringIO())
        self.assertIn('YOUTUBE_API_KEY', str(erro.exception))
