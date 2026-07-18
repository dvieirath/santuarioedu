from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('quiz', '0034_perfil_aceite_termos_marketing'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ─── Sistema de Suporte ───────────────────────────────────────
        migrations.CreateModel(
            name='TicketSuporte',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False, auto_created=True)),
                ('categoria', models.CharField(max_length=20, default='duvida', choices=[
                    ('bug', '🐛 Bug ou erro técnico'),
                    ('duvida', '❓ Dúvida sobre a plataforma'),
                    ('questao', '📝 Erro em questão/gabarito'),
                    ('pagamento', '💳 Pagamento ou plano'),
                    ('sugestao', '💡 Sugestão de melhoria'),
                    ('outro', 'Outro assunto'),
                ])),
                ('assunto', models.CharField(max_length=200)),
                ('mensagem', models.TextField()),
                ('email_contato', models.EmailField(blank=True, max_length=254)),
                ('url_origem', models.URLField(blank=True, default='')),
                ('status', models.CharField(max_length=15, default='aberto', choices=[
                    ('aberto', 'Aberto'),
                    ('respondido', 'Respondido pelo suporte'),
                    ('aguardando', 'Aguardando usuário'),
                    ('fechado', 'Fechado'),
                ])),
                ('prioridade', models.CharField(max_length=10, default='media', choices=[
                    ('baixa', 'Baixa'),
                    ('media', 'Média'),
                    ('alta', 'Alta'),
                    ('urgente', 'Urgente'),
                ])),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('fechado_em', models.DateTimeField(blank=True, null=True)),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='tickets', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Ticket de Suporte',
                'verbose_name_plural': 'Tickets de Suporte',
                'ordering': ['-criado_em'],
            },
        ),
        migrations.CreateModel(
            name='RespostaTicket',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False, auto_created=True)),
                ('mensagem', models.TextField()),
                ('eh_staff', models.BooleanField(default=False)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('autor', models.ForeignKey(null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to=settings.AUTH_USER_MODEL)),
                ('ticket', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='respostas', to='quiz.ticketsuporte')),
            ],
            options={'ordering': ['criado_em']},
        ),

        # ─── Marcar questão pra revisar depois ────────────────────────
        migrations.CreateModel(
            name='QuestaoMarcada',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False, auto_created=True)),
                ('motivo', models.CharField(blank=True, default='', max_length=120)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('questao', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    to='quiz.questao')),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='marcadas', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-criado_em'],
                'unique_together': {('usuario', 'questao')},
            },
        ),

        # ─── Concurso preferido (onboarding) ──────────────────────────
        migrations.CreateModel(
            name='ConcursoPreferido',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False, auto_created=True)),
                ('concurso', models.CharField(max_length=20, choices=[
                    ('prf', 'PRF — Polícia Rodoviária Federal'),
                    ('pf', 'PF — Polícia Federal'),
                    ('inss', 'INSS — Técnico do Seguro Social'),
                    ('enem', 'ENEM'),
                    ('tjdf', 'TJ-DF — Tribunal de Justiça'),
                    ('trf', 'TRF — Tribunais Regionais'),
                    ('camara', 'Câmara/Senado'),
                    ('estadual', 'Concurso Estadual'),
                    ('municipal', 'Concurso Municipal'),
                    ('outro', 'Outro'),
                ])),
                ('data_prova_esperada', models.DateField(blank=True, null=True)),
                ('horas_por_dia', models.PositiveSmallIntegerField(default=2)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('usuario', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                    related_name='concurso_pref', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
