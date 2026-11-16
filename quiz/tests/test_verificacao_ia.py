"""
Conferência de gabarito das pendentes de IA: votos, decisão e aplicação.

Nenhum teste chama provedor de IA: `quiz.verificacao_ia.chamar` é trocado por
um juiz de mentira.
"""
import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

from quiz import verificacao_ia as v
from quiz.models import Alternativa, Categoria, Questao

G = 'gemini:gemini-3.1-flash-lite'
O = 'groq:openai/gpt-oss-120b'
Q = 'groq:qwen/qwen3.8-27b'


def voto(r, c='alta', d='', f=''):
    return {'r': r, 'c': c, 'd': d, 'f': f}


class FamiliaTests(SimpleTestCase):
    def test_modelos_do_mesmo_fabricante_sao_uma_familia(self):
        self.assertEqual(v.familia_de('groq:openai/gpt-oss-120b'), 'openai')
        self.assertEqual(v.familia_de('groq:openai/gpt-oss-20b'), 'openai')
        self.assertEqual(v.familia_de('gemini:gemini-3.1-flash-lite'), 'google')
        self.assertEqual(v.familia_de('openrouter:google/gemma-4-31b-it:free'), 'google')
        self.assertEqual(v.familia_de('groq:qwen/qwen3.8-27b'), 'qwen')


class DecisaoTests(SimpleTestCase):
    def test_um_voto_so_nao_decide(self):
        self.assertEqual(v.decidir('C', {G: voto('C')})[0], v.INCOMPLETA)

    def test_dois_modelos_da_mesma_familia_nao_decidem(self):
        votos = {O: voto('C'), 'groq:openai/gpt-oss-20b': voto('C')}
        self.assertEqual(v.decidir('C', votos)[0], v.INCOMPLETA)

    def test_confirmada_quando_todos_acertam_sem_ressalva(self):
        self.assertEqual(v.decidir('C', {G: voto('C'), O: voto('C', 'media')}), (v.CONFIRMADA, ''))

    def test_baixa_certeza_vira_duvida(self):
        decisao, motivo = v.decidir('C', {G: voto('C'), O: voto('C', 'baixa')})
        self.assertEqual(decisao, v.DUVIDA)
        self.assertIn('baixa certeza', motivo)

    def test_dois_contra_o_gabarito_rejeita(self):
        decisao, motivo = v.decidir('C', {G: voto('E'), O: voto('E')})
        self.assertEqual(decisao, v.REJEITAR)
        self.assertIn('gabarito C', motivo)
        self.assertIn('responderam E', motivo)

    def test_dois_contra_em_letras_diferentes_e_duvida(self):
        self.assertEqual(v.decidir('A', {G: voto('B'), O: voto('D')})[0], v.DUVIDA)

    def test_divergencia_e_duvida(self):
        decisao, motivo = v.decidir('C', {G: voto('C'), O: voto('E')})
        self.assertEqual(decisao, v.DUVIDA)
        self.assertIn('divergem', motivo)

    def test_defeito_de_um_e_duvida_de_dois_rejeita(self):
        um = v.decidir('C', {G: voto('C', d='ambígua'), O: voto('C')})
        self.assertEqual(um[0], v.DUVIDA)
        self.assertIn('ambígua', um[1])
        dois = v.decidir('C', {G: voto('C', d='ambígua'), O: voto('C', d='duas respostas')})
        self.assertEqual(dois[0], v.REJEITAR)
        self.assertIn('defeito apontado por dois modelos', dois[1])

    def test_fraca_de_um_e_duvida_de_dois_rejeita(self):
        um = v.decidir('B', {G: voto('B', f='caso incoerente'), O: voto('B')})
        self.assertEqual(um[0], v.DUVIDA)
        self.assertIn('fraca', um[1])
        dois = v.decidir('B', {G: voto('B', f='caso incoerente'), O: voto('B', d='sem resposta exata')})
        self.assertEqual(dois[0], v.REJEITAR)
        self.assertIn('fraca segundo dois modelos', dois[1])

    def test_voto_antigo_sem_campo_fraca_continua_valendo(self):
        antigo = {'r': 'C', 'c': 'alta', 'd': ''}
        self.assertEqual(v.decidir('C', {G: antigo, O: voto('C')})[0], v.CONFIRMADA)

    def test_terceiro_voto_desempata_a_favor(self):
        votos = {G: voto('C'), O: voto('E', 'media'), Q: voto('C')}
        self.assertEqual(v.decidir('C', votos)[0], v.CONFIRMADA)

    def test_terceiro_voto_nao_confirma_contra_voto_de_certeza_alta(self):
        votos = {G: voto('C'), O: voto('E', 'alta'), Q: voto('C')}
        self.assertEqual(v.decidir('C', votos)[0], v.DUVIDA)

    def test_terceiro_voto_desempata_contra(self):
        votos = {G: voto('C'), O: voto('E'), Q: voto('E')}
        self.assertEqual(v.decidir('C', votos)[0], v.REJEITAR)


