from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('quiz', '0028_alternativa_texto_textfield'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='LogSistema',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nivel', models.CharField(
                    choices=[('INFO', 'Informação'), ('AVISO', 'Aviso'), ('ERRO', 'Erro'), ('CRITICO', 'Crítico')],
                    default='INFO', max_length=10)),
                ('origem', models.CharField(blank=True, default='sistema',
                                            help_text='Ex: importação, questão, auth, api', max_length=120)),
                ('mensagem', models.TextField()),
                ('detalhe', models.TextField(blank=True,
                                             help_text='Traceback, JSON de contexto, etc.')),
                ('usuario', models.ForeignKey(blank=True, null=True,
                                              on_delete=django.db.models.deletion.SET_NULL,
                                              related_name='logs_sistema',
                                              to=settings.AUTH_USER_MODEL)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Log do Sistema',
                'verbose_name_plural': 'Logs do Sistema',
                'ordering': ['-criado_em'],
            },
        ),
    ]
