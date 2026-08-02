"""
Importa questoes de PDFs oficiais de provas usando o pipeline de IA
(ai_provider: Groq principal, Gemini fallback).

Uso:
    # 1 PDF, banca/ano auto-detectados do filename
    python manage.py importar_pdf_questoes --arquivo "provas_pdf/cespe_prf_2013.pdf"

    # Pasta inteira em lote
    python manage.py importar_pdf_questoes --pasta "provas_pdf/"

    # Com gabarito em PDF separado
    python manage.py importar_pdf_questoes \\
        --arquivo provas_pdf/cespe_prf_2013.pdf \\
        --gabarito provas_pdf/cespe_prf_2013_gab.pdf

    # Sobrescrever banca/ano/categoria manualmente
    python manage.py importar_pdf_questoes --arquivo "..." \\
        --banca CESPE --ano 2013 --categoria "Prova PRF"

    # Gerar justificativa da IA no mesmo passe (mais chamadas)
    python manage.py importar_pdf_questoes --arquivo "..." --com_justificativa

    # Dry-run (imprime amostra, nao salva)
    python manage.py importar_pdf_questoes --arquivo "..." --dry_run

Salva com:
    gerada_por_ia = False   # e prova oficial da banca
    revisada      = False   # entra na fila de aprovacao no admin
    banca, ano    = detectados do filename ou fornecidos
    assunto       = inferido pela IA (opcional)

Depois: /admin/quiz/questao/?revisada__exact=0
"""
import json
import re
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from pypdf import PdfReader

from quiz.models import Questao, Alternativa, Categoria
from quiz.ai_provider import gerar_json, gerar_conteudo, AIError


PROMPT_EXTRACAO = """Voce esta recebendo o TEXTO BRUTO de uma prova de concurso publico.
Extraia TODAS as questoes que conseguir identificar no trecho abaixo.

REGRAS DE EXTRACAO:
- Identifique questoes numeradas (1, 2, 3... ou QUESTAO 1, QUESTAO 2...)
- MULTIPLA ESCOLHA: capture todas as alternativas A/B/C/D/E, com tipo="ME"
- CERTO/ERRADO (Cebraspe/CESPE): tipo="CE", sem alternativas, com resposta_ce="C" ou "E"
- Quando o GABARITO for fornecido abaixo, USE-O como fonte de verdade
- Sem gabarito, marque como correta a que voce infere ser a resposta
- Ignore cabecalhos, rodapes, marcas d'agua (pcimarkpci, www.pciconcursos.com.br)
- Se a questao referencia um texto/imagem/tabela ("com base no texto acima"), inclua o contexto no campo "texto"
- Se ha imagem que voce nao pode ler, adicione no texto: "[FIGURA: descreva o que voce infere do contexto]"
- Nao invente questoes. Se o trecho e ruim/ilegivel, retorne lista vazia
- Preserve pontuacao e formatacao original do enunciado

GABARITO FORNECIDO:
{gabarito}

TEXTO DA PROVA (trecho):
====================
{texto}
====================

Responda SOMENTE com JSON valido no formato:
{{
  "questoes": [
    {{
      "numero": 1,
      "tipo": "ME",
      "texto": "Enunciado completo com contexto se houver",
      "alternativas": [
        {{"letra": "A", "texto": "...", "correta": false}},
        {{"letra": "B", "texto": "...", "correta": true}},
        {{"letra": "C", "texto": "...", "correta": false}},
        {{"letra": "D", "texto": "...", "correta": false}},
        {{"letra": "E", "texto": "...", "correta": false}}
      ],
      "assunto": "topico inferido (ex: Legislacao de Transito, Direito Administrativo)"
    }},
    {{
      "numero": 2,
      "tipo": "CE",
      "texto": "Proposicao a ser julgada",
      "resposta_ce": "C",
      "assunto": "..."
    }}
  ]
}}
"""


PROMPT_JUSTIFICATIVA = """Voce e um professor experiente de concursos publicos.
Explique de forma clara e didatica por que a resposta correta e a indicada,
citando a lei/artigo/principio aplicavel quando pertinente.

QUESTAO:
{enunciado}

{alternativas}

RESPOSTA CORRETA: {correta}

Escreva uma justificativa de 2 a 4 paragrafos, em portugues, tom didatico.
Nao inclua saudacoes nem preambulos. Comece direto pela analise.
"""