class VotosTests(SimpleTestCase):
    def setUp(self):
        self.ce = v.Item(1, 'CE', 'Direito Penal', 'A pena é de reclusão.', ('Certo', 'Errado'), 'C')
        self.me = v.Item(2, 'ME', 'Português', 'Qual é o sujeito?', ('a', 'b', 'c', 'd', 'e'), 'D')

    def test_prompt_nao_revela_o_gabarito(self):
        q = mock.Mock(id=9, tipo='ME', texto='Qual é a capital do Pará?', texto_apoio_id=None)
        q.categoria.nome = 'Geografia'
        alternativas = [mock.Mock(texto=t, correta=(t == 'Belém')) for t in ('Manaus', 'Belém', 'Macapá', 'Palmas')]
        q.alternativa_set.all.return_value = alternativas
        item = v.item_de(q)
        self.assertEqual(item.gabarito, 'B')
        prompt = v.montar_prompt_cego([item])
        self.assertIn('### 9 [Geografia] (múltipla escolha)', prompt)
        self.assertIn('B) Belém', prompt)
        bloco = v.bloco_da_questao(item)
        self.assertNotIn('←', bloco)
        self.assertNotIn('CORRETA', bloco.upper())
        self.assertNotIn('gabarito B', prompt)

    def test_item_certo_errado_le_o_gabarito_pelo_texto_da_alternativa(self):
        q = mock.Mock(id=3, tipo='CE', texto='A União responde.', texto_apoio_id=None)
        q.categoria.nome = 'Direito Administrativo'
        q.alternativa_set.all.return_value = [mock.Mock(texto='Certo', correta=False),
                                              mock.Mock(texto='Errado', correta=True)]
        self.assertEqual(v.item_de(q).gabarito, 'E')
        self.assertNotIn('A) Certo', v.bloco_da_questao(v.item_de(q)))

    def test_interpreta_resposta_normalizando_formatos(self):
        texto = '```json\n' + json.dumps({'respostas': [
            {'id': 1, 'resposta': 'Certo', 'certeza': 'Média', 'defeito': 'nenhum', 'fraca': ''},
            {'id': '2', 'resposta': 'd)', 'certeza': 'alta', 'defeito': '', 'fraca': 'norma revogada'},
        ]}) + '\n```'
        votos = v.interpretar_votos(texto, [self.ce, self.me])
        self.assertEqual(votos[1], {'r': 'C', 'c': 'media', 'd': '', 'f': ''})
        self.assertEqual(votos[2], {'r': 'D', 'c': 'alta', 'd': '', 'f': 'norma revogada'})

    def test_descarta_voto_invalido_e_id_desconhecido(self):
        texto = json.dumps({'respostas': [
            {'id': 1, 'resposta': 'talvez', 'certeza': 'alta'},
            {'id': 2, 'resposta': 'F', 'certeza': 'alta'},
            {'id': 99, 'resposta': 'C', 'certeza': 'alta'},
        ]})
        self.assertEqual(v.interpretar_votos(texto, [self.ce, self.me]), {})

    def test_resposta_que_nao_e_json_levanta_erro(self):
        with self.assertRaises(v.AIBadResponse):
            v.interpretar_votos('não consegui responder', [self.ce])

    def test_espera_do_limite_por_minuto_e_do_dia(self):
        self.assertEqual(v._espera_em_segundos('Please try again in 7.5s.'), 7.5)
        self.assertEqual(v._espera_em_segundos('try again in 12m30s'), 750)
        self.assertEqual(v._espera_em_segundos('"retryDelay": "32s"'), 32)
        self.assertIsNone(v._espera_em_segundos('erro qualquer'))
        self.assertGreater(v._tratar_429('x', 'tokens per minute (TPM). Please try again in 7.5s.'), 7)
        with self.assertRaises(v.CotaDiariaEsgotada):
            v._tratar_429('x', 'tokens per day (TPD): Limit 200000. Please try again in 12m30s')
        with self.assertRaises(v.CotaDiariaEsgotada):
            v._tratar_429('x', '"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"')

    def test_estado_guarda_votos_e_recarrega(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / 'votos.jsonl'
            estado = v.Estado(caminho)
            estado.registrar(G, {1: voto('C')}, {1: 'C'})
            estado.registrar(O, {1: voto('E')}, {1: 'C'})
            self.assertEqual(set(v.Estado(caminho).de(1)), {G, O})
            self.assertEqual(v.Estado(caminho).de(2), {})


JUSTIFICATIVA = json.dumps({
    'assunto': 'Responsabilidade civil do Estado',
    'justificativa': '## 🔍 Por que a resposta é CERTO\n' + 'A regra constitucional é objetiva. ' * 12,
})


class ComandoVerificarTests(TestCase):
    """Fluxo completo com juízes de mentira."""

    @classmethod
    def setUpTestData(cls):
        cat = Categoria.objects.create(nome='Direito Administrativo')

        def questao(texto, certo=True, **kw):
            q = Questao.objects.create(categoria=cat, texto=texto, tipo='CE', gerada_por_ia=True, **kw)
            Alternativa.objects.create(questao=q, texto='Certo', correta=certo)
            Alternativa.objects.create(questao=q, texto='Errado', correta=not certo)
            return q

        cls.boa = questao('A União responde objetivamente pelos danos que seus agentes causarem a terceiros.')
        cls.gabarito_errado = questao('O prazo prescricional contra a Fazenda Pública é de dez anos.')
        cls.divergente = questao('A autarquia é pessoa jurídica de direito público criada por lei específica.')
        cls.fraca = questao('O INSS concede aposentadoria ao servidor estatutário federal, conforme o código.')
        cls.liberada = questao('Os atos administrativos gozam de presunção de legitimidade.', revisada=True)

    def _juiz(self, respostas):
        """Juiz de mentira: `respostas` = {id: voto} para quem resolve às cegas."""
        chamadas = []

        def chamar(juiz, prompt, **kw):
            chamadas.append(juiz)
            if 'FORMATO DE SAÍDA' in prompt:          # prompt de justificativa
                return JUSTIFICATIVA
            pedidas = [qid for qid in respostas[juiz] if f'### {qid} ' in prompt]
            return json.dumps({'respostas': [
                {'id': qid, 'resposta': respostas[juiz][qid]['r'], 'certeza': respostas[juiz][qid]['c'],
                 'defeito': respostas[juiz][qid]['d'], 'fraca': respostas[juiz][qid]['f']}
                for qid in pedidas]})
        return chamar, chamadas

    def _rodar(self, respostas, *args):
        chamar, chamadas = self._juiz(respostas)
        saida = StringIO()
        with tempfile.TemporaryDirectory() as pasta, override_settings(BASE_DIR=pasta), \
                mock.patch.object(v, 'chamar', chamar), mock.patch('time.sleep'), \
                mock.patch('shutil.copy2'):
            call_command('verificar_pendentes_ia', '--juiz_base', G, '--juizes_extras', O,
                         '--justificadores', G, *args, stdout=saida)
            relatorio = json.loads(next(Path(pasta, 'output', 'verificacao_ia').glob('relatorio_*.json'))
                                   .read_text(encoding='utf-8'))
        return relatorio, chamadas, saida.getvalue()

    def _respostas(self):
        return {
            G: {self.boa.id: voto('C'), self.gabarito_errado.id: voto('E'),
                self.divergente.id: voto('C'), self.fraca.id: voto('C', f='órgão errado')},
            O: {self.boa.id: voto('C'), self.gabarito_errado.id: voto('E'),
                self.divergente.id: voto('E'), self.fraca.id: voto('C', f='regime trocado')},
        }

    def test_sem_aplicar_so_vota(self):
        rel, _, _ = self._rodar(self._respostas())
        self.assertEqual(rel['decisao'], {v.CONFIRMADA: 1, v.REJEITAR: 2, v.DUVIDA: 1})
        self.assertFalse(rel['aplicado'])
        self.assertEqual(Questao.objects.filter(gerada_por_ia=True, revisada=True).count(), 1)
        self.assertFalse(Questao.objects.filter(rejeitada_definitiva=True).exists())
        self.assertFalse(Questao.objects.exclude(justificativa__isnull=True).exclude(justificativa='').exists())

    def test_aplicar_libera_confirmada_rejeita_reprovada_e_deixa_duvida(self):
        rel, chamadas, _ = self._rodar(self._respostas(), '--aplicar')

        self.boa.refresh_from_db()
        self.assertTrue(self.boa.revisada)
        self.assertIn('🔍', self.boa.justificativa)
        self.assertEqual(self.boa.assunto, 'Responsabilidade civil do Estado')
        self.assertEqual(rel['liberadas'], [self.boa.id])

        for q, trecho in ((self.gabarito_errado, 'gabarito C'), (self.fraca, 'fraca segundo dois modelos')):
            q.refresh_from_db()
            self.assertTrue(q.rejeitada_definitiva)
            self.assertFalse(q.revisada)
            self.assertTrue(q.motivo_rejeicao.startswith(v.PREFIXO_MOTIVO))
            self.assertIn(trecho, q.motivo_rejeicao)

        self.divergente.refresh_from_db()
        self.assertFalse(self.divergente.revisada)
        self.assertFalse(self.divergente.rejeitada_definitiva)
        self.assertEqual([d['id'] for d in rel['duvidas']], [self.divergente.id])
        self.assertEqual(rel['pendentes_de_ia_depois'], 1)
        # só a confirmada gasta chamada de justificativa
        self.assertEqual(len(chamadas), 3)

    def test_questao_liberada_nao_entra_na_fila(self):
        rel, _, _ = self._rodar(self._respostas(), '--aplicar')
        self.assertEqual(rel['nesta_execucao'], 4)
        self.liberada.refresh_from_db()
        self.assertFalse(self.liberada.justificativa)

    def test_cota_diaria_esgotada_para_o_juiz_e_nao_decide(self):
        def chamar(juiz, prompt, **kw):
            if juiz == O:
                raise v.CotaDiariaEsgotada('acabou')
            return json.dumps({'respostas': [{'id': self.boa.id, 'resposta': 'C', 'certeza': 'alta'}]})
        saida = StringIO()
        with tempfile.TemporaryDirectory() as pasta, override_settings(BASE_DIR=pasta), \
                mock.patch.object(v, 'chamar', chamar), mock.patch('time.sleep'):
            call_command('verificar_pendentes_ia', '--aplicar', '--juiz_base', G,
                         '--juizes_extras', O, stdout=saida)
        self.assertIn('cota do dia acabou', saida.getvalue())
        self.boa.refresh_from_db()
        self.assertFalse(self.boa.revisada)

    def test_justificativa_invalida_deixa_confirmada_pendente(self):
        def chamar(juiz, prompt, **kw):
            if 'FORMATO DE SAÍDA' in prompt:
                return json.dumps({'assunto': 'x', 'justificativa': 'curta'})
            return json.dumps({'respostas': [{'id': self.boa.id, 'resposta': 'C', 'certeza': 'alta'}]})
        saida = StringIO()
        with tempfile.TemporaryDirectory() as pasta, override_settings(BASE_DIR=pasta), \
                mock.patch.object(v, 'chamar', chamar), mock.patch('time.sleep'), \
                mock.patch('shutil.copy2'):
            call_command('verificar_pendentes_ia', '--aplicar', '--juiz_base', G,
                         '--juizes_extras', O, '--justificadores', G, stdout=saida)
        self.boa.refresh_from_db()
        self.assertFalse(self.boa.revisada)
        self.assertFalse(self.boa.justificativa)
        self.assertIn('ainda sem justificativa', saida.getvalue())

    def test_segunda_execucao_reaproveita_os_votos(self):
        chamar, chamadas = self._juiz(self._respostas())
        with tempfile.TemporaryDirectory() as pasta, override_settings(BASE_DIR=pasta), \
                mock.patch.object(v, 'chamar', chamar), mock.patch('time.sleep'), \
                mock.patch('shutil.copy2'):
            argumentos = ('verificar_pendentes_ia', '--juiz_base', G, '--juizes_extras', O,
                          '--justificadores', G)
            call_command(*argumentos, stdout=StringIO())
            votos_da_primeira = len(chamadas)
            call_command(*argumentos, '--aplicar', stdout=StringIO())
        # a segunda só gasta a chamada da justificativa
        self.assertEqual(len(chamadas), votos_da_primeira + 1)
        self.boa.refresh_from_db()
        self.assertTrue(self.boa.revisada)
