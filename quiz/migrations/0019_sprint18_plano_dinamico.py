from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('quiz', '0018_sprint16_nivel_turbo'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='PlanoEstudoDinamico',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('concurso_alvo', models.CharField(default='PRF', max_length=120)),
                ('data_prova', models.DateField(blank=True, null=True)),
                ('horas_por_dia', models.PositiveSmallIntegerField(default=2)),
                ('dias_por_semana', models.PositiveSmallIntegerField(default=5)),
                ('distribuicao', models.JSONField(default=dict)),
                ('distribuicao_ant', models.JSONField(default=dict)),
                ('data_recalculo', models.DateTimeField(blank=True, null=True)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('usuario', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='plano_dinamico',
                    to='auth.user',
                )),
            ],
            options={
                'verbose_name': 'Plano de Estudos Dinâmico',
            },
        ),
    ]
