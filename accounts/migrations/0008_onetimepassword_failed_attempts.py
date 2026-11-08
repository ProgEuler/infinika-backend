from django.core.management import call_command
from django.db import migrations, models


def create_cache_table(apps, schema_editor):
    # settings.CACHES uses DatabaseCache (shared across gunicorn workers, needed
    # for auth throttling and the forgot-password verified flag). Creating the
    # table here guarantees it exists wherever `migrate` has run.
    call_command("createcachetable", database=schema_editor.connection.alias, verbosity=0)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_user_is_push_notification"),
    ]

    operations = [
        migrations.AddField(
            model_name="onetimepassword",
            name="failed_attempts",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.RunPython(create_cache_table, migrations.RunPython.noop),
    ]
