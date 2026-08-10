"""
Cleanup final das categorias "Prova X" no BD.

1. Move TODAS as questoes de categorias comecando com "Prova " pra
   bucket permanente "Questoes Especializadas"
2. Deleta as categorias "Prova X" (agora vazias)

Idempotente: se ja rodou, nao faz nada.

Uso em prod:
    railway run python manage.py limpar_categorias_prova
    railway run python manage.py limpar_categorias_prova --dry_run  # preview

Depois de rodar isto, recomendado tambem:
    railway run python manage.py reclassificar_por_tema
"""
from django.core.management.base import BaseCommand
from django.db import transaction, connections

from quiz.models import Questao, Categoria


def _reconectar_db():
    for conn in connections.all():
        try:
            conn.close_if_unusable_or_obsolete()
            conn.ensure_connection()
        except Exception:
            try: conn.close()
            except Exception: pass


class Command(BaseCommand):
    help = 'Move questoes de categorias "Prova X" pra bucket "Questoes Especializadas" e deleta as vazias'

    def add_arguments(self, parser):
        parser.add_argument('--dry_run', action='store_true',
                            help='Mostra o que seria feito sem executar')
        parser.add_argument('--bucket_nome', type=str, default='Questões Especializadas',
                            help='Nome do bucket destino (default: "Questoes Especializadas")')

    def handle(self, *args, **opts):
        dry_run = opts['dry_run']
        bucket_nome = opts['bucket_nome']

        _reconectar_db()

        # 1. Levantar categorias "Prova X"
        prova_cats = list(Categoria.objects.filter(nome__startswith='Prova '))
        if not prova_cats:
            self.stdout.write(self.style.SUCCESS(
                '✓ Nenhuma categoria "Prova X" encontrada. BD ja esta limpo.'
            ))
            return

        # 2. Contar questoes
        total_questoes = 0
        detalhamento = []
        for c in prova_cats:
            n = Questao.objects.filter(categoria=c).count()
            detalhamento.append((c.nome, n))
            total_questoes += n

        self.stdout.write(self.style.HTTP_INFO(
            f'\n═══ {len(prova_cats)} categorias "Prova X" · {total_questoes} questoes ═══\n'
        ))
        for nome, n in sorted(detalhamento, key=lambda x: -x[1]):
            if n > 0:
                self.stdout.write(f'  {nome:45s} {n} questoes')

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'\n[DRY RUN] Seriam movidas {total_questoes} questoes pra bucket "{bucket_nome}"'
                f' e {len(prova_cats)} categorias "Prova X" deletadas.'
            ))
            return

        # 3. Cria bucket se nao existe (sem transaction wrap — cada batch
        # eh atomico por natureza do SQL, e reconectar_db mata transacao)
        _reconectar_db()
        bucket, criado = Categoria.objects.get_or_create(
            nome=bucket_nome, parent=None,
        )
        if criado:
            self.stdout.write(self.style.SUCCESS(
                f'\n✓ Bucket "{bucket_nome}" criado (id={bucket.id})'
            ))
        else:
            self.stdout.write(f'\nBucket "{bucket_nome}" ja existia (id={bucket.id})')

        # 4. Move questoes em batch — cada UPDATE eh atomico independente
        self.stdout.write(f'\nMovendo {total_questoes} questoes...')
        BATCH = 500
        movidas = 0
        bucket_id = bucket.id  # cacheia pra usar apos reconectar
        for c in prova_cats:
            _reconectar_db()
            ids = list(Questao.objects.filter(categoria=c).values_list('id', flat=True))
            for i in range(0, len(ids), BATCH):
                batch_ids = ids[i:i+BATCH]
                _reconectar_db()
                # Cada UPDATE dentro de sua propria transacao implicita
                n = Questao.objects.filter(id__in=batch_ids).update(categoria_id=bucket_id)
                movidas += n
            if len(ids) > 0:
                self.stdout.write(f'  → {c.nome}: {len(ids)} questoes movidas')

        # 5. Deleta categorias Prova X vazias
        _reconectar_db()
        n_deletadas, _ = Categoria.objects.filter(
            nome__startswith='Prova '
        ).delete()

        # 6. Snapshot final
        _reconectar_db()
        final = Questao.objects.filter(categoria=bucket).count()

        self.stdout.write('\n' + '═' * 60)
        self.stdout.write(self.style.SUCCESS(
            f'✓ {movidas} questoes movidas pra "{bucket_nome}"'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'✓ {n_deletadas} categorias "Prova X" deletadas'
        ))
        self.stdout.write(f'\n"{bucket_nome}" agora tem {final} questoes total.')
        self.stdout.write(self.style.HTTP_INFO(
            '\nProximo passo (recomendado):\n'
            '  python manage.py reclassificar_por_tema'
        ))
