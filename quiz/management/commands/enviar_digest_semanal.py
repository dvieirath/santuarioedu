"""
Envia o email de digest semanal para todos os usuários ativos.

Conteúdo: resumo de estudos da semana + meta da próxima.
Roda toda segunda-feira (configurar cron no Render/Railway).

Uso:
    python manage.py enviar_digest_semanal              # todos
    python manage.py enviar_digest_semanal --user joao  # só um
    python manage.py enviar_digest_semanal --dry_run    # não envia
"""
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.conf import settings

from quiz.models import RespostaUsuario, Simulado, MetaEstudo


User = get_user_model()


class Command(BaseCommand):
    help = 'Envia email digest semanal para usuários ativos'

    def add_arguments(self, parser):
        parser.add_argument('--user', type=str, default=None,
                            help='Username específico (default: todos)')
        parser.add_argument('--dry_run', action='store_true',
                            help='Mostra quem receberia sem enviar')

    def handle(self, *args, **opts):
        agora = timezone.now()
        sete = agora - timedelta(days=7)

        # Define quem recebe
        qs = User.objects.filter(is_active=True).exclude(email='')
        if opts['user']:
            qs = qs.filter(username=opts['user'])

        # Só usuários que tiveram alguma atividade nos últimos 14 dias
        qs = qs.filter(
            id__in=RespostaUsuario.objects.filter(
                data__gte=agora - timedelta(days=14)
            ).values('usuario').distinct()
        )

        total_enviados = 0
        for user in qs:
            stats = self._calcular_stats(user, sete, agora)
            assunto = self._montar_assunto(stats)
            corpo = self._montar_corpo(user, stats)

            self.stdout.write(f'  • {user.username} ({user.email})… ', ending='')
            if opts['dry_run']:
                self.stdout.write('[dry-run]')
                continue

            try:
                send_mail(
                    subject=assunto,
                    message=corpo['text'],
                    html_message=corpo['html'],
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
                total_enviados += 1
                self.stdout.write(self.style.SUCCESS('enviado'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'falhou: {e}'))

        self.stdout.write(
            self.style.SUCCESS(f'\n✓ {total_enviados} digests enviados')
        )

    def _calcular_stats(self, user, sete, agora):
        resps = RespostaUsuario.objects.filter(usuario=user, data__gte=sete)
        respondidas = resps.count()
        acertos = resps.filter(acertou=True).count()
        pct = round(acertos / respondidas * 100) if respondidas else 0

        sims = Simulado.objects.filter(
            usuario=user, finalizado=True, finalizado_em__gte=sete
        ).count()

        try:
            meta = user.metaestudo
            streak = meta.streak_atual
        except Exception:
            streak = 0

        return {
            'respondidas': respondidas,
            'acertos': acertos,
            'pct': pct,
            'simulados': sims,
            'streak': streak,
        }

    def _montar_assunto(self, s):
        if s['respondidas'] >= 50:
            return f'🔥 Você arrebentou a semana — {s["respondidas"]} questões!'
        if s['respondidas'] >= 20:
            return f'📈 Sua semana de estudos · {s["pct"]}% de acerto'
        if s['respondidas']:
            return f'💪 Bora retomar o ritmo · {s["respondidas"]} questões'
        return '😴 Que tal voltar a estudar?'

    def _montar_corpo(self, user, s):
        nome = user.first_name or user.username
        text = (
            f'Olá, {nome}!\n\n'
            f'Resumo dos seus últimos 7 dias no SantuarioEdu:\n\n'
            f'  • Questões respondidas: {s["respondidas"]}\n'
            f'  • Taxa de acerto: {s["pct"]}%\n'
            f'  • Simulados completados: {s["simulados"]}\n'
            f'  • Streak atual: {s["streak"]} dia(s)\n\n'
            f'Continue firme! Acesse: https://santuarioedu.com.br/dashboard/\n\n'
            f'Pra cancelar este email: https://santuarioedu.com.br/perfil/notificacoes/'
        )
        # HTML simples (poderia usar template, mas inline é mais robusto)
        html = f'''
        <div style="font-family: Inter, Arial, sans-serif; max-width: 560px; margin: 0 auto; padding: 24px; background: #f8f9fa; color: #191c1d;">
          <div style="background: #002046; color: #fff; padding: 20px 24px; border-radius: 16px 16px 0 0;">
            <div style="font-family: Manrope, sans-serif; font-weight: 800; font-size: 18px; letter-spacing: 0.15em; text-transform: uppercase;">SantuarioEdu</div>
          </div>
          <div style="background: #fff; padding: 32px 28px; border-radius: 0 0 16px 16px; box-shadow: 0 4px 20px rgba(0,0,0,.06);">
            <h1 style="font-family: Manrope, sans-serif; font-weight: 800; color: #002046; font-size: 24px; margin: 0 0 8px;">Olá, {nome}!</h1>
            <p style="color: #44474e; line-height: 1.6; margin: 0 0 24px;">
              Aqui está o seu resumo dos últimos <strong>7 dias</strong>:
            </p>
            <table style="width: 100%; border-collapse: collapse;">
              <tr>
                <td style="padding: 14px; background: #f3f4f5; border-radius: 12px;">
                  <div style="color: #44474e; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;">Questões</div>
                  <div style="font-family: Manrope; font-weight: 800; color: #002046; font-size: 28px;">{s["respondidas"]}</div>
                </td>
                <td style="width: 14px;"></td>
                <td style="padding: 14px; background: #f3f4f5; border-radius: 12px;">
                  <div style="color: #44474e; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;">Acerto</div>
                  <div style="font-family: Manrope; font-weight: 800; color: #006c4d; font-size: 28px;">{s["pct"]}%</div>
                </td>
              </tr>
              <tr><td colspan="3" style="height: 12px;"></td></tr>
              <tr>
                <td style="padding: 14px; background: #f3f4f5; border-radius: 12px;">
                  <div style="color: #44474e; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;">Simulados</div>
                  <div style="font-family: Manrope; font-weight: 800; color: #002046; font-size: 28px;">{s["simulados"]}</div>
                </td>
                <td style="width: 14px;"></td>
                <td style="padding: 14px; background: #fef3c7; border-radius: 12px;">
                  <div style="color: #92400e; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;">🔥 Streak</div>
                  <div style="font-family: Manrope; font-weight: 800; color: #92400e; font-size: 28px;">{s["streak"]} dias</div>
                </td>
              </tr>
            </table>
            <div style="margin-top: 24px; text-align: center;">
              <a href="https://santuarioedu.com.br/dashboard/" style="display: inline-block; background: #002046; color: #fff; text-decoration: none; padding: 12px 28px; border-radius: 999px; font-weight: 700; font-size: 13px;">Voltar a estudar →</a>
            </div>
          </div>
          <p style="color: #74777f; font-size: 11px; text-align: center; margin: 20px 0 0;">
            Cancele este email em <a href="https://santuarioedu.com.br/perfil/notificacoes/" style="color: #006c4d;">/perfil/notificacoes/</a>
          </p>
        </div>
        '''
        return {'text': text, 'html': html}
