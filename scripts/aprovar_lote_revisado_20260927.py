"""Aplica a revisão de conteúdo de 27/09, preservando alterações concorrentes."""
import json
import os
from pathlib import Path
import sqlite3
import sys
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'prf_master.settings')
os.environ['SENTRY_DSN'] = ''
import django
django.setup()
from django.conf import settings
from django.db import transaction
from quiz.models import Questao

BASE = ROOT / 'docs' / 'geracao_justificativas'
APROVAR = {8209, 9414, 9415, 9454, 9457, 9460, 9660, 11993, 11994,
           12170, 12171, 12172, 12200, 12205, 12407, 12445, 12446, 12447}
EXCECOES = {
    8209: 'Imagem institucional é reputação, não figura ausente. Transparência confirmada na Lei 12.527/2011, arts. 3 e 7.',
    11993: 'A, B e C são nomes dos centros, não letras corrompidas. Geometria e justificativa conferidas.',
    12205: 'Texto de apoio consta integralmente; alternativas de um dígito são números válidos. Sete bytes distintos conferidos.',
}
PROBLEMAS = {
    8212: 'Contagem de incidências inconsistente: 20 elementos em 3 pares cada dão 60 incidências, equivalentes a 30 pares, não 12.',
    8220: '(4×3+2)/2=7, ausente das alternativas; cadastro marca 10.',
    8221: 'A escolha do meio não é especificada; com meio inferior o oitavo elemento é encontrado na primeira comparação, não na terceira.',
    8222: 'Dados não determinam a: (3,8,10,17) e (4,8,10,16) satisfazem todas as condições.',
    8275: 'Texto exige atualizações de firmware, enquanto a proposição nega essa necessidade e está marcada Certo.',
    8286: 'Sequência finita sem regra suficientemente definida para determinar o próximo termo.',
    8287: 't(50)−t(30)=105−65=40. Gabarito Errado incompatível se t estiver em minutos; unidade também deve ser explicitada.',
    8288: 'Condição do WHILE não garante distância mínima sem conhecer movimento, passo e leitura de sensores.',
    8291: 'Regra de eliminação de pares de letras ambígua.',
    8292: 'Nova marcação nas posições 2,6,10: três elementos. União com 1,4,7,10 tem seis, não quatro.',
    8299: 'Pergunta ME cadastrada como CE; justificativa seleciona letra E e usa referências jurídicas não pertinentes.',
    8321: 'Justificativa atribui participação política ao art. 5, XXXVII e voto eletrônico ao art. 14, §4; dispositivos não tratam disso.',
    8338: 'Justificativa restringe indevidamente controle judicial a conflitos de competência; exige correção de conteúdo.',
    8393: 'Referência à individualização da pena está incorreta: CF art. 5, XLVI, não XLVIII. Programa e conclusão precisam de revisão.',
    8398: 'Caso narrativo sem proposição final clara; explicação acrescenta conteúdo de lei local não fornecido.',
    8400: 'Caso narrativo sem proposição final clara; justificativa presume validade da distinção sem fundamento apresentado.',
    8410: 'Afirma obrigatoriedade e nulidade automática com referências incompatíveis; necessária revisão jurídica.',
    8413: 'Justificativa contém instrução residual “Máximo 4 frases” e referências incompatíveis com a hipótese penal.',
    8432: 'A mera alegação em embargos não suspende automaticamente a execução: CPC art. 919. Referência a §1 do art. 924 inadequada.',
    8433: 'Cita art. 1793 do CPC e leilão universalmente obrigatório; referência e explicação precisam de correção.',
    8434: 'Enunciado exige laudo preliminar, mas a própria justificativa afirma que não é obrigatório.',
    8435: 'Justificativa impede revogação da liminar antes do mérito, contrariando CPC art. 296.',
    8436: 'Alternativas C e D materialmente semelhantes; contexto usa suposto limite de isenção do CDC sem base.',
    8437: 'Referência à Súmula 545/STJ não corresponde ao tema descrito; conferir fontes antes de liberar.',
    8438: 'Suposto limite de isenção no art. 1 do CDC não sustenta suspensão de execução fiscal.',
    8431: 'Justificativa declara vício insanável e indeferimento inevitável sem tratar adequadamente da emenda do art. 321 do CPC.',
    8168: 'Tema é direito autoral na categoria Português; referência central sobre independência de registro deve ser art. 18 da LDA.',
    8171: 'Explicação atribui exigências não fornecidas ao edital e confunde citação com referência completa.',
    8176: 'Conceito central plausível, mas referências bibliográficas específicas não verificadas.',
    8210: 'Há também omissão de informação; justificativa generaliza improbidade e cita súmula que precisa ser verificada.',
    8215: 'Média ponderada não informa pesos; explicação assume igualdade de pesos sem explicitação.',
    8243: 'Diretriz e seção bibliográfica alegadas não verificadas; ausência de menção não demonstra por si a conclusão.',
    8250: 'Resposta atende ao edital hipotético, mas manual e capítulo atribuídos ao Cebraspe não foram verificados.',
    8281: 'Referências específicas não verificadas e memorização generaliza indevidamente todo custo dependente da entrada como O(n).',
    8284: 'Justificativa contém fórmula corrompida e regra “O(N²) sempre” que não explica o melhor caso linear.',
    8289: 'Cálculo correto, mas resolução e artigo atribuídos à ANTT não foram verificados.',
    8340: 'Referência da igualdade atribuída indevidamente ao §1 do art. 5 da CF; conferir também fonte do caso.',
    8418: 'Requer esclarecer registro do medicamento versus registro do fornecedor e conferir contexto sanitário antes de aprovar.',
}

