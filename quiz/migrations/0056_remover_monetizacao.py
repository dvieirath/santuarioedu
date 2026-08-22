# Generated manually — remove models de monetizacao (app 100% gratuita)

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('quiz', '0055_blog'),
    ]

    operations = [
        # Ordem importante: primeiro remove FKs, depois deleta models.
        # UsoCupom depende de CupomDesconto — deletar UsoCupom primeiro.
        migrations.AlterUniqueTogether(
            name='usocupom',
            unique_together=set(),
        ),
        migrations.DeleteModel(
            name='UsoCupom',
        ),
        migrations.DeleteModel(
            name='CupomDesconto',
        ),
        migrations.DeleteModel(
            name='PagamentoMP',
        ),
        migrations.DeleteModel(
            name='PlanoUsuario',
        ),
    ]
