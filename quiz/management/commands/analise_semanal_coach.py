"""
Analise semanal automatica do coach IA — todo domingo o coach analisa
a semana do user e envia uma mensagem estruturada no chat.

Rodar via cron:
    0 20 * * 0  python manage.py analise_semanal_coach

A mensagem contem:
- Stats da semana (questoes, acerto, XP, streak)
- Comparativo com semana anterior
- Analise das disciplinas mais e menos estudadas
- 1-2 acoes concretas pra proxima semana
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Q
from django.db import connections

from quiz.models import (MensagemCoachIA, RespostaUsuario, NivelUsuario,
                          MetaEstudo, ConcursoPreferido)


def _reconectar_db():
    for conn in connections.all():
        try:
            conn.close_if_unusable_or_obsolete()
            conn.ensure_connection()
        except Exception:
            try: conn.close()
            except Exception: pass


class Command(BaseCommand):
    help = 'Gera analise semanal do coach IA pra cada usuario ativo'

    def add_arguments(self, parser):
        parser.add_argument('--dry_run', action='store_true')
        parser.add_argument('--user_id', type=int, default=None)

    def handle(self, *args, **opts):
        dry_run = opts['dry_run']
        user_id = opts['user_id']

        from django.contrib.auth import get_user_model
        User = get_user_model()

        # User ativo: >= 5 respostas na semana passada
        semana_atras = timezone.now() - timedelta(days=7)

        if user_id:
            users = User.objects.filter(id=user_id)
        else:
            users_ids = (RespostaUsuario.objects
                .filter(data__gte=semana_atras)
                .values('usuario_id')
                .annotate(n=Count('id'))
                .filter(n__gte=5)
                .values_list('usuario_id', flat=True))
            users = User.objects.filter(id__in=list(users_ids))

        total = 0
        for user in users:
            _reconectar_db()
            if self._gerar_analise(user, dry_run):
                total += 1

        self.stdout.write(self.style.SUCCESS(
            f'\n✓ {total} analise{("s" if total != 1 else "")} semanal{("is" if total > 1 else "")} '
            f'{"seriam geradas" if dry_run else "geradas"}'
        ))

    def _gerar_analise(self, user, dry_run):
        agora = timezone.now()
        semana = agora - timedelta(days=7)
        duas_semanas = agora - timedelta(days=14)

        # Stats semana atual
        rs_atual = RespostaUsuario.objects.filter(usuario=user, data__gte=semana)
        n_atual = rs_atual.count()
        acertos_atual = rs_atual.filter(acertou=True).count()
        pct_atual = round(acertos_atual / n_atual * 100) if n_atual else 0

        if n_atual < 5:
            return False  # user com menos de 5 questoes, pula

        # Stats semana anterior (pra comparativo)
        rs_anterior = RespostaUsuario.objects.filter(
            usuario=user, data__gte=duas_semanas, data__lt=semana,
        )
        n_anterior = rs_anterior.count()
        acertos_anterior = rs_anterior.filter(acertou=True).count()
        pct_anterior = round(acertos_anterior / n_anterior * 100) if n_anterior else 0

        # Streak + nivel
        try:
            meta = user.meta
            streak = meta.streak_atual
        except Exception:
            streak = 0

        try:
            nivel = user.nivelusuario
            xp = nivel.xp_total
        except Exception:
            xp = 0

        # Top disciplinas da semana
        top_cats = (rs_atual
            .values('questao__categoria__nome')
            .annotate(n=Count('id'), acertos=Count('id', filter=Q(acertou=True)))
            .order_by('-n')[:3])

        # Concurso preferido
        pref = ConcursoPreferido.objects.filter(usuario=user).first()
        concurso = pref.get_concurso_display() if pref else None

        # Prompt IA
        stats_texto = f'''
DADOS DA SEMANA de {user.first_name or user.username}:
- Questoes respondidas: {n_atual} (semana anterior: {n_anterior})
- Acertos: {acertos_atual}/{n_atual} ({pct_atual}%) (semana anterior: {pct_anterior}%)
- Streak atual: {streak} dias
- XP total: {xp}
- Concurso alvo: {concurso or "nao definido"}

TOP DISCIPLINAS ESSA SEMANA:
'''
        for c in top_cats:
            nome = c['questao__categoria__nome'] or 'Sem categoria'
            pct = round(c['acertos'] / c['n'] * 100) if c['n'] else 0
            stats_texto += f'  - {nome}: {c["n"]} questoes ({pct}% acerto)\n'

        prompt = (
            'Voce e um coach de concurso publico. Analise a semana do usuario '
            'com os dados abaixo e envie UMA mensagem estruturada em markdown '
            '(3-4 paragrafos, max 350 palavras). Estrutura:\n\n'
            '1. Como foi a semana (numeros concretos, comparativo com anterior)\n'
            '2. O que foi bem (destacar algo positivo)\n'
            '3. Onde melhorar (disciplina mais fraca ou padrao preocupante)\n'
            '4. 1-2 acoes concretas pra proxima semana\n\n'
            'Tom: coach amigo, direto, sem exageros motivacionais. Portugues brasileiro.\n\n'
            + stats_texto
        )

        if dry_run:
            self.stdout.write(f'  [DRY] {user.username} — {n_atual} q, {pct_atual}%')
            return True

        try:
            from quiz.ai_provider import gerar_conteudo, AIError
            texto = gerar_conteudo(prompt, max_tokens=800, temperature=0.5)
            if not texto or len(texto) < 100:
                return False

            _reconectar_db()
            MensagemCoachIA.objects.create(
                usuario=user, papel='assistant',
                conteudo=texto.strip(), origem='analise_semanal',
            )

            # Notificacao pra chamar atencao
            from quiz.models import Notificacao
            Notificacao.objects.create(
                usuario=user, tipo='sistema',
                titulo='📊 Sua análise semanal chegou',
                mensagem=f'Você respondeu {n_atual} questões ({pct_atual}% acerto). Ver detalhes no coach.',
                link='/coach/',
            )

            self.stdout.write(self.style.SUCCESS(f'  ✓ {user.username} ({n_atual} q)'))
            return True
        except AIError as e:
            self.stdout.write(self.style.ERROR(f'  ✗ {user.username}: {e}'))
            return False
