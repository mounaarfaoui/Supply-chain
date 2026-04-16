from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='OrderSubmission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('turn_number', models.IntegerField()),
                ('order_quantity', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('actor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='order_submissions', to='game.actor')),
                ('game', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='order_submissions', to='game.game')),
                ('submitted_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='order_submissions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['turn_number', 'actor__role'],
                'constraints': [models.UniqueConstraint(fields=('game', 'turn_number', 'actor'), name='unique_submission_per_actor_per_turn')],
            },
        ),
    ]
