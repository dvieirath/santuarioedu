"""
Confere o gabarito das pendentes geradas por IA usando só cota gratuita, gera
a justificativa das confirmadas e libera (ver `quiz/verificacao_ia.py`).

    python manage.py verificar_pendentes_ia                 # vota e mostra o que faria
    python manage.py verificar_pendentes_ia --aplicar       # vota, rejeita, justifica e libera
    python manage.py verificar_pendentes_ia --aplicar --limite 800
    python manage.py verificar_pendentes_ia --aplicar --so_decidir   # sem pedir voto novo
    python manage.py verificar_pendentes_ia --aplicar --desempatar   # terceiro voto nas dúvidas

Pode rodar todo dia: os votos ficam em `output/verificacao_ia/votos.jsonl` e a
execução seguinte continua de onde a cota do dia acabou. Rode antes
`python manage.py triar_pendentes_ia --aplicar`, que descarta sem IA o que tem
defeito comprovável.

O que cada execução faz:
  1. duas faixas votam ao mesmo tempo, cada questão resolvida às cegas:
     os juízes-base (Google) e os juízes extras (outra família de modelo);
  2. decide pelos votos: confirmada, rejeitar ou dúvida;
  3. com --aplicar: rejeita as reprovadas; nas confirmadas gera a justificativa
     e libera, desde que a auditoria não acuse mais nada. Dúvida fica pendente.
"""
import json
import queue
import shutil
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from quiz import verificacao_ia as v
from quiz.auditoria import FLAGS_GRAVES, detectar_flags
from quiz.categorias_pendentes import eh_a_classificar
from quiz.models import Questao
from quiz.prompts_justificativa import montar_prompt
from quiz.triagem_pendentes import pendentes_de_ia

JUIZES_BASE = 'gemini:gemini-3.5-flash-lite,gemini:gemini-3.1-flash-lite'
# Faixas separadas por ";" votam ao mesmo tempo; dentro da faixa, "," é ordem de uso.
JUIZES_EXTRAS = ('groq:openai/gpt-oss-120b;groq:qwen/qwen3.8-27b;'
                 'openrouter:nvidia/nemotron-3-ultra-550b-a55b:free')
JUSTIFICADORES = 'gemini:gemini-3.1-flash-lite,groq:openai/gpt-oss-20b'
# Plano gratuito: intervalo entre chamadas e chamadas simultâneas por provedor.
PAUSA = {'gemini': 2.0, 'groq': 20.0, 'openrouter': 6.0}
PARALELO = {'gemini': 4, 'groq': 1, 'openrouter': 1}
# Groq gratuito dá 8 mil tokens por minuto; o modelo do OpenRouter raciocina
# bastante antes de responder e leva minutos por chamada.
AJUSTE = {
    'groq': {'lote': 6},
    'openrouter': {'lote': 10, 'timeout': 420, 'max_tokens': 9000},
}
FALHAS_SEGUIDAS_MAX = 6


def flags_que_impedem(q, alts):
    """Alertas graves da auditoria, fora a falta de justificativa (que este comando resolve)."""
    return sorted((set(detectar_flags(q, alts)) & FLAGS_GRAVES) - {'sem_justificativa'})


def intercalar_por_categoria(questoes):
    """Reveza as disciplinas, para uma execução parcial não ficar numa só."""
    filas = defaultdict(list)
    for q in questoes:
        filas[q.categoria_id].append(q)
    saida, nivel = [], 0
    while True:
        rodada = [fila[nivel] for fila in filas.values() if nivel < len(fila)]
        if not rodada:
            return saida
        saida.extend(rodada)
        nivel += 1


