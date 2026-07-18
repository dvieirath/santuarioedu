from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('quiz', '0023_sprint23_geracao_ia_topicos'),
    ]

    operations = [
        migrations.AddField(
            model_name='simulado',
            name='modo',
            field=models.CharField(
                choices=[('normal', 'Normal'), ('prova_real', 'Prova Real')],
                default='normal',
                max_length=20,
            ),
        ),
    ]
