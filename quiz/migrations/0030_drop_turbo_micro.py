from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('quiz', '0029_logsistema'),
    ]

    operations = [
        migrations.DeleteModel(name='SessaoTurbo'),
        migrations.DeleteModel(name='SessaoMicroEstudo'),
        migrations.RemoveField(
            model_name='preferenciasnotificacao',
            name='micro_estudo',
        ),
    ]
