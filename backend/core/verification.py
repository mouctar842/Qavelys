import hashlib
import secrets
from datetime import timedelta
from django.conf import settings
from .mail_delivery import send_mail
from django.utils import timezone
from .models import EmailVerification


def verification_required():
    return not settings.DEBUG or settings.REQUIRE_EMAIL_VERIFICATION


def delivery_instructions():
    if settings.DEBUG and settings.EMAIL_BACKEND == 'django.core.mail.backends.filebased.EmailBackend':
        return 'En développement local, ouvrez le dernier e-mail dans le dossier .local/emails du projet, puis son lien de vérification. Aucun e-mail n’est envoyé dans votre boîte personnelle.'
    if settings.DEBUG and settings.EMAIL_BACKEND == 'django.core.mail.backends.console.EmailBackend':
        return 'En développement local, le lien de vérification est affiché dans la console du serveur Django. Aucun e-mail n’est envoyé dans votre boîte personnelle.'
    return 'Consultez votre boîte e-mail et vos courriers indésirables, puis ouvrez le lien de vérification.'


def send_verification(user):
    """À appeler dans une transaction ; jeton jamais renvoyé par l’API."""
    token = secrets.token_urlsafe(32)
    EmailVerification.objects.create(user=user, token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=timezone.now() + timedelta(hours=24))
    send_mail('Vérifiez votre adresse Qavelys', f'Pour activer votre compte, ouvrez ce lien puis cliquez sur « Vérifier mon adresse » :\n\n{settings.FRONTEND_URL}/verify-email#token={token}\n\nCe lien est valable 24 heures et ne peut être utilisé qu’une fois.', settings.DEFAULT_FROM_EMAIL, [user.email])
