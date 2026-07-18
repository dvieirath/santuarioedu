from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('quiz', '0022_sprint22_simulado_preditivo'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # gerada_por_ia flag on Questao
        migrations.AddField(
            model_name='questao',
            name='gerada_por_ia',
            field=models.BooleanField(default=False),
        ),
        # PrevisaoTopico model
        migrations.CreateModel(
            name='PrevisaoTopico',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('probabilidade', models.FloatField(default=0.0)),
                ('justificativa', models.TextField(blank=True)),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('usuario', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='previsoes_topico',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('categoria', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='previsoes',
                    to='quiz.categoria',
                )),
            ],
            options={
                'ordering': ['-probabilidade'],
                'unique_together': {('usuario', 'categoria')},
            },
        ),
    ]
