from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from core.models import PlatformAuditLog, User
from core.platform_services import lock_platform
from core.verification import verification_required


class Command(BaseCommand):
    help = 'Attribuer le rôle plateforme à un compte existant explicitement désigné, sans modifier son e-mail ni son mot de passe.'

    def add_arguments(self, parser):
        parser.add_argument('email')

    @transaction.atomic
    def handle(self, *args, **options):
        lock_platform()
        target = User.objects.select_for_update().filter(email__iexact=options['email'].strip()).first()
        if not target or not target.is_active:
            raise CommandError('Compte actif introuvable. Créez votre compte depuis l’inscription.')
        if verification_required() and not target.email_verified:
            raise CommandError('Ce compte doit d’abord vérifier son adresse e-mail.')
        if target.is_staff and target.is_superuser:
            self.stdout.write('Ce compte possède déjà le rôle plateforme.')
            return
        before = {'is_staff': target.is_staff, 'is_superuser': target.is_superuser}
        target.is_staff = target.is_superuser = True
        target.save(update_fields=['is_staff', 'is_superuser'])
        PlatformAuditLog.objects.create(actor=None, source='management', target_user=target, action='user.platform_access_granted',
            reason='Attribution explicite par commande opérateur.', before_data=before, after_data={'is_staff': True, 'is_superuser': True})
        self.stdout.write(self.style.SUCCESS('Rôle plateforme attribué au compte désigné.'))
