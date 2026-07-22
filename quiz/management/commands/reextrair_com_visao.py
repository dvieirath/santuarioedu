"""
Re-extrai questoes de PDFs usando Gemini Vision multimodal (File API).

Diferente do importar_pdf_questoes.py (que usa pypdf + IA texto), este
comando manda o PDF INTEIRO pro Gemini que enxerga o layout, capturando:
  - Texto de referencia (blocos "Texto CG2A1..." que ficam separados da questao)
  - Descricao de imagens em texto ([FIGURA: mapa do Brasil com ...])
  - Multi-coluna, tabelas etc

Fluxo:
  1. Upload do PDF via Gemini File API
  2. Prompt estruturado -> JSON com questoes completas
  3. Match contra questoes existentes no BD (banca+ano+prefixo fuzzy)
  4. UPDATE do texto quando a nova versao e claramente melhor
  5. Marca revisada=False pra usuario revisar de novo

Uso:
    # Piloto: 1 PDF, dry-run (nao salva)
    python manage.py reextrair_com_visao --arquivo provas_pdf/processados/cespe_prf_2013.pdf --dry_run

    # Aplicar (atualiza BD)
    python manage.py reextrair_com_visao --arquivo provas_pdf/processados/cespe_prf_2013.pdf

    # Pasta inteira
    python manage.py reextrair_com_visao --pasta provas_pdf/processados/

    # So questoes que atualmente estao com flag de imagem/texto ausente
    python manage.py reextrair_com_visao --arquivo ... --so_problematicas
"""
import json
import re
import time
from difflib import SequenceMatcher
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from quiz.models import Questao, Alternativa
from quiz.auditoria import detectar_flags


PROMPT_VISAO = """Voce esta recebendo o PDF de uma prova oficial de concurso publico.
Extraia TODAS as questoes, capturando so os campos abaixo. NAO extraia
alternativas — ja temos elas no banco. So enunciado + apoio + imagem.

REGRAS:
- Numero da questao (1, 2, 3...)
- Enunciado COMPLETO do que a questao pergunta
- Se ha um texto de apoio ("texto CG2A1", "texto acima"), COPIE literal
  no campo "texto_referencia" (senao "")
- Se ha figura/grafico/tabela/mapa, DESCREVA em detalhes no
  "imagem_descricao" (senao "")
- Ignore watermarks

Formato JSON (responda SO isso):
{
  "questoes": [
    {
      "numero": 1,
      "texto": "Enunciado da questao (sem texto de apoio)",
      "texto_referencia": "Texto de apoio integral, se houver",
      "imagem_descricao": "Descricao da figura/grafico/tabela, se houver"
    }
  ]
}
"""


BANCAS_MAP = {
    'cebraspe': 'Cebraspe',
    'cespe':    'CESPE',
    'funcab':   'FUNCAB',
    'funrio':   'FUNRIO',
    'fgv':      'FGV',
}


def detectar_banca_ano(filename):
    nome = filename.lower()
    banca = None
    for key, label in BANCAS_MAP.items():
        if key in nome:
            banca = label
            break
    m = re.search(r'(19[89]\d|20\d{2})', nome)
    ano = int(m.group(1)) if m else None
    return banca, ano


def montar_texto_completo(q_data):
    """Junta texto_referencia (se houver) + texto + [FIGURA: descricao] (se houver)."""
    partes = []
    tr = (q_data.get('texto_referencia') or '').strip()
    if tr:
        partes.append(tr)
        partes.append('---')  # separador visual
    partes.append((q_data.get('texto') or '').strip())
    img = (q_data.get('imagem_descricao') or '').strip()
    if img:
        partes.append(f'\n[FIGURA: {img}]')
    return '\n\n'.join(p for p in partes if p)


def similarity(a, b):
    return SequenceMatcher(None, a[:120], b[:120]).ratio()


