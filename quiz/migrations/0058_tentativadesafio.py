import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('quiz', '0057_alter_questao_texto_hash_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AddField(model_name='duelo', name='questao_iniciada_em',
                            field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='simuladocoletivo', name='questao_iniciada_em',
                            field=models.DateTimeField(blank=True, null=True)),
        migrations.CreateModel(
            name='TentativaDesafio',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('questoes_ids', models.JSONField(default=list)),
                ('respostas', models.JSONField(default=list)),
                ('segundos_por_questao', models.PositiveSmallIntegerField(default=30)),
                ('aberta_em', models.DateTimeField(blank=True, null=True)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('resultado', models.JSONField(blank=True, null=True)),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
