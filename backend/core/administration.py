import hashlib
import json
import secrets
from datetime import timedelta
from django.conf import settings
from .mail_delivery import send_mail
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from .models import (AuditLog, Company, CompanyInvitation, CompanyModule, DocumentSequence,
                     InvitationRole, Membership, MembershipRole, Module, Permission, Role, RolePermission)
from .services import require_membership


def audit(company, actor, action, entity, before=None, after=None):
    clean = lambda data: json.loads(json.dumps(data or {}, cls=DjangoJSONEncoder))
    AuditLog.objects.create(company=company, actor=actor, action=action, entity_type=type(entity).__name__, entity_id=entity.pk, before_data=clean(before), after_data=clean(after))


def locked_company(actor, company_id, permission):
    company = Company.objects.select_for_update().filter(pk=company_id).first()
    if company is None:
        raise PermissionDenied('Entreprise inaccessible.')
    require_membership(actor, company_id, permission)
    return company


def check_admin(company):
    if not Membership.objects.filter(company=company, status='active', user__is_active=True, membershiprole__role__company=company, membershiprole__role__is_system=True, membershiprole__role__name='Administrateur').exists():
        raise ValidationError('L’entreprise doit conserver au moins un administrateur actif.')


def same_company_roles(company, ids):
    if not ids:
        raise ValidationError({'role_ids': 'Sélectionnez au moins un rôle.'})
    roles = list(Role.objects.filter(company=company, id__in=ids))
    if len(roles) != len(set(ids)):
        raise ValidationError({'role_ids': 'Un rôle est inconnu ou appartient à une autre entreprise.'})
    return roles


@transaction.atomic
def save_role(actor, company_id, data, role_id=None):
    company = locked_company(actor, company_id, 'roles.manage')
    permission_codes = data['permission_codes']
    if Permission.objects.filter(code__in=permission_codes).count() != len(set(permission_codes)):
        raise ValidationError({'permission_codes': 'Permission inconnue.'})
    if Role.objects.filter(company=company, name=data['name']).exclude(pk=role_id).exists():
        raise ValidationError({'name': 'Ce nom de rôle existe déjà.'})
    if role_id:
        role = Role.objects.filter(company=company, pk=role_id).first()
        if role is None:
            raise NotFound()
        if role.is_system:
            raise ValidationError('Les rôles système ne peuvent pas être modifiés.')
        before = {'name': role.name, 'permissions': list(RolePermission.objects.filter(role=role).values_list('permission_id', flat=True))}
        role.name = data['name']
        role.save(update_fields=['name'])
    else:
        role = Role.objects.create(company=company, name=data['name'])
        before = {}
    RolePermission.objects.filter(role=role).exclude(permission_id__in=permission_codes).delete()
    for code in set(permission_codes):
        RolePermission.objects.get_or_create(role=role, permission_id=code)
    audit(company, actor, 'role.updated' if role_id else 'role.created', role, before, {'name': role.name, 'permissions': permission_codes})
    return role


@transaction.atomic
def assign_roles(actor, company_id, member_id, role_ids):
    company = locked_company(actor, company_id, 'members.manage')
    member = Membership.objects.filter(company=company, pk=member_id).first()
    if member is None:
        raise NotFound()
    roles = same_company_roles(company, role_ids)
    before = list(MembershipRole.objects.filter(membership=member).values_list('role_id', flat=True))
    MembershipRole.objects.filter(membership=member).exclude(role_id__in=role_ids).delete()
    for role in roles:
        MembershipRole.objects.get_or_create(company=company, membership=member, role=role)
    check_admin(company)
    audit(company, actor, 'membership.roles_updated', member, {'roles': [str(i) for i in before]}, {'roles': [str(role.id) for role in roles]})
    return member


@transaction.atomic
def activate_member(actor, company_id, member_id):
    company = locked_company(actor, company_id, 'members.manage')
    member = Membership.objects.filter(company=company, pk=member_id).first()
    if member is None:
        raise NotFound()
    if member.status != 'active':
        member.status = 'active'
        member.save(update_fields=['status'])
        audit(company, actor, 'membership.activated', member, {'status': 'suspended'}, {'status': 'active'})
    return member


def mail_invitation(invitation, raw):
    send_mail(f'Invitation à rejoindre {invitation.company.name}', f'Vous êtes invité à rejoindre {invitation.company.name} sur Qavelys.\n\nConnectez-vous ou créez votre compte avec cette adresse, puis ouvrez ce lien :\n{settings.FRONTEND_URL}/invitation#token={raw}\n\nCe lien expire dans 7 jours.', settings.DEFAULT_FROM_EMAIL, [invitation.email])