class Command(BaseCommand):
    help = 'Re-extrai questoes de PDFs via Gemini Vision (multimodal)'

    def add_arguments(self, parser):
        grupo = parser.add_mutually_exclusive_group(required=True)
        grupo.add_argument('--arquivo', type=str,
                           help='PDF unico')
        grupo.add_argument('--pasta', type=str,
                           help='Pasta com PDFs')
        parser.add_argument('--banca', type=str, default='',
                            help='Override banca detectada')
        parser.add_argument('--ano', type=int, default=None,
                            help='Override ano detectado')
        parser.add_argument('--model', type=str, default='gemini-3.5-flash',
                            help='Modelo Gemini (default 3.5-flash — bom equilibrio vision/custo)')
        parser.add_argument('--dry_run', action='store_true',
                            help='Nao salva no BD, so mostra o que faria')
        parser.add_argument('--so_problematicas', action='store_true',
                            help='So atualiza questoes com flag referencia_a_imagem_sem_imagem '
                                 'ou referencia_a_texto_ausente')
        parser.add_argument('--min_similarity', type=float, default=0.55,
                            help='Similaridade minima pra dar match (0-1, default 0.55)')

    def handle(self, *args, **opts):
        try:
            import google.generativeai as genai
        except ImportError:
            raise CommandError('google-generativeai nao instalado')
        api_key = getattr(settings, 'GEMINI_API_KEY', '')
        if not api_key:
            raise CommandError('GEMINI_API_KEY nao configurada')
        genai.configure(api_key=api_key)

        if opts['arquivo']:
            arquivos = [Path(opts['arquivo'])]
        else:
            pasta = Path(opts['pasta'])
            if not pasta.is_dir():
                raise CommandError(f'Pasta nao encontrada: {pasta}')
            arquivos = sorted(pasta.glob('*.pdf'))
            if not arquivos:
                raise CommandError(f'Nenhum PDF em {pasta}')

        total_upd = 0
        total_criadas = 0
        total_puladas = 0
        for pdf in arquivos:
            self.stdout.write(self.style.HTTP_INFO(
                f'\n{"=" * 60}\n▶ {pdf.name}\n{"=" * 60}'
            ))
            u, c, p = self._processar_pdf(pdf, opts, genai)
            total_upd += u
            total_criadas += c
            total_puladas += p

        self.stdout.write(self.style.SUCCESS(
            f'\n{"=" * 60}\n'
            f'TOTAL: {total_upd} atualizadas · {total_criadas} novas · {total_puladas} puladas'
        ))
        if opts['dry_run']:
            self.stdout.write(self.style.WARNING('[DRY-RUN] Nada foi salvo no BD'))

    def _processar_pdf(self, pdf_path, opts, genai):
        if not pdf_path.exists():
            self.stdout.write(self.style.ERROR(f'  Nao existe: {pdf_path}'))
            return 0, 0, 0

        banca_det, ano_det = detectar_banca_ano(pdf_path.name)
        banca = opts['banca'] or banca_det
        ano = opts['ano'] or ano_det
        self.stdout.write(f'  Banca: {banca or "?"} | Ano: {ano or "?"}')

        # Upload via File API
        self.stdout.write('  Upload PDF pro Gemini File API... ', ending='')
        self.stdout.flush()
        try:
            uploaded = genai.upload_file(path=str(pdf_path))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'FALHOU: {e}'))
            return 0, 0, 0
        self.stdout.write(self.style.SUCCESS(f'ok ({uploaded.name})'))

        # Gera com Vision
        self.stdout.write('  Extraindo com Gemini Vision... ', ending='')
        self.stdout.flush()
        model = genai.GenerativeModel(opts['model'])
        try:
            resp = model.generate_content(
                [PROMPT_VISAO, uploaded],
                generation_config={
                    'temperature': 0.1,
                    'max_output_tokens': 60000,
                    'response_mime_type': 'application/json',
                },
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'FALHOU: {type(e).__name__}: {str(e)[:120]}'))
            try:
                genai.delete_file(uploaded.name)
            except Exception:
                pass
            return 0, 0, 0

        # Limpa o file upload (nao precisa ficar consumindo cota)
        try:
            genai.delete_file(uploaded.name)
        except Exception:
            pass

        # Verifica se Gemini bloqueou por safety/recitation ANTES de acessar .text
        # finish_reason: 1=STOP, 2=MAX_TOKENS, 3=SAFETY, 4=RECITATION, 5=LANGUAGE, 6=OTHER
        try:
            finish = getattr(resp.candidates[0], 'finish_reason', None) if resp.candidates else None
        except Exception:
            finish = None
        finish_num = int(finish) if finish is not None else 1
        if finish_num not in (1, 2):
            razoes = {3: 'SAFETY', 4: 'RECITATION (copyright)', 5: 'LANGUAGE', 6: 'OTHER'}
            razao = razoes.get(finish_num, f'finish_reason={finish_num}')
            self.stdout.write(self.style.WARNING(
                f'  Gemini bloqueou: {razao} — pulando PDF'
            ))
            return 0, 0, 0

        try:
            raw = (resp.text or '').strip()
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  Sem texto extraido: {str(e)[:80]}'))
            return 0, 0, 0
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        try:
            dados = json.loads(raw)
        except json.JSONDecodeError as e:
            self.stdout.write(self.style.ERROR(f'JSON invalido: {e}'))
            return 0, 0, 0
        questoes_novas = dados.get('questoes', []) if isinstance(dados, dict) else []
        self.stdout.write(self.style.SUCCESS(f'ok ({len(questoes_novas)} questoes extraidas)'))

        # Match contra BD
        filtro = {}
        if banca:
            filtro['banca'] = banca
        if ano:
            filtro['ano'] = ano
        candidatas_qs = Questao.objects.filter(**filtro).prefetch_related('alternativa_set')

        if opts['so_problematicas']:
            problematicas_ids = []
            for q in candidatas_qs:
                alts = list(q.alternativa_set.all())
                flags = set(detectar_flags(q, alts))
                if 'referencia_a_imagem_sem_imagem' in flags or 'referencia_a_texto_ausente' in flags:
                    problematicas_ids.append(q.id)
            candidatas_qs = candidatas_qs.filter(id__in=problematicas_ids)
            self.stdout.write(f'  Restringido a {candidatas_qs.count()} questoes problematicas')

        candidatas = list(candidatas_qs)
        self.stdout.write(f'  Comparando com {len(candidatas)} questoes existentes...')

        atualizadas, criadas, puladas = 0, 0, 0
        min_sim = opts['min_similarity']
        with transaction.atomic():
            for q_data in questoes_novas:
                # Enunciado curto (so a pergunta) — usado pra dar MATCH contra o BD
                enunciado = (q_data.get('texto') or '').strip()
                # Versao completa (com texto de apoio + descricao de figura) —
                # sera o que grava no BD substituindo o texto quebrado
                novo_texto = montar_texto_completo(q_data)
                if len(enunciado) < 30:
                    puladas += 1
                    continue

                # Busca melhor match — compara o enunciado limpo contra o texto
                # existente no BD (que tambem e so o enunciado, sem apoio)
                melhor = None
                melhor_sim = 0.0
                for c in candidatas:
                    existente = c.texto or ''
                    # tenta match tanto no inicio (enunciado direto) quanto no
                    # fim (caso o texto existente termine com o enunciado)
                    sim_a = SequenceMatcher(None, enunciado[:150], existente[:150]).ratio()
                    sim_b = SequenceMatcher(None, enunciado[:150], existente[-150:]).ratio()
                    sim = max(sim_a, sim_b)
                    if sim > melhor_sim:
                        melhor_sim = sim
                        melhor = c

                if melhor and melhor_sim >= min_sim:
                    # Match: UPDATE se o novo tem mais conteudo (texto_ref ou imagem_descricao)
                    tem_extra = bool((q_data.get('texto_referencia') or '').strip()
                                     or (q_data.get('imagem_descricao') or '').strip())
                    if not tem_extra:
                        # Novo nao adiciona nada novo — pula
                        puladas += 1
                        continue

                    if opts['dry_run']:
                        self.stdout.write(
                            f'    [match {melhor_sim:.0%}] Q#{melhor.id}: +{len(novo_texto) - len(melhor.texto)} chars'
                        )
                    else:
                        melhor.texto = novo_texto
                        melhor.revisada = False
                        melhor.motivo_rejeicao = ''
                        melhor.save(update_fields=['texto', 'revisada', 'motivo_rejeicao'])
                    atualizadas += 1
                    # remove da lista pra nao dar match dobrado
                    candidatas.remove(melhor)
                else:
                    # Sem match — pula (nao criar novas neste modo, evita duplicatas)
                    puladas += 1

        self.stdout.write(self.style.SUCCESS(
            f'  ✓ {atualizadas} atualizadas · {criadas} novas · {puladas} puladas'
        ))
        return atualizadas, criadas, puladas
