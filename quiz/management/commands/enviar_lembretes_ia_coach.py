"""
Meta-lembretes IA — coach dispara mensagens proativas no chat baseado
em heuristicas do comportamento do user.

Rodar diariamente via cron:
    0 12 * * *  python manage.py enviar_lembretes_ia_coach

Regras (uma mensagem por dia por regra, dedup via cache):
1. Streak em risco: user com streak >= 3 dias sem responder ha 20h+
2. Disciplina fraca esquecida: gap top 1 sem revisao ha 5+ dias
3. Prova em <30 dias: intensificar frequencia (1x por semana)
4. Cronograma edital nao acompanhado: se meta abaixo por 3 dias

IA gera texto personalizado baseado no contexto.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.core.cache import cache
from django.db import connections

from quiz.models import (MensagemCoachIA, MetaEstudo, RespostaUsuario,
                          ConcursoPreferido, EditalPersonalizado)


def _reconectar_db():
    for conn in connections.all():
        try:
            conn.close_if_unusable_or_obsolete()
            conn.ensure_connection()
        except Exception:
            try: conn.close()
            except Exception: pass


class Command(BaseCommand):
    help = 'Envia meta-lembretes IA proativos no chat do coach'

    def add_arguments(self, parser):
        parser.add_argument('--dry_run', action='store_true')
        parser.add_argument('--user_id', type=int, default=None,
                            help='Rodar so pra um user especifico (debug)')

    def handle(self, *args, **opts):
        dry_run = opts['dry_run']
        user_id = opts['user_id']

        from django.contrib.auth import get_user_model
        User = get_user_model()

        if user_id:
            users = User.objects.filter(id=user_id)
        else:
            # Users ativos: com ao menos 1 resposta nos ultimos 30 dias
            trinta_dias = timezone.now() - timedelta(days=30)
            users_ids = RespostaUsuario.objects.filter(
                data__gte=trinta_dias
            ).values_list('usuario_id', flat=True).distinct()
            users = User.objects.filter(id__in=users_ids)

        total_enviados = 0
        for user in users:
            _reconectar_db()
            enviado = self._processar_user(user, dry_run)
            if enviado:
                total_enviados += 1

        self.stdout.write(self.style.SUCCESS(
            f'\n✓ {total_enviados} lembrete{("s" if total_enviados != 1 else "")} '
            f'{"seriam enviados" if dry_run else "enviados"}'
        ))

    def _processar_user(self, user, dry_run):
        """Aplica regras em ordem, primeiro match dispara. Um lembrete/dia por user."""
        cache_key = f'lembrete_ia_coach:{user.id}:{timezone.localdate().isoformat()}'
        if cache.get(cache_key):
            return False  # ja enviou hoje

        # Regra 1: Streak em risco
        try:
            meta = user.meta
            if meta.streak_atual >= 3:
                ultimo = RespostaUsuario.objects.filter(usuario=user).order_by('-data').first()
                if ultimo:
                    horas = (timezone.now() - ultimo.data).total_seconds() / 3600
                    if horas >= 20 and horas < 30:
                        return self._gerar_e_enviar(
                            user, dry_run,
                            'streak_risco',
                            f'user com streak de {meta.streak_atual} dias mas sem responder ha {int(horas)}h',
                            cache_key,
                        )
        except Exception:
            pass

        # Regra 2: Prova proxima (<30 dias)
        pref = ConcursoPreferido.objects.filter(usuario=user).first()
        if pref and pref.dias_para_prova is not None and pref.dias_para_prova > 0:
            if pref.dias_para_prova <= 30:
                # 1x por semana
                cache_key_semanal = f'lembrete_prova:{user.id}:{timezone.localdate().isoformat()[:7]}'
                if not cache.get(cache_key_semanal):
                    if self._gerar_e_enviar(
                        user, dry_run,
                        'prova_proxima',
                        f'faltam {pref.dias_para_prova} dias pra prova do {pref.get_concurso_display()}',
                        cache_key,
                    ):
                        cache.set(cache_key_semanal, 1, 7 * 86400)
                        return True

        # Regra 3: Sem responder ha 3+ dias
        ultimo = RespostaUsuario.objects.filter(usuario=user).order_by('-data').first()
        if ultimo:
            dias = (timezone.now() - ultimo.data).days
            if 3 <= dias <= 7:
                return self._gerar_e_enviar(
                    user, dry_run,
                    'ausencia',
                    f'user sumido ha {dias} dias — reengajamento',
                    cache_key,
                )

        return False

    def _gerar_e_enviar(self, user, dry_run, tipo, contexto, cache_key):
        """Gera texto via IA + salva como mensagem coach."""
        pref = ConcursoPreferido.objects.filter(usuario=user).first()
        concurso = pref.get_concurso_display() if pref else 'seu concurso'

        prompt_templates = {
            'streak_risco': (
                f'Você é um coach de concurso publico. O usuario {user.first_name or user.username} '
                f'esta com uma streak de estudo mas nao respondeu questoes em ~20 horas. '
                f'Envie UMA mensagem CURTA (max 2 paragrafos) motivando a manter a streak. '
                f'Sem emojis exagerados. Tom: amigo que se importa. '
                f'Foque em: streak nao pode zerar hoje + questao rapida bastar. '
                f'Portugues brasileiro, direto.'
            ),
            'prova_proxima': (
                f'Coach de concurso. Faltam {pref.dias_para_prova} dias pra prova de {concurso}. '
                f'Envie UMA mensagem CURTA lembrando de intensificar. '
                f'Cite algo concreto: fazer 1 simulado essa semana, revisar top-3 disciplinas fracas. '
                f'Sem panico, foco em acao. Portugues brasileiro, direto.'
            ),
            'ausencia': (
                f'Coach de concurso. Usuario sumiu ha alguns dias. '
                f'Envie UMA mensagem CURTA de reengajamento sem culpa. '
                f'Reconheca que aconteceu (nao ignore), sugira retomar com algo pequeno '
                f'(3 questoes, 1 flashcard). Portugues brasileiro, empatico mas direto.'
            ),
        }

        prompt = prompt_templates.get(tipo, f'Coach: mensagem curta pra {user.username}. Contexto: {contexto}')

        if dry_run:
            self.stdout.write(f'  [DRY] {user.username} -> {tipo}')
            return True

        try:
            from quiz.ai_provider import gerar_conteudo, AIError
            texto = gerar_conteudo(prompt, max_tokens=400, temperature=0.7)
            if not texto or len(texto) < 30:
                return False

            _reconectar_db()
            MensagemCoachIA.objects.create(
                usuario=user, papel='assistant',
                conteudo=texto.strip(), origem='lembrete',
            )

            # Tambem cria notificacao
            from quiz.models import Notificacao
            Notificacao.objects.create(
                usuario=user, tipo='sistema',
                titulo='💬 Coach IA tem uma mensagem pra você',
                mensagem=texto[:150] + ('…' if len(texto) > 150 else ''),
                link='/coach/',
            )

            cache.set(cache_key, 1, 86400)  # dedup 24h
            self.stdout.write(self.style.SUCCESS(f'  ✓ {user.username} -> {tipo}'))
            return True
        except AIError as e:
            self.stdout.write(self.style.ERROR(f'  ✗ {user.username}: {e}'))
            return False
