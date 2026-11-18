from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from core.models import User
from core.verification import send_verification
from core.mail_delivery import MailDeliveryUnavailable


class Command(BaseCommand):
    help = 'Réémet un e-mail de vérification pour un compte non vérifié, sans activer le compte.'

    def add_arguments(self, parser):
        parser.add_argument('email')

    @transaction.atomic
    def handle(self, *args, **options):
        user = User.objects.select_for_update().filter(email__iexact=options['email'].strip()).first()
        if user is None:
            raise CommandError('Compte introuvable.')
        if not user.is_active or user.email_verified:
            raise CommandError('Le compte est inactif ou son adresse est déjà vérifiée.')
        try:
            send_verification(user)
        except MailDeliveryUnavailable as exc:
            raise CommandError(str(exc.detail)) from None
        self.stdout.write(self.style.SUCCESS('E-mail de vérification réémis via le transport configuré.'))
