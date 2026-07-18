from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('quiz', '0020_sprint19_micro_notif'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExplicacaoIA',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('texto', models.TextField()),
                ('util', models.BooleanField(blank=True, null=True)),
                ('rank_no_momento', models.CharField(default='Cadete', max_length=40)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                              related_name='explicacoes_ia', to='auth.user')),
                ('questao', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                              related_name='explicacoes_ia', to='quiz.questao')),
                ('alt_escolhida', models.ForeignKey(blank=True, null=True,
                                                    on_delete=django.db.models.deletion.SET_NULL,
                                                    related_name='explicacoes_escolhida',
                                                    to='quiz.alternativa')),
            ],
            options={'ordering': ['-criado_em']},
        ),
    ]
