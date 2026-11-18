from uuid import UUID
from django.core.management.base import BaseCommand
from core.models import Membership
from core.services import permissions_for
from core.notifications import sync


class Command(BaseCommand):
    help = 'Synchroniser les notifications personnelles actives, sans envoyer d’e-mail.'
    def add_arguments(self, parser): parser.add_argument('--company', type=UUID)
    def handle(self, *args, **options):
        members = Membership.objects.filter(status='active', company__status='active', user__is_active=True).select_related('user')
        if options['company']: members = members.filter(company_id=options['company'])
        created = 0
        for member in members.iterator():
            if 'notifications.view' in permissions_for(member): created += sync(member.user, member.company_id)
        self.stdout.write(f'{created} notification(s) créée(s).')
