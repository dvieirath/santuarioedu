"""
Gera questões em lote para MÚLTIPLAS categorias de uma vez.

Uso:
    # Gera 100 questões para cada categoria existente (Cebraspe ME)
    python manage.py gerar_lote_completo --por_categoria 100

    # Apenas categorias específicas
    python manage.py gerar_lote_completo --por_categoria 50 --categorias "Direito Constitucional,Direito Administrativo,Língua Portuguesa"

    # Preset PRF (distribuição realista do edital)
    python manage.py gerar_lote_completo --preset prf

    # Preset INSS
    python manage.py gerar_lote_completo --preset inss

    # Modo dry-run (mostra o plano sem rodar)
    python manage.py gerar_lote_completo --preset prf --dry_run
"""
import sys
import time
from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command

from quiz.models import Categoria


# ── Presets de distribuição por edital ──────────────────────────────────────
# Estrutura: (categoria, qtd, banca, tipo, assunto_opcional)
PRESETS = {
    'prf': [
        ('Língua Portuguesa',              150, 'Cebraspe', 'ME', ''),
        ('Direito Constitucional',         100, 'Cebraspe', 'ME', ''),
        ('Direito Administrativo',         100, 'Cebraspe', 'ME', ''),
        ('Raciocínio Lógico e Matemática',  80, 'Cebraspe', 'ME', ''),
        ('Informática',                     80, 'Cebraspe', 'ME', ''),
        ('Segurança Pública',               80, 'Cebraspe', 'ME', ''),
        ('Conhecimentos Específicos',      100, 'Cebraspe', 'ME', 'Legislação de trânsito'),
    ],
    'inss': [
        ('Língua Portuguesa',              120, 'Cesgranrio', 'ME', ''),
        ('Raciocínio Lógico e Matemática',  80, 'Cesgranrio', 'ME', ''),
        ('Informática',                     60, 'Cesgranrio', 'ME', ''),
        ('Direito Constitucional',          80, 'Cesgranrio', 'ME', ''),
        ('Direito Administrativo',          80, 'Cesgranrio', 'ME', ''),
        ('Conhecimentos Específicos',      150, 'Cesgranrio', 'ME', 'Direito Previdenciário e Seguridade Social'),
    ],
    'pf': [
        ('Língua Portuguesa',              120, 'Cebraspe', 'CE', ''),
        ('Direito Constitucional',         100, 'Cebraspe', 'CE', ''),
        ('Direito Administrativo',         100, 'Cebraspe', 'CE', ''),
        ('Direito Penal',                  150, 'Cebraspe', 'CE', ''),
        ('Direito Processual Penal',        80, 'Cebraspe', 'CE', ''),
        ('Informática',                     60, 'Cebraspe', 'CE', ''),
    ],
    'tjdf': [
        ('Língua Portuguesa',               80, 'FGV', 'ME', ''),
        ('Direito Constitucional',          80, 'FGV', 'ME', ''),
        ('Direito Administrativo',          80, 'FGV', 'ME', ''),
        ('Direito Civil',                  100, 'FGV', 'ME', ''),
        ('Direito Processual Civil',       100, 'FGV', 'ME', ''),
        ('Raciocínio Lógico e Matemática',  60, 'FGV', 'ME', ''),
    ],
}