class Command(BaseCommand):
    help = 'Confere gabarito das pendentes de IA com cota gratuita, justifica e libera'

    def add_arguments(self, parser):
        parser.add_argument('--aplicar', action='store_true',
                            help='Grava no banco (sem isto só vota e mostra o que faria)')
        parser.add_argument('--limite', type=int, default=0,
                            help='Trabalhar só nas N primeiras pendentes da fila')
        parser.add_argument('--lote', type=int, default=8,
                            help='Questões por chamada na resolução às cegas')
        parser.add_argument('--juiz_base', default=JUIZES_BASE,
                            help='Juízes-base, em ordem de uso (mesma família)')
        parser.add_argument('--juizes_extras', default=JUIZES_EXTRAS,
                            help='Juízes de outra família, em ordem de uso')
        parser.add_argument('--justificadores', default=JUSTIFICADORES)
        parser.add_argument('--desempatar', action='store_true',
                            help='Pedir terceiro voto (de outra família) para as que ficaram em dúvida')
        parser.add_argument('--so_decidir', action='store_true',
                            help='Não pede voto novo: decide com os votos já gravados')
        parser.add_argument('--sem_justificativa', action='store_true',
                            help='Não gera justificativa (confirmadas ficam pendentes)')
        parser.add_argument('--max_minutos', type=float, default=0,
                            help='Parar de chamar IA depois deste tempo')
        parser.add_argument('--estado', default='',
                            help='Arquivo de votos (padrão output/verificacao_ia/votos.jsonl)')

    # ── utilidades ──
    def _acabou_o_tempo(self):
        return bool(self.prazo) and time.time() > self.prazo

    def _diz(self, texto):
        with self.trava:
            self.stdout.write(texto)
            self.stdout.flush()

    def _votar(self, juiz, itens, lote, ainda_falta=None):
        """Pede votos de `juiz` para `itens`. Para quando a cota do dia acaba.

        `ainda_falta(item)` é consultado na hora de cada chamada: outra faixa
        pode ter votado naquela questão nesse meio-tempo.
        """
        provedor = juiz.split(':')[0]
        ajuste = AJUSTE.get(provedor, {})
        lote = min(lote, ajuste['lote']) if provedor == 'groq' else ajuste.get('lote', lote)
        grupos = [itens[i:i + lote] for i in range(0, len(itens), lote)]
        parar = threading.Event()
        conta = {'feitas': 0, 'falhas': 0, 'lotes': 0}

        def trabalhar(grupo):
            if parar.is_set() or self._acabou_o_tempo():
                return
            if ainda_falta:
                grupo = [it for it in grupo if ainda_falta(it)]
                if not grupo:
                    return
            try:
                texto = v.chamar(juiz, v.montar_prompt_cego(grupo),
                                 max_tokens=ajuste.get('max_tokens', 1200 + 300 * len(grupo)),
                                 esforco='medium', timeout=ajuste.get('timeout', 120))
                votos = v.interpretar_votos(texto, grupo)
            except v.CotaDiariaEsgotada as e:
                if not parar.is_set():
                    parar.set()
                    self.cotas_esgotadas.add(juiz)
                    self._diz(f'  {juiz}: cota do dia acabou ({str(e)[:110]})')
                return
            except Exception as e:   # erro do provedor ou resposta fora do formato
                with self.trava:
                    conta['falhas'] += 1
                    self.erros[juiz] += 1
                    desistir = conta['falhas'] >= FALHAS_SEGUIDAS_MAX
                self._diz(f'  {juiz}: erro no lote ({str(e)[:130]})')
                if desistir and not parar.is_set():
                    parar.set()
                    self._diz(f'  {juiz}: erros seguidos, deixando para depois')
                time.sleep(PAUSA.get(provedor, 5.0))
                return
            with self.trava:
                self.estado.registrar(juiz, votos, {i.id: i.gabarito for i in grupo})
                conta['falhas'] = 0
                conta['feitas'] += len(votos)
                conta['lotes'] += 1
                self.votos_novos[juiz] += len(votos)
                avisar = conta['lotes'] % 10 == 0
            if avisar:
                self._diz(f'  {juiz}: {conta["feitas"]}/{len(itens)} votos')
            time.sleep(PAUSA.get(provedor, 5.0))

        with ThreadPoolExecutor(PARALELO.get(provedor, 1)) as executor:
            list(executor.map(trabalhar, grupos))
        self._diz(f'  {juiz}: terminou com {conta["feitas"]} votos')
        return conta['feitas']

    def _faixa(self, nome, juizes, falta_para, ainda_falta=None):
        """Uma faixa de juízes em sequência: quando um para, o seguinte assume o que falta."""
        for juiz in juizes:
            if self._acabou_o_tempo():
                break
            falta = falta_para(juiz)
            self._diz(f'[{nome}] {juiz}: {len(falta)} questões sem voto')
            if falta:
                self._votar(juiz, falta, self.lote, ainda_falta)

    def _justificar(self, juiz, q):
        """Pede a justificativa. Devolve ('ok', texto, assunto), ('falha',) ou ('cota',)."""
        provedor = juiz.split(':')[0]
        try:
            dados = v.ler_json(v.chamar(juiz, montar_prompt(q), max_tokens=2500, temperatura=0.4))
        except v.CotaDiariaEsgotada as e:
            self.cotas_esgotadas.add(juiz)
            self._diz(f'  {juiz}: cota do dia acabou ({str(e)[:100]})')
            return ('cota',)
        except Exception:   # erro do provedor ou resposta fora do formato
            dados = None
        texto = str(dados.get('justificativa') or '').strip() if isinstance(dados, dict) else ''
        time.sleep(PAUSA.get(provedor, 5.0))
        if len(texto) < 200 or '##' not in texto:
            with self.trava:
                self.erros[juiz] += 1
            return ('falha',)
        return ('ok', texto, str(dados.get('assunto') or '').strip()[:255])

    def _justificar_todas(self, questoes, justificadores):
        """Cada justificador puxa da mesma fila; quem fica sem cota devolve a questão.

        Os operários só falam com a IA. Quem grava no banco é esta thread, uma
        justificativa por vez, para o trabalho não se perder se a execução cair.
        """
        fila, prontas = queue.Queue(), queue.Queue()
        for q in questoes:
            fila.put(q)

        def operario(juiz):
            falhas = 0
            while not self._acabou_o_tempo():
                try:
                    q = fila.get_nowait()
                except queue.Empty:
                    return
                resultado = self._justificar(juiz, q)
                if resultado[0] == 'cota':
                    fila.put(q)
                    return
                if resultado[0] == 'ok':
                    falhas = 0
                    prontas.put((juiz, q, resultado[1], resultado[2]))
                else:
                    falhas += 1
                    if falhas >= FALHAS_SEGUIDAS_MAX:
                        self._diz(f'  {juiz}: erros seguidos na justificativa, parando')
                        return

        operarios = [threading.Thread(target=operario, args=(juiz,))
                     for juiz in justificadores
                     for _ in range(PARALELO.get(juiz.split(':')[0], 1))]
        for t in operarios:
            t.start()
        while any(t.is_alive() for t in operarios) or not prontas.empty():
            try:
                juiz, q, texto, assunto = prontas.get(timeout=0.5)
            except queue.Empty:
                continue
            q.justificativa = texto
            campos = ['justificativa']
            if not q.assunto and assunto:
                q.assunto = assunto
                campos.append('assunto')
            q.save(update_fields=campos)
            self.justificativas[juiz] += 1
            feitas = sum(self.justificativas.values())
            if feitas % 25 == 0:
                self._diz(f'  {feitas}/{len(questoes)} justificativas gravadas')

    # ── fluxo ──
    def handle(self, *args, **opts):
        base = Path(settings.BASE_DIR)
        pasta = base / 'output' / 'verificacao_ia'
        pasta.mkdir(parents=True, exist_ok=True)
        carimbo = timezone.localtime().strftime('%Y%m%d_%H%M%S')
        self.trava = threading.RLock()
        self.estado = v.Estado(Path(opts['estado']) if opts['estado'] else pasta / 'votos.jsonl')
        self.prazo = time.time() + opts['max_minutos'] * 60 if opts['max_minutos'] else 0
        self.lote = opts['lote']
        self.cotas_esgotadas, self.erros = set(), Counter()
        self.votos_novos, self.justificativas = Counter(), Counter()
        aplicar = opts['aplicar']

        # Fila: sem alerta de auditoria primeiro (são as que podem ser liberadas).
        limpas, com_alerta, alertas = [], [], {}
        for q in pendentes_de_ia():
            if eh_a_classificar(q):
                continue
            impedem = flags_que_impedem(q, list(q.alternativa_set.all()))
            if impedem:
                alertas[q.id] = impedem
                com_alerta.append(q)
            else:
                limpas.append(q)
        fila = intercalar_por_categoria(limpas) + intercalar_por_categoria(com_alerta)
        total_fila = len(fila)
        if opts['limite']:
            fila = fila[:opts['limite']]
        questoes = {q.id: q for q in fila}
        itens = {}
        for q in fila:
            try:
                itens[q.id] = v.item_de(q)
            except ValueError:
                continue
        self._diz(f'Pendentes de IA na fila: {total_fila} '
                  f'({len(limpas)} sem alerta de auditoria). Nesta execução: {len(itens)}.')

        bases = [j for j in opts['juiz_base'].split(',') if j]
        faixas_extras = [[j for j in faixa.split(',') if j.strip()]
                         for faixa in opts['juizes_extras'].split(';') if faixa.strip()]
        extras = [j for faixa in faixas_extras for j in faixa]
        familia_base = v.familia_de(bases[0])

        def familias(it):
            return {v.familia_de(j) for j in self.estado.de(it.id)}

        def voto_base(it):
            return next((vt for j, vt in self.estado.de(it.id).items()
                         if v.familia_de(j) == familia_base), None)

        def falta_base(_juiz):
            return [it for it in itens.values() if familia_base not in familias(it)]

        def sem_segundo_voto(it):
            return not (familias(it) - {familia_base})

        def falta_extra(numero):
            # Primeiro as que o juiz-base já confirmou; por último as que ele reprovou.
            def ordem(it):
                voto = voto_base(it)
                if voto is None:
                    return 1
                limpo = voto['r'] == it.gabarito and not voto['d'] and not voto.get('f')
                return 0 if limpo else 2

            def calcular(_juiz):
                falta = sorted((it for it in itens.values() if sem_segundo_voto(it)), key=ordem)
                # cada faixa começa num ponto diferente da lista, para não repetir trabalho
                corte = len(falta) * numero // len(faixas_extras)
                return falta[corte:] + falta[:corte]
            return calcular

        if not opts['so_decidir']:
            faixas = [threading.Thread(target=self._faixa, args=('base', bases, falta_base))]
            faixas += [threading.Thread(target=self._faixa,
                                        args=(f'extra {n + 1}', faixa, falta_extra(n), sem_segundo_voto))
                       for n, faixa in enumerate(faixas_extras)]
            for t in faixas:
                t.start()
            for t in faixas:
                t.join()

            if opts['desempatar']:
                def falta_desempate(juiz):
                    return [it for it in itens.values()
                            if v.decidir(it.gabarito, self.estado.de(it.id))[0] == v.DUVIDA
                            and v.familia_de(juiz) not in familias(it)]
                self._faixa('desempate', extras, falta_desempate)

        # decisão
        decisoes = {qid: v.decidir(it.gabarito, self.estado.de(qid)) for qid, it in itens.items()}
        contagem = Counter(d for d, _ in decisoes.values())
        self._diz('\nDecisão pelos votos: ' + ', '.join(
            f'{contagem.get(k, 0)} {k}' for k in (v.CONFIRMADA, v.REJEITAR, v.DUVIDA, v.INCOMPLETA)))

        rejeitadas, liberadas, sem_just, com_flag = [], [], [], []
        relatorio = {
            'quando': carimbo, 'aplicado': aplicar,
            'fila_total': total_fila, 'nesta_execucao': len(itens),
            'decisao': dict(contagem),
        }

        if aplicar:
            banco = Path(settings.DATABASES['default']['NAME'])
            if banco.exists() and (contagem.get(v.REJEITAR) or contagem.get(v.CONFIRMADA)):
                destino = base / 'backups' / f'antes_verificacao_ia_{carimbo}.sqlite3'
                destino.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(banco, destino)
                relatorio['backup'] = str(destino.relative_to(base))
                self._diz(f'Backup: {relatorio["backup"]}')

            for qid, (decisao, motivo) in decisoes.items():
                if decisao == v.REJEITAR:
                    Questao.objects.filter(id=qid, revisada=False).update(
                        rejeitada_definitiva=True, motivo_rejeicao=v.PREFIXO_MOTIVO + motivo)
                    rejeitadas.append({'id': qid, 'motivo': motivo})
            self._diz(f'Rejeitadas: {len(rejeitadas)}')

            confirmadas = [questoes[qid] for qid, (d, _) in decisoes.items() if d == v.CONFIRMADA]
            liberaveis = [q for q in confirmadas if q.id not in alertas]
            com_flag = [{'id': q.id, 'alertas': alertas[q.id]} for q in confirmadas if q.id in alertas]
            a_justificar = [q for q in liberaveis if not (q.justificativa or '').strip()]
            self._diz(f'Confirmadas: {len(confirmadas)} ({len(a_justificar)} a justificar)')
            if a_justificar and not opts['sem_justificativa']:
                self._justificar_todas(a_justificar, [j for j in opts['justificadores'].split(',') if j])

            for q in liberaveis:
                if not (q.justificativa or '').strip():
                    sem_just.append(q.id)
                    continue
                restantes = flags_que_impedem(q, list(q.alternativa_set.all()))
                if restantes:
                    com_flag.append({'id': q.id, 'alertas': restantes})
                    continue
                Questao.objects.filter(id=q.id, rejeitada_definitiva=False).update(
                    revisada=True, motivo_rejeicao='')
                liberadas.append(q.id)
            self._diz(self.style.SUCCESS(f'Liberadas: {len(liberadas)}'))
            if sem_just:
                self._diz(f'Confirmadas ainda sem justificativa (cota ou erro): {len(sem_just)}')
            if com_flag:
                self._diz(f'Confirmadas, mas com alerta de auditoria (ficam para você): {len(com_flag)}')
        else:
            self._diz(self.style.WARNING('Nada gravado no banco. Use --aplicar.'))

        relatorio.update({
            'votos_novos': dict(self.votos_novos),
            'justificativas_geradas': dict(self.justificativas),
            'cotas_esgotadas': sorted(self.cotas_esgotadas),
            'erros': dict(self.erros),
            'liberadas': liberadas,
            'rejeitadas': rejeitadas,
            'confirmadas_sem_justificativa': sem_just,
            'confirmadas_com_alerta': com_flag,
            'duvidas': [{'id': qid, 'motivo': m} for qid, (d, m) in decisoes.items() if d == v.DUVIDA],
            'pendentes_de_ia_depois': pendentes_de_ia().count(),
        })
        destino = pasta / f'relatorio_{carimbo}.json'
        destino.write_text(json.dumps(relatorio, ensure_ascii=False, indent=1), encoding='utf-8')
        self._diz(f'\nPendentes de IA agora: {relatorio["pendentes_de_ia_depois"]}')
        self._diz(f'Relatório: {destino.relative_to(base)}')
