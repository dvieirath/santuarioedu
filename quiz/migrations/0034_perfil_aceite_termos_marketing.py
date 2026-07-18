from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('quiz', '0033_codigoindicacao_indicacao_usocupom'),
    ]

    operations = [
        migrations.AddField(
            model_name='perfil',
            name='aceite_termos',
            field=models.BooleanField(default=False,
                help_text='Usuário leu e aceitou explicitamente os Termos de Uso?'),
        ),
        migrations.AddField(
            model_name='perfil',
            name='aceite_termos_em',
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='perfil',
            name='aceite_termos_ip',
            field=models.GenericIPAddressField(null=True, blank=True,
                help_text='IP no momento do aceite — evidência judicial.'),
        ),
        migrations.AddField(
            model_name='perfil',
            name='aceita_marketing',
            field=models.BooleanField(default=False,
                help_text='Opt-in para receber e-mails de marketing/dicas (LGPD).'),
        ),
        migrations.AddField(
            model_name='perfil',
            name='aceita_marketing_em',
            field=models.DateTimeField(null=True, blank=True),
        ),
    ]
