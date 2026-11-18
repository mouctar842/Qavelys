from django.core.management.base import BaseCommand, CommandError
from core.health import ready


class Command(BaseCommand):
    help = 'Vérifier PostgreSQL et les migrations sans exposer de donnée métier.'
    requires_system_checks = []

    def handle(self, *args, **options):
        if not ready():
            raise CommandError('Application indisponible.', returncode=1)
        self.stdout.write('Application prête.')
