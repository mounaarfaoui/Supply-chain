from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0002_ordersubmission'),
    ]

    operations = [
        migrations.AlterField(
            model_name='actor',
            name='role',
            field=models.CharField(
                choices=[
                    ('client', 'Client'),
                    ('detaillant', 'Retailer'),
                    ('distributeur', 'Distributor'),
                    ('grossiste', 'Wholesaler'),
                    ('usine', 'Factory'),
                ],
                max_length=20,
            ),
        ),
    ]
