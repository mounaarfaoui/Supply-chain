from django.db import migrations, models


def populate_room_codes(apps, schema_editor):
    Game = apps.get_model("game", "Game")

    for game in Game.objects.all():
        if game.room_code:
            continue
        code = f"G{game.id:06d}"
        game.room_code = code
        game.save(update_fields=["room_code"])


class Migration(migrations.Migration):

    dependencies = [
        ("game", "0003_actor_role_client"),
    ]

    operations = [
        migrations.AddField(
            model_name="game",
            name="room_code",
            field=models.CharField(blank=True, max_length=12, null=True, unique=True),
        ),
        migrations.RunPython(populate_room_codes, migrations.RunPython.noop),
    ]