# ── Heuristica de auto-detect a partir do filename ───────────────────────
BANCAS_CONHECIDAS = [
    ('cebraspe', 'Cebraspe'),
    ('cespe',    'CESPE'),
    ('funcab',   'FUNCAB'),
    ('funrio',   'FUNRIO'),
    ('fgv',      'FGV'),
    ('vunesp',   'VUNESP'),
    ('quadrix',  'Quadrix'),
    ('nucepe',   'NUCEPE'),
]


def detectar_metadados_filename(nome_arquivo):
    """Extrai banca + ano do nome do arquivo. Retorna (banca, ano)."""
    nome = nome_arquivo.lower()
    banca = None
    for key, label in BANCAS_CONHECIDAS:
        if key in nome:
            banca = label
            break

    m = re.search(r'(19[89]\d|20\d{2})', nome)
    ano = int(m.group(1)) if m else None
    return banca, ano


class Command(BaseCommand):
    help = 'Extrai questoes de PDFs oficiais usando IA (Groq -> Gemini fallback)'

    def add_arguments(self, parser):
        grupo = parser.add_mutually_exclusive_group(required=True)
        grupo.add_argument('--arquivo', type=str,
                           help='Caminho de um unico PDF')
        grupo.add_argument('--pasta', type=str,
                           help='Pasta com varios PDFs (processa em lote)')

        parser.add_argument('--gabarito', type=str, default='',
                            help='PDF de gabarito separado (opcional)')
        parser.add_argument('--categoria', type=str, default='Prova PRF',
                            help='Nome da categoria (cria se nao existir)')
        parser.add_argument('--banca', type=str, default='',
                            help='Sobrescreve banca detectada do filename')
        parser.add_argument('--ano', type=int, default=None,
                            help='Sobrescreve ano detectado do filename')
        parser.add_argument('--chunk_paginas', type=int, default=2,
                            help='Paginas por chamada de IA (default 2 — evita rate limit)')
        parser.add_argument('--delay', type=float, default=4.0,
                            help='Segundos entre chamadas de IA (default 4)')
        parser.add_argument('--max_chars_chunk', type=int, default=6000,
                            help='Tamanho maximo de cada chunk em chars (default 6000)')
        parser.add_argument('--com_justificativa', action='store_true',
                            help='Gera justificativa da IA para cada questao (dobra chamadas)')
        parser.add_argument('--com_figuras', action='store_true',
                            help='Depois de extrair texto, roda extrair_figuras_vision pra '
                                 'anexar figuras precisas via Gemini Vision + PyMuPDF crop')
        parser.add_argument('--dry_run', action='store_true',
                            help='Mostra o que extraiu, nao salva')
        parser.add_argument('--max_questoes', type=int, default=0,
                            help='Limita numero de questoes salvas por PDF (0 = sem limite)')

    def handle(self, *args, **opts):
        if opts['arquivo']:
            arquivos = [Path(opts['arquivo'])]
        else:
            pasta = Path(opts['pasta'])
            if not pasta.is_dir():
                raise CommandError(f'Pasta nao encontrada: {pasta}')
            arquivos = sorted(pasta.glob('*.pdf'))
            if not arquivos:
                raise CommandError(f'Nenhum PDF em {pasta}')
            self.stdout.write(self.style.HTTP_INFO(
                f'\nProcessando {len(arquivos)} PDFs em lote:'
            ))
            for a in arquivos:
                self.stdout.write(f'  - {a.name}')

        categoria, criada = Categoria.objects.get_or_create(
            nome=opts['categoria']
        )
        if criada:
            self.stdout.write(self.style.SUCCESS(
                f'\n+ Categoria criada: "{categoria.nome}"'
            ))

        total_criadas = 0
        total_ignoradas = 0
        for pdf in arquivos:
            self.stdout.write(self.style.HTTP_INFO(
                f'\n{"=" * 60}\n▶ {pdf.name}\n{"=" * 60}'
            ))
            criadas, ignoradas = self._processar_pdf(pdf, categoria, opts)
            total_criadas += criadas
            total_ignoradas += ignoradas

            # Fase pos-texto: extrai figuras via Vision + crop se pedido
            if opts.get('com_figuras') and criadas > 0 and not opts.get('dry_run'):
                self.stdout.write(self.style.HTTP_INFO(
                    f'\n  ▷ [--com_figuras] Extraindo figuras de {pdf.name}...'
                ))
                try:
                    from django.core.management import call_command
                    call_command('extrair_figuras_vision', arquivo=str(pdf))
                except Exception as e:
                    self.stdout.write(self.style.WARNING(
                        f'  Falha extraindo figuras: {type(e).__name__}: {str(e)[:120]}'
                    ))

        self.stdout.write(self.style.SUCCESS(
            f'\n{"=" * 60}\nTOTAL: {total_criadas} questoes salvas'
            f' · {total_ignoradas} ignoradas (duplicadas/curtas)'
        ))
        self.stdout.write(
            '\nRevise no admin: /admin/quiz/questao/?revisada__exact=0'
        )

    # ── Processa um PDF ─────────────────────────────────────────────────
    def _processar_pdf(self, pdf_path, categoria, opts):
        if not pdf_path.exists():
            self.stdout.write(self.style.ERROR(f'  Nao existe: {pdf_path}'))
            return 0, 0

        banca_det, ano_det = detectar_metadados_filename(pdf_path.name)
        banca = opts['banca'] or banca_det
        ano = opts['ano'] or ano_det
        self.stdout.write(
            f'  Banca: {banca or "?"} | Ano: {ano or "?"} | '
            f'Categoria: {categoria.nome}'
        )

        texto_prova = self._extrair_pdf(pdf_path)
        n_pags = texto_prova.count('\x0c') + 1
        self.stdout.write(f'  Texto extraido: {len(texto_prova)} chars, {n_pags} paginas')

        gabarito_texto = '(nenhum gabarito separado — use inferencia)'
        if opts['gabarito']:
            gab_path = Path(opts['gabarito'])
            if gab_path.exists():
                gabarito_texto = self._extrair_pdf(gab_path)[:6000]
                self.stdout.write(f'  Gabarito lido: {len(gabarito_texto)} chars')

        chunks = self._quebrar_em_paginas(
            texto_prova,
            opts['chunk_paginas'],
            opts['max_chars_chunk'],
        )
        self.stdout.write(f'  Dividido em {len(chunks)} chunks para IA\n')

        todas_questoes = []
        for idx, chunk in enumerate(chunks, 1):
            self.stdout.write(f'  Chunk {idx}/{len(chunks)} ({len(chunk)} chars)... ', ending='')
            self.stdout.flush()

            lista = self._extrair_com_retry(chunk, gabarito_texto, max_tentativas=3)
            if lista:
                todas_questoes.extend(lista)
                self.stdout.write(self.style.SUCCESS(f'+{len(lista)} questoes'))
            else:
                self.stdout.write(self.style.WARNING('vazio (chunk pulado)'))

            if opts['delay'] and idx < len(chunks):
                time.sleep(opts['delay'])

        if not todas_questoes:
            self.stdout.write(self.style.ERROR('  Nenhuma questao extraida deste PDF'))
            return 0, 0

        self.stdout.write(self.style.SUCCESS(
            f'\n  ✓ {len(todas_questoes)} questoes extraidas'
        ))

        if opts['max_questoes'] and len(todas_questoes) > opts['max_questoes']:
            todas_questoes = todas_questoes[: opts['max_questoes']]
            self.stdout.write(f'  (limitado a {opts["max_questoes"]})')

        if opts['dry_run']:
            self.stdout.write(self.style.WARNING('\n  [DRY-RUN] Amostra das primeiras 2:'))
            for q in todas_questoes[:2]:
                self.stdout.write(
                    f'    #{q.get("numero","?")} [{q.get("tipo","?")}] '
                    f'{(q.get("texto") or "")[:100]}...'
                )
            return 0, 0

        return self._salvar_questoes(todas_questoes, categoria, banca, ano, opts)

    # ── Salva no banco ───────────────────────────────────────────────────
    def _salvar_questoes(self, lista, categoria, banca, ano, opts):
        from quiz.models import _hash_texto_questao

        criadas = 0
        ignoradas = 0
        dup_hash = 0
        dup_prefixo = 0
        curtas = 0

        with transaction.atomic():
            for q in lista:
                texto_q = (q.get('texto') or '').strip()
                if len(texto_q) < 20:
                    curtas += 1
                    ignoradas += 1
                    continue

                # Dedup 1 (robusto): SHA-256 do texto normalizado.
                # Detecta duplicatas mesmo com espacos/acentos/pontuacao diferente.
                # Busca GLOBAL (nao so por banca/ano/categoria) — a mesma
                # questao em bancas diferentes ainda deve ser dedup.
                hash_novo = _hash_texto_questao(texto_q)
                if hash_novo and Questao.objects.filter(texto_hash=hash_novo).exists():
                    dup_hash += 1
                    ignoradas += 1
                    continue

                # Dedup 2 (fallback): prefixo istartswith. Cobre casos
                # onde a IA parafraseia levemente (hash diferente mas
                # inicio identico). Aplica so no mesmo escopo pra evitar
                # falsos positivos entre bancas.
                filtro_dup = {
                    'categoria': categoria,
                    'texto__istartswith': texto_q[:80],
                }
                if banca:
                    filtro_dup['banca'] = banca
                if ano:
                    filtro_dup['ano'] = ano
                if Questao.objects.filter(**filtro_dup).exists():
                    dup_prefixo += 1
                    ignoradas += 1
                    continue

                # Normaliza tipo — campo eh VARCHAR(2), aceita so ME ou CE.
                # IA as vezes retorna "me", "certo_errado", "multipla_escolha" etc.
                tipo_raw = (q.get('tipo') or 'ME').upper().strip()
                if tipo_raw in ('ME', 'MULTIPLA', 'MULTIPLA_ESCOLHA', 'MULTIPLE'):
                    tipo = 'ME'
                elif tipo_raw in ('CE', 'CERTO_ERRADO', 'C/E', 'TRUE_FALSE'):
                    tipo = 'CE'
                else:
                    # Fallback: se tem resposta_ce definida, eh CE; senao ME
                    tipo = 'CE' if q.get('resposta_ce') else 'ME'

                justificativa = ''
                if opts['com_justificativa']:
                    justificativa = self._gerar_justificativa(q)

                obj = Questao.objects.create(
                    categoria=categoria,
                    texto=texto_q,
                    tipo=tipo,
                    justificativa=justificativa,
                    assunto=(q.get('assunto') or '')[:255] or None,
                    banca=banca or None,
                    ano=ano,
                    revisada=False,
                    gerada_por_ia=False,  # e OFICIAL da banca, nao gerada por IA
                )

                if tipo == 'ME':
                    alts = q.get('alternativas') or []
                    for alt in alts:
                        Alternativa.objects.create(
                            questao=obj,
                            texto=(alt.get('texto') or '').strip(),
                            correta=bool(alt.get('correta')),
                        )
                else:  # CE
                    resp_ce = (q.get('resposta_ce') or 'C').upper()
                    Alternativa.objects.create(questao=obj, texto='Certo',
                                               correta=(resp_ce == 'C'))
                    Alternativa.objects.create(questao=obj, texto='Errado',
                                               correta=(resp_ce == 'E'))
                criadas += 1

        # Relatorio detalhado das ignoradas
        detalhes = []
        if dup_hash:
            detalhes.append(f'{dup_hash} duplicata exata (hash)')
        if dup_prefixo:
            detalhes.append(f'{dup_prefixo} duplicata por prefixo (mesma banca/ano)')
        if curtas:
            detalhes.append(f'{curtas} texto muito curto')
        detalhe_str = ' — ' + '; '.join(detalhes) if detalhes else ''

        self.stdout.write(self.style.SUCCESS(
            f'  ✓ {criadas} salvas · {ignoradas} ignoradas{detalhe_str}'
        ))
        return criadas, ignoradas

    # ── Gera justificativa via IA ────────────────────────────────────────
    def _gerar_justificativa(self, q):
        tipo = q.get('tipo', 'ME')
        enunciado = q.get('texto', '')

        if tipo == 'ME':
            alts = q.get('alternativas') or []
            linhas = [f'{a.get("letra","?")}) {a.get("texto","")}' for a in alts]
            alts_str = '\n'.join(linhas)
            correta = next(
                (a.get('letra') for a in alts if a.get('correta')), '?'
            )
        else:
            alts_str = 'Alternativas: (C) Certo | (E) Errado'
            correta = q.get('resposta_ce', '?').upper()

        prompt = PROMPT_JUSTIFICATIVA.format(
            enunciado=enunciado,
            alternativas=alts_str,
            correta=correta,
        )
        try:
            return gerar_conteudo(prompt, max_tokens=800, temperature=0.3)
        except AIError:
            return ''

    # ── Extracao com retry + backoff ─────────────────────────────────────
    def _extrair_com_retry(self, chunk, gabarito_texto, max_tentativas=3):
        """Chama IA com retry:
          - JSON invalido: retry com temperature 0 e prompt reforcado
          - Rate limit 429: espera o tempo indicado pelo Groq (regex)
        Retorna lista de questoes (pode ser vazia)."""
        prompt_base = PROMPT_EXTRACAO.format(
            gabarito=gabarito_texto,
            texto=chunk,
        )
        for tent in range(1, max_tentativas + 1):
            temp = 0.2 if tent == 1 else 0.0
            prompt = prompt_base
            if tent > 1:
                prompt += ('\n\nATENCAO: sua resposta anterior teve JSON invalido. '
                           'Verifique CUIDADOSAMENTE: aspas duplas, virgulas entre itens, '
                           'sem trailing comma, sem markdown. Retorne SO o JSON.')
            try:
                dados = gerar_json(prompt, max_tokens=4096, temperature=temp)
                lista = dados.get('questoes', []) if isinstance(dados, dict) else []
                if isinstance(lista, list):
                    return lista
                return []
            except AIError as e:
                msg = str(e)
                # Groq indica "try again in Xs" — respeita
                m_wait = re.search(r'try again in ([\d.]+)s', msg)
                if m_wait:
                    espera = min(60, float(m_wait.group(1)) + 1)
                    self.stdout.write(f'[wait {espera:.0f}s]', ending=' ')
                    self.stdout.flush()
                    time.sleep(espera)
                    continue
                if 'quota' in msg.lower() and tent < max_tentativas:
                    time.sleep(5)
                    continue
                if tent >= max_tentativas:
                    return []
            except json.JSONDecodeError:
                if tent >= max_tentativas:
                    return []
                time.sleep(1)
            except Exception:
                if tent >= max_tentativas:
                    return []
                time.sleep(1)
        return []

    # ── Helpers de PDF ───────────────────────────────────────────────────
    def _extrair_pdf(self, caminho):
        """Extrai texto do PDF e limpa marcas d'agua conhecidas."""
        reader = PdfReader(str(caminho))
        partes = []
        for pag in reader.pages:
            try:
                t = pag.extract_text() or ''
            except Exception:
                t = ''
            partes.append(t)
        texto = '\x0c'.join(partes)
        # Remove marcas d'agua do PCI Concursos
        texto = re.sub(r'pcimarkpci\s+\S+', '', texto)
        texto = texto.replace('www.pciconcursos.com.br', '')
        texto = re.sub(r'\n{3,}', '\n\n', texto)
        return texto

    def _quebrar_em_paginas(self, texto, paginas_por_chunk, max_chars):
        """Divide texto em chunks respeitando (a) N paginas e (b) max_chars.
        Se um chunk ficaria maior que max_chars, subdivide por paragrafos."""
        paginas = texto.split('\x0c')
        blocos = []
        for i in range(0, len(paginas), paginas_por_chunk):
            bloco = '\n'.join(paginas[i:i + paginas_por_chunk]).strip()
            if bloco:
                blocos.append(bloco)

        # Segunda passada: quebra blocos grandes por paragrafo
        chunks_finais = []
        for bloco in blocos:
            if len(bloco) <= max_chars:
                chunks_finais.append(bloco)
                continue
            paragrafos = re.split(r'\n\s*\n', bloco)
            atual = ''
            for p in paragrafos:
                if len(atual) + len(p) + 2 <= max_chars:
                    atual = (atual + '\n\n' + p) if atual else p
                else:
                    if atual:
                        chunks_finais.append(atual)
                    atual = p if len(p) <= max_chars else p[:max_chars]
            if atual:
                chunks_finais.append(atual)
        return chunks_finais
