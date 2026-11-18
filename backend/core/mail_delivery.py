"""Erreurs de transport contrôlées ; ne jamais journaliser le message SMTP."""
import logging

from django.core.mail import send_mail as django_send_mail
from rest_framework.exceptions import APIException

logger = logging.getLogger('qavelys.mail')


class MailDeliveryUnavailable(APIException):
    status_code = 503
    default_detail = 'Le service e-mail est temporairement indisponible. Réessayez plus tard.'
    default_code = 'mail_unavailable'


def send_mail(subject, message, from_email, recipient_list):
    try:
        sent = django_send_mail(subject, message, from_email, recipient_list, fail_silently=False)
        if sent != 1:
            raise OSError('No message accepted')
    except OSError:
        # SMTPException et erreurs TLS/socket dérivent de OSError. Aucun exc_info.
        logger.warning('mail_delivery_unavailable')
        raise MailDeliveryUnavailable() from None
    return sent
