from django.core.management.base import BaseCommand
from core.recovery import backup


class Command(BaseCommand):
    help = 'Sauvegarder PostgreSQL et les médias dans un nouveau dossier privé local.'
    def handle(self, *args, **options):
        folder = backup()
        self.stdout.write(self.style.SUCCESS(f'Sauvegarde vérifiée : {folder}'))
