from django.core.management import call_command
from django.db import migrations


def create_cache_table(apps, schema_editor):
    # The database cache holds the login throttling counters. Creating its table in a migration means every
    # environment, including the test database, has it without an extra manual step.
    call_command("createcachetable", database=schema_editor.connection.alias)


class Migration(migrations.Migration):
    dependencies = []

    operations = [migrations.RunPython(create_cache_table, migrations.RunPython.noop)]
