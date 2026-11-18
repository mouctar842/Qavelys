import hashlib
from datetime import timedelta
from uuid import UUID
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_POST
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Company, EmailVerification, LoginAttempt, Membership, Role, User
from .serializers import CompanySerializer, MembershipSerializer, RoleSerializer
from .services import create_company, permissions_for, require_membership, suspend_member
from .verification import delivery_instructions, send_verification, verification_required
from .mail_delivery import MailDeliveryUnavailable


@require_GET
def csrf(request):
    return JsonResponse({'csrfToken': get_token(request)})


class Credentials(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=128, trim_whitespace=False)


class Registration(Credentials):
    full_name = serializers.CharField(max_length=150)


def parse_body(request, serializer_class):
    import json
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return None, JsonResponse({'detail': 'JSON invalide.'}, status=400)
    serializer = serializer_class(data=data)
    if not serializer.is_valid():
        return None, JsonResponse(serializer.errors, status=400)
    return serializer.validated_data, None


@require_POST
@csrf_protect
def register(request):
    data, error = parse_body(request, Registration)
    if error is not None:
        return error
    candidate = User(email=data['email'].lower(), full_name=data['full_name'])
    try:
        validate_password(data['password'], candidate)
    except DjangoValidationError as exc:
        return JsonResponse({'password': exc.messages}, status=400)
    created_user = None
    try:
        with transaction.atomic():
            user = User.objects.create_user(**data)
            # L'échec d’envoi annule l’inscription. Aucun jeton dans la réponse API.
            if verification_required():
                send_verification(user)
        created_user = user
    except IntegrityError:
        # Même réponse pour une adresse existante, pour limiter l’énumération.
        pass
    except MailDeliveryUnavailable as exc:
        return JsonResponse({'detail': str(exc.detail)}, status=exc.status_code)
    if not verification_required():
        if created_user is not None:
            login(request, created_user)
            return JsonResponse({'detail': 'Compte créé. Votre espace d’administration est prêt.', 'authenticated': True}, status=201)
        return JsonResponse({'detail': 'Si vous possédez déjà un compte avec cette adresse, utilisez le formulaire de connexion.', 'authenticated': False}, status=202)
    return JsonResponse({'detail': 'Si cette adresse peut être inscrite, un e-mail de vérification a été préparé. ' + delivery_instructions()}, status=202)


class Verification(serializers.Serializer):
    token = serializers.CharField(max_length=200)


@require_POST
@csrf_protect
def verify_email(request):
    data, error = parse_body(request, Verification)
    if error is not None:
        return error
    with transaction.atomic():
        verification = EmailVerification.objects.select_for_update().filter(token_hash=hashlib.sha256(data['token'].encode()).hexdigest(), used_at__isnull=True, expires_at__gt=timezone.now()).first()
        if verification is None:
            return JsonResponse({'detail': 'Lien invalide ou expiré.'}, status=400)
        User.objects.filter(pk=verification.user_id).update(email_verified=True)
        # La preuve de possession de l’adresse permet de repartir sans blocage antérieur.
        email = verification.user.email.strip().lower()
        LoginAttempt.objects.filter(key=hashlib.sha256(email.encode()).hexdigest()).update(failures=0, window_start=timezone.now())
        verification.used_at = timezone.now()
        verification.save(update_fields=['used_at'])
    return JsonResponse({'detail': 'Adresse vérifiée. Vous pouvez vous connecter.'})


@require_POST
@csrf_protect
def sign_in(request):
    data, error = parse_body(request, Credentials)
    if error is not None:
        return error
    email = data['email'].strip().lower()
    # Limite par compte persistée en base, commune aux workers.
    key = hashlib.sha256(email.encode()).hexdigest()
    with transaction.atomic():
        LoginAttempt.objects.get_or_create(key=key, defaults={'window_start': timezone.now()})
        attempt = LoginAttempt.objects.select_for_update().get(pk=key)
        if attempt.window_start < timezone.now() - timedelta(minutes=15):
            attempt.failures = 0
            attempt.window_start = timezone.now()
        if attempt.failures >= 5:
            return JsonResponse({'detail': 'Trop de tentatives. Réessayez dans 15 minutes.'}, status=429)
        user = authenticate(request, email=email, password=data['password'])
        if user is None:
            attempt.failures += 1
            attempt.save()
            return JsonResponse({'detail': 'Identifiants invalides.'}, status=400)
        if verification_required() and not user.email_verified:
            # Un mot de passe correct sans adresse vérifiée n’est pas un échec de mot de passe.
            return JsonResponse({'detail': 'Votre adresse e-mail doit être vérifiée avant la connexion. ' + delivery_instructions(), 'code': 'email_not_verified'}, status=403)
        attempt.failures = 0
        attempt.save()
    login(request, user)
    return JsonResponse({'id': str(user.id), 'full_name': user.full_name})


@require_POST
@csrf_protect
def sign_out(request):
    logout(request)
    return JsonResponse({'detail': 'Déconnexion effectuée.'})


class MeView(APIView):
    def get(self, request):
        return Response({'id': request.user.id, 'full_name': request.user.full_name, 'email': request.user.email, 'is_platform_admin': request.user.is_active and request.user.is_staff and request.user.is_superuser})
    def post(self, request):
        class Profile(serializers.Serializer):
            full_name = serializers.CharField(max_length=150)
        data = Profile(data=request.data)
        data.is_valid(raise_exception=True)
        request.user.full_name = data.validated_data['full_name']
        request.user.save(update_fields=['full_name'])
        return self.get(request)


class CompaniesView(APIView):
    def get(self, request):
        companies = Company.objects.filter(membership__user=request.user, membership__status='active', status='active').select_related('companysettings').order_by('name', 'id')
        return Response(CompanySerializer(companies, many=True).data)

    def post(self, request):
        if verification_required() and not request.user.email_verified:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Adresse e-mail non vérifiée.')
        try:
            key = UUID(request.headers.get('Idempotency-Key', ''))
        except ValueError:
            raise ValidationError({'Idempotency-Key': 'Une clé UUID est obligatoire.'})
        serializer = CompanySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company, created = create_company(request.user, key, serializer.validated_data)
        return Response(CompanySerializer(company).data, status=201 if created else 200)


class CompanyContextView(APIView):
    def get(self, request, company_id):
        membership = require_membership(request.user, company_id, 'company.view')
        from .models import CompanyModule
        modules = list(CompanyModule.objects.filter(company_id=company_id, enabled=True, module__status='available').values_list('module__code', flat=True))
        return Response({'company': CompanySerializer(membership.company).data, 'membership_id': membership.id, 'permissions': permissions_for(membership), 'modules': modules})


class MembersView(APIView):
    def get(self, request, company_id):
        require_membership(request.user, company_id, 'members.view')
        return Response(MembershipSerializer(Membership.objects.filter(company_id=company_id).select_related('user').prefetch_related('membershiprole_set__role').order_by('joined_at'), many=True).data)


class RolesView(APIView):
    def get(self, request, company_id):
        require_membership(request.user, company_id, 'roles.view')
        return Response(RoleSerializer(Role.objects.filter(company_id=company_id).prefetch_related('rolepermission_set').order_by('name'), many=True).data)


class SuspendMemberView(APIView):
    def post(self, request, company_id, member_id):
        require_membership(request.user, company_id, 'members.manage')
        return Response(MembershipSerializer(suspend_member(request.user, company_id, member_id)).data)