@transaction.atomic
def create_invitation(actor, company_id, email, role_ids):
    company = locked_company(actor, company_id, 'members.manage')
    roles = same_company_roles(company, role_ids)
    email = email.strip().lower()
    if Membership.objects.filter(company=company, user__email=email).exists():
        raise ValidationError('Cette personne possède déjà une adhésion ; gérez son accès depuis les membres.')
    if CompanyInvitation.objects.filter(company=company, email=email, accepted_at__isnull=True, revoked_at__isnull=True).exists():
        raise ValidationError('Une invitation existe déjà. Utilisez son action de renvoi.')
    raw = secrets.token_urlsafe(32)
    invitation = CompanyInvitation.objects.create(company=company, email=email, token_hash=hashlib.sha256(raw.encode()).hexdigest(), expires_at=timezone.now() + timedelta(days=7))
    InvitationRole.objects.bulk_create([InvitationRole(company=company, invitation=invitation, role=role) for role in roles])
    mail_invitation(invitation, raw)
    audit(company, actor, 'invitation.created', invitation, after={'email': email, 'roles': [str(role.id) for role in roles]})
    return invitation


@transaction.atomic
def change_invitation(actor, company_id, invitation_id, action):
    company = locked_company(actor, company_id, 'members.manage')
    invitation = CompanyInvitation.objects.select_for_update().filter(company=company, pk=invitation_id).first()
    if invitation is None:
        raise NotFound()
    if invitation.accepted_at or invitation.revoked_at:
        raise ValidationError('Cette invitation n’est plus active.')
    if action == 'revoke':
        invitation.revoked_at = timezone.now()
    else:
        raw = secrets.token_urlsafe(32)
        invitation.token_hash = hashlib.sha256(raw.encode()).hexdigest()
        invitation.expires_at = timezone.now() + timedelta(days=7)
        mail_invitation(invitation, raw)
    invitation.save()
    audit(company, actor, f'invitation.{action}', invitation)
    return invitation


@transaction.atomic
def accept_invitation(user, token):
    digest = hashlib.sha256(token.encode()).hexdigest()
    candidate = CompanyInvitation.objects.filter(token_hash=digest).first()
    if candidate is None:
        raise ValidationError('Invitation invalide ou expirée.')
    # Même ordre que l’administration : société puis invitation, jamais l’inverse.
    company = Company.objects.select_for_update().get(pk=candidate.company_id)
    invitation = CompanyInvitation.objects.select_for_update().get(pk=candidate.pk)
    if company.status != 'active' or invitation.token_hash != digest or invitation.accepted_at or invitation.revoked_at or invitation.expires_at <= timezone.now():
        raise ValidationError('Invitation invalide ou expirée.')
    if user.email.lower() != invitation.email.lower():
        raise PermissionDenied('Connectez-vous avec l’adresse destinataire de cette invitation.')
    member, _ = Membership.objects.get_or_create(company=company, user=user)
    if member.status != 'active':
        raise PermissionDenied('Votre adhésion est suspendue. Contactez l’administrateur.')
    for link in InvitationRole.objects.filter(invitation=invitation).select_related('role'):
        MembershipRole.objects.get_or_create(company=company, membership=member, role=link.role)
    invitation.accepted_at = timezone.now()
    invitation.save(update_fields=['accepted_at'])
    audit(company, user, 'invitation.accepted', invitation)
    return company


@transaction.atomic
def set_module(actor, company_id, code, enabled):
    company = locked_company(actor, company_id, 'modules.manage')
    module = Module.objects.filter(code=code).first()
    if module is None:
        raise NotFound()
    if not enabled and code == 'core':
        raise ValidationError('Le noyau reste toujours actif.')
    if not enabled and CompanyModule.objects.filter(company=company, enabled=True, module__dependencies__required_module=module).exists():
        raise ValidationError('Un autre module actif dépend de celui-ci. Désactivez-le d’abord.')
    visiting, done = set(), set()
    def enable(item):
        if item.id in visiting:
            raise ValidationError('Dépendance de modules cyclique.')
        if item.id in done:
            return
        if item.status != 'available':
            raise ValidationError(f'Le module {item.name} n’est pas encore disponible.')
        visiting.add(item.id)
        for dependency in item.dependencies.select_related('required_module').order_by('required_module__code'):
            enable(dependency.required_module)
        visiting.remove(item.id)
        done.add(item.id)
        update(item, True)
    def update(item, state):
        current, _ = CompanyModule.objects.get_or_create(company=company, module=item)
        if current.enabled != state:
            current.enabled = state
            current.activated_at = timezone.now() if state else current.activated_at
            current.save()
            audit(company, actor, 'module.enabled' if state else 'module.disabled', item, after={'code': item.code})
    enable(module) if enabled else update(module, False)


def require_module(company_id, code):
    if not CompanyModule.objects.filter(company_id=company_id, module__code=code, enabled=True, module__status='available').exists():
        raise PermissionDenied('Ce module n’est pas activé pour cette entreprise.')


@transaction.atomic
def next_reference(company, document_type):
    sequence = DocumentSequence.objects.select_for_update().filter(company=company, document_type=document_type).first()
    if sequence is None:
        raise ValidationError('Séquence documentaire non configurée.')
    number = sequence.next_number
    sequence.next_number += 1
    sequence.save(update_fields=['next_number'])
    return f'{sequence.prefix}{number:06d}'
