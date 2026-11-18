import hashlib
import json
import uuid
from django.db import transaction
from django.utils.text import slugify
from rest_framework.exceptions import PermissionDenied, ValidationError
from .models import (AuditLog, Company, CompanyCreation, CompanySettings, Membership,
                     MembershipRole, Permission, Role, RolePermission, User)
from .catalog import CORE_PERMISSIONS, SEQUENCES


def permissions_for(membership):
    return sorted(set(RolePermission.objects.filter(role__membershiprole__membership=membership, role__company=membership.company, role__membershiprole__company=membership.company).values_list('permission_id', flat=True)))


def require_membership(user, company_id, permission):
    membership = Membership.objects.filter(user=user, user__is_active=True, company_id=company_id, status='active', company__status='active').first()
    if not membership or permission not in permissions_for(membership):
        raise PermissionDenied('Accès interdit à cette entreprise ou permission insuffisante.')
    return membership


@transaction.atomic
def create_company(user, key, data):
    # Verrou utilisateur : sérialise également les premières requêtes avec la même clé.
    User.objects.select_for_update().get(pk=user.pk)
    fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    previous = CompanyCreation.objects.filter(user=user, key=key).select_related('company').first()
    if previous:
        if previous.payload_hash != fingerprint:
            raise ValidationError('Cette clé a déjà été utilisée avec des données différentes.')
        require_membership(user, previous.company_id, 'company.view')
        return previous.company, False
    company = Company.objects.create(created_by=user, slug=f'{slugify(data["name"])[:180] or "entreprise"}-{uuid.uuid4().hex}', **data)
    CompanySettings.objects.create(company=company)
    from inventory.services import initialize_inventory
    initialize_inventory(company)
    member = Membership.objects.create(company=company, user=user)
    role = Role.objects.create(company=company, name='Administrateur', is_system=True)
    MembershipRole.objects.create(company=company, membership=member, role=role)
    for code, description in CORE_PERMISSIONS.items():
        permission, _ = Permission.objects.get_or_create(code=code, defaults={'description': description})
        RolePermission.objects.create(role=role, permission=permission)
    CompanyCreation.objects.create(user=user, key=key, company=company, payload_hash=fingerprint)
    from .models import CompanyModule, DocumentSequence, Module
    core, _ = Module.objects.get_or_create(code='core', defaults={'name': 'Administration', 'status': 'available'})
    CompanyModule.objects.create(company=company, module=core, enabled=True, activated_at=member.joined_at)
    DocumentSequence.objects.bulk_create([DocumentSequence(company=company, document_type=kind, prefix=prefix) for kind, prefix in SEQUENCES.items()])
    AuditLog.objects.create(company=company, actor=user, action='company.created', entity_type='Company', entity_id=company.id, after_data={'name': company.name})
    return company, True


@transaction.atomic
def suspend_member(actor, company_id, member_id):
    # Toutes les mutations d’administration doivent prendre ce verrou avant les membres.
    company = Company.objects.select_for_update().get(pk=company_id)
    require_membership(actor, company_id, 'members.manage')
    member = Membership.objects.select_for_update().filter(company=company, pk=member_id).first()
    if member is None:
        from rest_framework.exceptions import NotFound
        raise NotFound()
    admins = Membership.objects.filter(company=company, status='active', user__is_active=True, membershiprole__role__is_system=True, membershiprole__role__name='Administrateur').distinct()
    if member.status == 'active' and admins.filter(pk=member.pk).exists() and admins.count() <= 1:
        raise ValidationError('L’entreprise doit conserver au moins un administrateur actif.')
    if member.status != 'suspended':
        member.status = 'suspended'
        member.save(update_fields=['status'])
        AuditLog.objects.create(company=company, actor=actor, action='membership.suspended', entity_type='Membership', entity_id=member.id, before_data={'status': 'active'}, after_data={'status': 'suspended'})
    return member