class Command(BaseCommand):
    help = 'Gera questões em lote para várias categorias ao mesmo tempo'

    def add_arguments(self, parser):
        parser.add_argument('--preset', type=str, default=None,
                            choices=list(PRESETS.keys()),
                            help='Distribuição pré-definida (prf, inss, pf, tjdf)')
        parser.add_argument('--por_categoria', type=int, default=None,
                            help='Gerar N questões novas para cada categoria (modo incremental)')
        parser.add_argument('--meta', type=int, default=None,
                            help='Meta absoluta: gera ate ter N questoes IA em cada categoria. '
                                 'Ex: --meta 1000 e categoria ja tem 300 IA -> gera so 700 novas.')
        parser.add_argument('--categorias', type=str, default=None,
                            help='Nomes separados por vírgula. Aceita paths hierarquicos: '
                                 '"Direito > Direito Constitucional,Ciências da Natureza > Biologia"')
        parser.add_argument('--incluir_subarvore', action='store_true',
                            help='Se categoria tem filhos, aplica meta em cada folha da subarvore')
        parser.add_argument('--banca', type=str, default='Cebraspe',
                            help='Banca para todas (default Cebraspe)')
        parser.add_argument('--tipo', type=str, default='ME', choices=['ME', 'CE'])
        parser.add_argument('--batch', type=int, default=5,
                            help='Por chamada à IA')
        parser.add_argument('--delay', type=float, default=3.0,
                            help='Segundos entre chamadas')
        parser.add_argument('--inter_categoria_delay', type=float, default=10.0,
                            help='Espera entre categorias (cooldown anti-rate-limit)')
        parser.add_argument('--dry_run', action='store_true',
                            help='Mostra o plano sem executar')

    def handle(self, *args, **opts):
        # Decide o plano (lista de tuplas)
        plano = self._montar_plano(opts)
        if not plano:
            raise CommandError('Plano vazio. Use --preset, --por_categoria ou --categorias.')

        total = sum(item[1] for item in plano)
        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(self.style.HTTP_INFO(
            f'PLANO DE GERAÇÃO — {len(plano)} categorias, {total} questões totais'
        ))
        self.stdout.write('=' * 70)
        for cat, qtd, banca, tipo, assunto in plano:
            extra = f' · {assunto}' if assunto else ''
            self.stdout.write(f'  {cat:38s} {qtd:>4} questões · {banca} · {tipo}{extra}')
        self.stdout.write('=' * 70 + '\n')

        if opts['dry_run']:
            self.stdout.write(self.style.WARNING('--dry_run ativado: nada será gerado.\n'))
            return

        # Confirmação interativa
        try:
            resp = input('Confirma a geração? [s/N] ').strip().lower()
        except EOFError:
            resp = 's'
        if resp != 's':
            self.stdout.write(self.style.WARNING('Abortado.'))
            return

        # Executa
        delay_inter = opts['inter_categoria_delay']
        total_geradas, falhas = 0, 0
        inicio = time.time()

        for idx, (cat_nome, qtd, banca, tipo, assunto) in enumerate(plano, 1):
            self.stdout.write('\n' + self.style.HTTP_INFO(
                f'[{idx}/{len(plano)}] {cat_nome} ({qtd} questões)'
            ))
            self.stdout.write('-' * 70)

            try:
                # Conta antes
                from quiz.models import Questao
                antes = Questao.objects.filter(gerada_por_ia=True).count()

                call_command(
                    'gerar_questoes_ia',
                    categoria=cat_nome,
                    qtd=qtd,
                    batch=opts['batch'],
                    banca=banca,
                    tipo=tipo,
                    assunto=assunto,
                    delay=opts['delay'],
                )

                depois = Questao.objects.filter(gerada_por_ia=True).count()
                feitas = depois - antes
                total_geradas += feitas
                if feitas < qtd:
                    falhas += (qtd - feitas)
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING('\n[interrompido pelo usuário]'))
                break
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ✗ Erro em "{cat_nome}": {e}'))
                falhas += qtd
                continue

            if idx < len(plano) and delay_inter > 0:
                self.stdout.write(f'  ⏸  Pausa de {delay_inter}s antes da próxima categoria…')
                try:
                    time.sleep(delay_inter)
                except KeyboardInterrupt:
                    break

        # Resumo final
        elapsed = int(time.time() - inicio)
        mins, secs = divmod(elapsed, 60)
        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(self.style.SUCCESS(
            f'✓ {total_geradas} questões geradas em {mins}min {secs}s'
        ))
        if falhas:
            self.stdout.write(self.style.WARNING(f'⚠ {falhas} faltaram (quota esgotada ou erros)'))
        self.stdout.write(
            '\nPróximos passos:\n'
            '  1. Acesse /admin/quiz/questao/?revisada__exact=0&gerada_por_ia__exact=1\n'
            '  2. Revise as questões e use action "✓ Aprovar"\n'
            '  3. Aprovadas viram visíveis aos usuários automaticamente.\n'
        )

    def _montar_plano(self, opts):
        """Decide a lista (cat, qtd, banca, tipo, assunto) com base nos args."""
        if opts['preset']:
            return PRESETS[opts['preset']]

        banca = opts['banca']; tipo = opts['tipo']

        # Modo --meta: calcula quanto falta pra atingir a meta absoluta
        # em cada categoria (checa quantas IA ja tem).
        meta = opts.get('meta')

        # Resolve nomes/paths pra objetos Categoria
        if opts['categorias']:
            cats = self._resolver_categorias(opts['categorias'], opts.get('incluir_subarvore'))
        elif opts['por_categoria'] or meta:
            cats = list(Categoria.objects.all())
        else:
            return []

        plano = []
        for cat in cats:
            if meta:
                from quiz.models import Questao
                ja_tem = Questao.objects.filter(categoria=cat, gerada_por_ia=True).count()
                faltam = max(0, meta - ja_tem)
                if faltam == 0:
                    self.stdout.write(f'  ✓ {cat.nome}: ja tem {ja_tem}/{meta} — skip')
                    continue
                plano.append((cat.nome, faltam, banca, tipo, ''))
                self.stdout.write(f'  → {cat.nome}: ja tem {ja_tem}/{meta}, gera {faltam}')
            else:
                qtd = opts['por_categoria'] or 50
                plano.append((cat.nome, qtd, banca, tipo, ''))
        return plano

    def _resolver_categorias(self, csv_paths, incluir_subarvore):
        """Aceita nomes simples OU paths tipo 'Direito > Direito Constitucional'.
        Retorna lista de objetos Categoria."""
        resultado = []
        for item in csv_paths.split(','):
            item = item.strip()
            if not item:
                continue
            partes = [p.strip() for p in item.split('>')]
            # Busca cascata: primeiro tenta nome exato, depois path
            cat = None
            if len(partes) == 1:
                cat = Categoria.objects.filter(nome__iexact=partes[0]).first()
            else:
                cat = None
                for i, nome in enumerate(partes):
                    cat = Categoria.objects.filter(
                        nome__iexact=nome, parent=cat if i > 0 else None,
                    ).first()
                    if not cat:
                        break

            if not cat:
                self.stderr.write(f'  ⚠ Categoria nao encontrada: {item}')
                continue

            if incluir_subarvore:
                # Adiciona TODAS as folhas da subarvore (categorias sem filhos)
                for sub_id in cat.subarvore_ids():
                    sub = Categoria.objects.get(pk=sub_id)
                    if not sub.filhos.exists():  # folha
                        resultado.append(sub)
            else:
                resultado.append(cat)
        return resultado
