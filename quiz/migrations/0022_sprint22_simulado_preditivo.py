from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('quiz', '0021_sprint20_explicacao_ia'),
    ]

    operations = [
        migrations.CreateModel(
            name='RelatorioSimuladoIA',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('texto', models.TextField()),
                ('nota_predita', models.FloatField(blank=True, null=True)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('simulado', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='relatorio_ia',
                    to='quiz.simulado',
                )),
            ],
            options={'ordering': ['-criado_em']},
        ),
    ]
