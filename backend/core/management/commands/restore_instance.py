from django.core.management.base import BaseCommand
from core.recovery import restore


class Command(BaseCommand):
    help = 'Restaurer une sauvegarde locale vérifiée dans une nouvelle base et de nouveaux médias.'
    def add_arguments(self, parser):
        parser.add_argument('folder')
        parser.add_argument('--target')
    def handle(self, *args, **options):
        result = restore(options['folder'], options.get('target'))
        self.stdout.write(self.style.SUCCESS(f'Restauration vérifiée : {result["database"]} ; médias : {result["media_root"]}'))
