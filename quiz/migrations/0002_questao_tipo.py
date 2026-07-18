from django.db import migrations, models
class Migration(migrations.Migration):
    dependencies = [ ('quiz', '0001_initial'), ]
    operations = [ migrations.AddField( model_name='questao', name='tipo', field=models.CharField(choices=[('ME', 'Múltipla Escolha'), ('CE', 'Certo ou Errado')], default='ME', max_length=2), ), ]

