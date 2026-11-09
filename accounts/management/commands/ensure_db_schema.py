"""
Create the PostgreSQL schema named in DB_SCHEMA if it does not exist yet.

settings.DATABASES pins every connection to `search_path=<DB_SCHEMA>`. On a fresh
database (e.g. a new Docker volume) only `public` exists, so `migrate` fails with
"no schema has been selected to create in". Run this before `migrate`.
"""
import re

from decouple import config
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


class Command(BaseCommand):
    help = "Create the DB_SCHEMA schema in PostgreSQL if it is missing."

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            self.stdout.write("Not PostgreSQL; nothing to do.")
            return

        schema = config("DB_SCHEMA", default="public").strip()
        if not IDENTIFIER.match(schema):
            raise CommandError(
                f"DB_SCHEMA={schema!r} is not a valid schema name "
                "(letters, digits and underscores, not starting with a digit)."
            )

        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_namespace WHERE nspname = %s", [schema])
            if cursor.fetchone():
                self.stdout.write(f"Schema '{schema}' already exists.")
                return
            # Identifier validated above; schema names cannot be passed as query parameters.
            cursor.execute(f'CREATE SCHEMA "{schema}"')
        self.stdout.write(self.style.SUCCESS(f"Created schema '{schema}'."))
