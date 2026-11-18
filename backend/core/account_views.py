import hashlib
from datetime import timedelta
from django.conf import settings
from django.contrib.auth import authenticate, logout
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from .mail_delivery import MailDeliveryUnavailable, send_mail
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from rest_framework import serializers
from .models import AuthThrottle, LoginAttempt, User
from .verification import delivery_instructions, send_verification, verification_required
from .views import Credentials, parse_body


@transaction.atomic
def allowed(purpose, identity, limit=3, minutes=15):
    key = hashlib.sha256(f'{purpose}:{identity}'.encode()).hexdigest()
    AuthThrottle.objects.get_or_create(key=key, defaults={'window_start': timezone.now()})
    record = AuthThrottle.objects.select_for_update().get(pk=key)
    if record.window_start <= timezone.now() - timedelta(minutes=minutes):
        record.count, record.window_start = 0, timezone.now()
    if record.count >= limit:
        return False
    record.count += 1
    record.save()
    return True


class ResetRequest(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class ResetConfirm(serializers.Serializer):
    uid = serializers.CharField(max_length=100)
    token = serializers.CharField(max_length=200)
    password = serializers.CharField(max_length=128, trim_whitespace=False)


@require_POST
@csrf_protect
def password_reset(request):
    data, error = parse_body(request, ResetRequest)
    if error is not None:
        return error
    email = data['email'].strip().lower()
    if allowed('password-reset', email) and allowed('password-reset-ip', request.META.get('REMOTE_ADDR', ''), limit=30):
        user = User.objects.filter(email=email, is_active=True).first()
        if user and user.has_usable_password():
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            try:
                send_mail('Réinitialiser votre mot de passe Qavelys', f'Ouvrez ce lien pour choisir un nouveau mot de passe :\n{settings.FRONTEND_URL}/reset-password#uid={uid}&token={token}\n\nSi vous n’êtes pas à l’origine de cette demande, ignorez cet e-mail.', settings.DEFAULT_FROM_EMAIL, [user.email])
            except MailDeliveryUnavailable:
                # Même réponse pour un compte absent ou une panne : pas d’énumération.
                pass
    return JsonResponse({'detail': 'Si un compte actif correspond à cette adresse, un e-mail de réinitialisation a été préparé. ' + delivery_instructions()}, status=202)


@require_POST
@csrf_protect
def password_reset_confirm(request):
    data, error = parse_body(request, ResetConfirm)
    if error is not None:
        return error
    if not allowed('password-reset-confirm', data['uid'] + request.META.get('REMOTE_ADDR', ''), limit=10):
        return JsonResponse({'detail': 'Trop de tentatives. Réessayez plus tard.'}, status=429)
    try:
        uid = urlsafe_base64_decode(data['uid']).decode()
        with transaction.atomic():
            user = User.objects.select_for_update().filter(pk=uid, is_active=True).first()
            if user is None or not default_token_generator.check_token(user, data['token']):
                return JsonResponse({'detail': 'Lien invalide ou expiré.'}, status=400)
            try:
                validate_password(data['password'], user)
            except ValidationError as exc:
                return JsonResponse({'password': exc.messages}, status=400)
            user.set_password(data['password'])
            user.save(update_fields=['password'])
            LoginAttempt.objects.filter(key=hashlib.sha256(user.email.encode()).hexdigest()).update(failures=0, window_start=timezone.now())
    except (ValueError, UnicodeDecodeError, ValidationError):
        return JsonResponse({'detail': 'Lien invalide ou expiré.'}, status=400)
    logout(request)
    return JsonResponse({'detail': 'Mot de passe modifié. Connectez-vous avec votre nouveau mot de passe.'})


@require_POST
@csrf_protect
def resend_verification(request):
    data, error = parse_body(request, Credentials)
    if error is not None:
        return error
    if not verification_required():
        return JsonResponse({'detail': 'La vérification e-mail est désactivée en local. Connectez-vous directement.'}, status=202)
    email = data['email'].strip().lower()
    if allowed('resend-verification', email):
        user = authenticate(request, email=email, password=data['password'])
        if user and not user.email_verified:
            try:
                with transaction.atomic():
                    User.objects.select_for_update().get(pk=user.pk)
                    send_verification(user)
            except MailDeliveryUnavailable as exc:
                return JsonResponse({'detail': str(exc.detail)}, status=exc.status_code)
    return JsonResponse({'detail': 'Si les informations correspondent à un compte en attente, un nouvel e-mail a été préparé. ' + delivery_instructions()}, status=202)
