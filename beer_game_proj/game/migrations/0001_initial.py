# Generated migration for initial models

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        # Create Game model
        migrations.CreateModel(
            name='Game',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('active', 'Active'), ('ended', 'Ended')], default='active', max_length=10)),
                ('current_turn', models.IntegerField(default=0)),
                ('total_turns', models.IntegerField(default=52)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        # Create Actor model
        migrations.CreateModel(
            name='Actor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('detaillant', 'Retailer'), ('distributeur', 'Distributor'), ('grossiste', 'Wholesaler'), ('usine', 'Factory')], max_length=20)),
                ('stock', models.IntegerField(default=15)),
                ('backlog', models.IntegerField(default=0)),
                ('total_cost', models.FloatField(default=0)),
                ('incoming_step_1', models.IntegerField(default=0)),
                ('incoming_step_2', models.IntegerField(default=0)),
                ('last_order', models.IntegerField(default=5)),
                ('game', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='actors', to='game.game')),
            ],
        ),
        # Create Turn model
        migrations.CreateModel(
            name='Turn',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('turn_number', models.IntegerField()),
                ('customer_demand', models.IntegerField(default=5)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('game', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='turns', to='game.game')),
            ],
            options={
                'ordering': ['turn_number'],
            },
        ),
        # Create ActorAction model
        migrations.CreateModel(
            name='ActorAction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order_quantity', models.IntegerField(default=0)),
                ('shipped_quantity', models.IntegerField(default=0)),
                ('stock_before', models.IntegerField(default=0)),
                ('stock_after', models.IntegerField(default=0)),
                ('backlog_before', models.IntegerField(default=0)),
                ('backlog_after', models.IntegerField(default=0)),
                ('cost_incurred', models.FloatField(default=0)),
                ('actor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='game.actor')),
                ('turn', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='actions', to='game.turn')),
            ],
        ),
    ]
