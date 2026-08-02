"""
Reposicao semanal de streak freezes.

Regras:
- Free tier: repoe 1 freeze/semana ate cap de 1
- PRO/Premium tier: repoe 1 freeze/semana ate cap de 3

Agendar via Railway Cron toda segunda-feira 06h UTC (~03h Brasilia):
    0 6 * * 1  python manage.py repor_streak_freezes

Uso:
    python manage.py repor_streak_freezes         # roda para todos
    python manage.py repor_streak_freezes --dry_run
    python manage.py repor_streak_freezes --usuario alice
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Repoe 1 streak freeze semanal por usuario ativo (respeitando cap do plano)'

    def add_arguments(self, parser):
        parser.add_argument('--dry_run', action='store_true',
                            help='Nao aplica alteracoes, so mostra o plano')
        parser.add_argument('--usuario', type=str, default=None,
                            help='Rodar apenas pra este username (teste)')

    def handle(self, *args, **opts):
        from quiz.models import MetaEstudo

        qs = MetaEstudo.objects.filter(usuario__is_active=True)
        if opts.get('usuario'):
            qs = qs.filter(usuario__username=opts['usuario'])

        total = qs.count()
        self.stdout.write(self.style.HTTP_INFO(
            f'\n═══ Reposicao de freezes: {total} usuarios ═══'
        ))
        if opts['dry_run']:
            self.stdout.write(self.style.WARNING('[DRY RUN] Nao salva\n'))

        repostos = 0
        ja_no_cap = 0

        for meta in qs.select_related('usuario', 'usuario__plano').iterator():
            cap = meta.cap_freezes()
            if meta.streak_freezes >= cap:
                ja_no_cap += 1
                continue

            if opts['dry_run']:
                self.stdout.write(
                    f'  + {meta.usuario.username}: {meta.streak_freezes} -> '
                    f'{min(meta.streak_freezes + 1, cap)} (cap {cap})'
                )
            else:
                meta.repor_freeze()

            repostos += 1

        self.stdout.write('\n' + '═' * 60)
        self.stdout.write(self.style.SUCCESS(
            f'✓ {repostos} freezes {"seriam repostos" if opts["dry_run"] else "repostos"}'
        ))
        if ja_no_cap:
            self.stdout.write(f'= {ja_no_cap} usuarios ja no cap (sem reposicao)')
