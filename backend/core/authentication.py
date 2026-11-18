from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied
from .verification import verification_required


class VerifiedSessionAuthentication(SessionAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result and verification_required() and not result[0].email_verified:
            raise PermissionDenied('Votre adresse e-mail doit être vérifiée.')
        return result