def main():
    rows = json.loads((BASE / 'aprovacao_entrada_20260927.json').read_text(encoding='utf-8'))
    assert APROVAR <= {r['id'] for r in rows}
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    db = Path(settings.DATABASES['default']['NAME']).resolve()
    assert settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3'
    assert db == ROOT / 'db.sqlite3'
    backup = ROOT / 'backups' / f'antes_aprovacao_{stamp}.sqlite3'
    with sqlite3.connect(str(db)) as src, sqlite3.connect(str(backup)) as dst:
        src.backup(dst)
        assert dst.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
    saved, skipped = [], []
    with transaction.atomic():
        for r in rows:
            if r['id'] not in APROVAR:
                continue
            q = Questao.objects.get(pk=r['id'])
            unchanged = all(getattr(q, k) == r[k] for k in ['texto','tipo','justificativa','motivo_rejeicao'])
            unchanged &= str(q.imagem) == r['imagem'] and q.categoria.nome == r['categoria']
            unchanged &= list(q.alternativa_set.order_by('id').values('id','texto','correta')) == r['alternativas']
            if not unchanged or q.revisada or q.rejeitada_definitiva or q.motivo_rejeicao:
                skipped.append(q.pk)
                continue
            assert q.justificativa.strip() and sum(a['correta'] for a in r['alternativas']) == 1
            assert not r['flags'] or q.pk in EXCECOES
            Questao.objects.filter(pk=q.pk, revisada=False, rejeitada_definitiva=False).update(revisada=True)
            saved.append(q.pk)
    held = [{'id':r['id'], 'motivo':PROBLEMAS.get(r['id'], 'Alerta de estrutura/contexto ou fonte ainda não resolvido; requer revisão de conteúdo antes de aprovação.'), 'flags':r['flags']} for r in rows if r['id'] not in APROVAR]
    result = dict(aprovadas=len(saved), ids_aprovados=saved, ignoradas_por_alteracao=skipped,
                  mantidas_pendentes=held, excecoes_conferidas=EXCECOES, backup=str(backup),
                  total_aprovadas=Questao.objects.filter(revisada=True).count(),
                  fontes=['https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2011/lei/l12527.htm',
                          'https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13105.htm',
                          'https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm'])
    (BASE / f'aprovacao_resultado_{stamp}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    assert Questao.objects.filter(pk__in=saved,revisada=True).count() == len(saved)
    print(json.dumps({k:v for k,v in result.items() if k not in ['mantidas_pendentes','excecoes_conferidas','fontes']},ensure_ascii=False))
    print('Mantidas pendentes:',len(held))

if __name__ == '__main__':
    main()
