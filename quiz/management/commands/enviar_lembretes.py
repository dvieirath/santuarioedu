"""
Enviar lembretes de estudo por e-mail.

Uso:
  python manage.py enviar_lembretes --tipo diario
  python manage.py enviar_lembretes --tipo semanal
  python manage.py enviar_lembretes --tipo srs
  python manage.py enviar_lembretes --tipo boas_vindas_d1

Agendar via cron (exemplo Railway/cron):
  # Diario as 11h UTC (8h Brasilia)
  0 11 * * * python manage.py enviar_lembretes --tipo diario

  # Novos usuarios inativos 24-48h apos confirmar email — mesmo horario
  30 11 * * * python manage.py enviar_lembretes --tipo boas_vindas_d1

  # Semanal toda segunda 10h UTC
  0 10 * * 1 python manage.py enviar_lembretes --tipo semanal
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone
from datetime import timedelta


class Command(BaseCommand):
    help = 'Envia lembretes de estudo por e-mail aos usuários.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tipo',
            choices=['diario', 'semanal', 'srs', 'boas_vindas_d1', 'trial_expira_d2', 'reengajamento_d3'],
            default='diario',
            help='Tipo de lembrete: diario | semanal | srs | boas_vindas_d1 | '
                 'trial_expira_d2 | reengajamento_d3',
        )
        parser.add_argument(
            '--usuario',
            type=str,
            default=None,
            help='Enviar apenas para este username (para testes)',
        )

    def handle(self, *args, **options):
        from quiz.models import RespostaUsuario, MetaEstudo, RevisaoEspacada, Conquista

        tipo     = options['tipo']
        username = options.get('usuario')
        agora    = timezone.now()
        hoje     = agora.date()

        usuarios = User.objects.filter(is_active=True, email__isnull=False).exclude(email='')
        if username:
            usuarios = usuarios.filter(username=username)

        enviados = 0
        erros    = 0

        for user in usuarios:
            try:
                ctx = self._build_context(user, tipo, agora, hoje)
                if ctx is None:
                    continue  # sem motivo para enviar

                assunto  = ctx.pop('assunto')
                corpo_txt= ctx.pop('corpo_txt')

                send_mail(
                    subject      = assunto,
                    message      = corpo_txt,
                    from_email   = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@santuarioedu.com.br'),
                    recipient_list=[user.email],
                    fail_silently= False,
                )
                enviados += 1
                self.stdout.write(self.style.SUCCESS(f'  ✓ {user.email}'))

            except Exception as e:
                erros += 1
                self.stderr.write(f'  ✗ {user.email}: {e}')

        self.stdout.write(self.style.SUCCESS(
            f'\nConcluído: {enviados} enviados, {erros} erros.'
        ))

    def _build_context(self, user, tipo, agora, hoje):
        from quiz.models import RespostaUsuario, MetaEstudo, RevisaoEspacada

        nome = user.first_name or user.username
        site_url = getattr(settings, 'SITE_URL', 'https://santuarioedu.com.br').rstrip('/')

        if tipo == 'srs':
            pendentes = RevisaoEspacada.objects.filter(
                usuario=user,
                proxima_revisao__date__lte=hoje,
            ).count()
            if pendentes == 0:
                return None
            assunto = f'🧠 Você tem {pendentes} revisão(ões) SRS pendente(s) — SantuarioEdu'
            corpo   = (
                f'Olá, {nome}!\n\n'
                f'Você tem {pendentes} questão(ões) aguardando revisão no sistema de repetição espaçada (SRS).\n\n'
                f'Revise agora para não perder seu progresso de memorização:\n'
                f'👉 {site_url}/revisao-srs/\n\n'
                f'-- SantuarioEdu\n'
            )

        elif tipo == 'diario':
            # Só envia se o usuário não respondeu nenhuma questão hoje
            respondeu_hoje = RespostaUsuario.objects.filter(
                usuario=user, data__date=hoje).exists()
            if respondeu_hoje:
                return None

            # Precisa ter respondido algo antes — quem nunca respondeu vai pro
            # tipo boas_vindas_d1 (evita duplicidade de mensagem confusa)
            if not RespostaUsuario.objects.filter(usuario=user).exists():
                return None

            try:
                meta = user.metaestudo
                streak = meta.streak_atual
            except Exception:
                streak = 0

            assunto = f'📚 Hora de estudar, {nome}!'
            corpo   = (
                f'Olá, {nome}!\n\n'
                f'Você ainda não respondeu nenhuma questão hoje. '
                f'{"Não perca sua sequência de " + str(streak) + " dias!" if streak > 1 else "Comece seu dia estudando!"}\n\n'
                f'🎯 Meta diária: responder questões e manter seu progresso.\n\n'
                f'Acesse agora:\n'
                f'👉 {site_url}/estudar/\n\n'
                f'-- SantuarioEdu\n'
            )

        elif tipo == 'boas_vindas_d1':
            # Novo usuario: confirmou email nas ultimas 24-48h E ainda nao respondeu nada.
            # Objetivo: reengajar antes do usuario esquecer que se cadastrou.
            try:
                from allauth.account.models import EmailAddress
            except ImportError:
                return None

            email_addr = EmailAddress.objects.filter(
                user=user, verified=True, email=user.email,
            ).first()
            if not email_addr:
                return None

            # Janela: user.date_joined entre 24h e 48h atras + zero respostas.
            # date_joined eh proxy robusto — email confirmation timestamp exigiria
            # query em EmailConfirmation, mais pesado sem ganho pratico.
            delta = agora - user.date_joined
            if not (timedelta(hours=24) <= delta <= timedelta(hours=48)):
                return None

            if RespostaUsuario.objects.filter(usuario=user).exists():
                return None

            assunto = f'👋 Ainda por aí, {nome}? Sua conta te espera'
            corpo   = (
                f'Olá, {nome}!\n\n'
                f'Você criou sua conta no SantuarioEdu ontem mas ainda não respondeu\n'
                f'nenhuma questão. Que tal começar agora?\n\n'
                f'🎁 Lembre-se: seu trial PRO de 7 dias está ativo. Cada dia que\n'
                f'passa sem estudar é 1 dia a menos de recursos ilimitados.\n\n'
                f'⚡ Sugestão pra começar (leva 5min):\n'
                f'1. Escolha sua disciplina favorita\n'
                f'2. Responda 5 questões\n'
                f'3. Veja a IA analisar seus acertos e erros\n\n'
                f'👉 Comece agora: {site_url}/estudar/\n\n'
                f'Alguma dúvida? Só responder este email.\n\n'
                f'-- SantuarioEdu\n'
            )

        elif tipo == 'trial_expira_d2':
            # Removido — app 100% gratuita, sem trial.
            return None

        elif tipo == 'semanal':
            inicio = hoje - timedelta(days=hoje.weekday())  # segunda-feira desta semana
            fim    = inicio - timedelta(days=1)             # domingo passado
            ini_anterior = fim - timedelta(days=6)          # segunda anterior

            respostas = RespostaUsuario.objects.filter(
                usuario=user,
                data__date__gte=ini_anterior,
                data__date__lte=fim,
            )
            total   = respostas.count()
            acertos = respostas.filter(acertou=True).count()
            pct     = round(acertos / total * 100) if total else 0

            # Nao manda pra quem nao teve atividade — email tipo "0 acertos de 0" eh triste
            if total == 0:
                return None

            # Achievements da semana
            from quiz.models import Conquista, NivelUsuario
            conquistas_semana = list(Conquista.objects.filter(
                usuario=user,
                desbloqueado_em__date__gte=ini_anterior,
                desbloqueado_em__date__lte=fim,
            ).values_list('codigo', flat=True))

            # Streak atual
            try:
                streak = user.meta.streak_atual
            except Exception:
                streak = 0

            # Nivel/rank atual
            try:
                nivel = user.nivelusuario
                rank_str = f'{nivel.rank_nome} · Nível {nivel.nivel}'
                xp_str = f' · {nivel.xp_total} XP'
            except Exception:
                rank_str = ''
                xp_str = ''

            # Conquistas em texto legivel
            from quiz.views import CONQUISTAS_META
            achievements_txt = ''
            if conquistas_semana:
                labels = []
                for c in conquistas_semana[:3]:
                    meta_c = CONQUISTAS_META.get(c, {})
                    labels.append(f'{meta_c.get("emoji","🏆")} {meta_c.get("label", c)}')
                achievements_txt = '\n🏆 Conquistas desbloqueadas essa semana:\n' + '\n'.join(f'   {l}' for l in labels) + '\n'
                if len(conquistas_semana) > 3:
                    achievements_txt += f'   ... e mais {len(conquistas_semana) - 3} conquista(s)!\n'

            assunto = f'📊 Seu resumo semanal — {acertos}/{total} ({pct}%)'
            corpo   = (
                f'Olá, {nome}! Confira seu desempenho da última semana '
                f'({ini_anterior.strftime("%d/%m")} a {fim.strftime("%d/%m/%Y")}):\n\n'
                f'  📝 Questões respondidas: {total}\n'
                f'  ✅ Acertos: {acertos}\n'
                f'  📈 Aproveitamento: {pct}%\n'
                f'  🔥 Streak atual: {streak} dia{"s" if streak != 1 else ""}\n'
                f'{("  🎖️  " + rank_str + xp_str + chr(10)) if rank_str else ""}'
                f'{achievements_txt}'
                f'\n{"🏆 Semana excelente! Continue assim!" if pct >= 70 else "📚 Bora subir esse aproveitamento na proxima!"}\n\n'
                f'Ver relatório completo:\n'
                f'👉 {site_url}/relatorio-semanal/\n\n'
                f'-- SantuarioEdu\n'
            )

        elif tipo == 'reengajamento_d3':
            # User sumido 3-14 dias: tem historico mas parou de estudar.
            # Combate churn medio prazo. Nao envia:
            # - se nunca respondeu (vai pro boas_vindas_d1)
            # - se ativo nos ultimos 3 dias
            # - se sumiu ha mais de 14 dias (churn consumado, nao vale insistir)
            ultima = RespostaUsuario.objects.filter(
                usuario=user,
            ).order_by('-data').first()

            if not ultima:
                return None  # sem historico -> boas_vindas_d1

            dias_sumido = (agora - ultima.data).days
            if dias_sumido < 3 or dias_sumido > 14:
                return None

            # Aproveitamento historico pra usar copy motivacional
            respostas = RespostaUsuario.objects.filter(usuario=user)
            total = respostas.count()
            acertos = respostas.filter(acertou=True).count()
            pct = round(acertos / total * 100) if total else 0

            try:
                streak = user.meta.streak_atual
            except Exception:
                streak = 0

            # Copy adaptativo — mais forte quando tinha streak/aproveitamento alto
            if streak >= 3 and pct >= 60:
                copy_hook = (
                    f'Voce estava indo BEM — {streak} dias de streak e {pct}% de acerto.\n'
                    f'Nao vale a pena perder esse ritmo agora.'
                )
            elif pct >= 60:
                copy_hook = (
                    f'Voce tem historico bom aqui — {pct}% de acerto em {total} questoes.\n'
                    f'Vai perder tudo?'
                )
            else:
                copy_hook = (
                    f'Voltar pra estudar depois de uma pausa e o passo mais dificil.\n'
                    f'Mas voce ta a 5 minutos de recomecar.'
                )

            assunto = f'👋 Faltam {dias_sumido} dias — bora voltar?'
            corpo   = (
                f'Ola, {nome}!\n\n'
                f'Voce nao aparece por aqui ha {dias_sumido} dias.\n\n'
                f'{copy_hook}\n\n'
                f'⚡ Ideia: comeca com 5 questoes rapidas pra pegar o ritmo de novo:\n'
                f'👉 {site_url}/estudar/\n\n'
                f'Se voce ja nao ta mais estudando pra concurso, tudo bem — sem\n'
                f'ressentimento. Da pra pausar sem deletar a conta (seu progresso\n'
                f'fica salvo caso queira voltar).\n\n'
                f'-- SantuarioEdu\n'
            )
        else:
            return None

        return {'assunto': assunto, 'corpo_txt': corpo}
