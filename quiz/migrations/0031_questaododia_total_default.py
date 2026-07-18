from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('quiz', '0030_drop_turbo_micro'),
    ]

    operations = [
        migrations.AlterField(
            model_name='questaododia',
            name='total',
            field=models.PositiveSmallIntegerField(default=1),
        ),
    ]
