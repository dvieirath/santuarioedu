from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('quiz', '0019_sprint18_plano_dinamico'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='SessaoMicroEstudo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('total', models.PositiveSmallIntegerField(default=0)),
                ('acertos', models.PositiveSmallIntegerField(default=0)),
                ('xp_ganho', models.PositiveSmallIntegerField(default=0)),
                ('duracao_seg', models.PositiveSmallIntegerField(default=0)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                              related_name='micro_sessoes', to='auth.user')),
            ],
            options={'ordering': ['-criado_em']},
        ),
        migrations.CreateModel(
            name='PreferenciasNotificacao',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('lembrete_diario', models.BooleanField(default=True)),
                ('hora_lembrete', models.TimeField(default='20:00')),
                ('streak_em_risco', models.BooleanField(default=True)),
                ('novidades', models.BooleanField(default=True)),
                ('micro_estudo', models.BooleanField(default=True)),
                ('hora_pico', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('usuario', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                                                 related_name='pref_notif', to='auth.user')),
            ],
            options={'verbose_name': 'Preferências de Notificação'},
        ),
    ]
