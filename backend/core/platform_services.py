from django.db import connection, transaction
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from .models import Company, Membership, PlatformAuditLog, User


def require_platform(user):
    actor = User.objects.filter(pk=user.pk, is_active=True, is_staff=True, is_superuser=True).first()
    if actor is None:
        raise PermissionDenied('Accès réservé à l’administration de la plateforme.')
    return actor


def lock_platform():
    # Namespace distinct des verrous métier ; libéré automatiquement au COMMIT/ROLLBACK.
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(%s)', [5855050901096383558])


def has_admin(company_id, excluding_user=None):
    query = Membership.objects.filter(company_id=company_id, status='active', user__is_active=True,
        membershiprole__role__company_id=company_id, membershiprole__role__is_system=True,
        membershiprole__role__name='Administrateur')
    if excluding_user:
        query = query.exclude(user_id=excluding_user)
    return query.exists()


@transaction.atomic
def change_company(actor, pk, active, reason):
    lock_platform()
    actor = require_platform(actor)
    company = Company.objects.select_for_update().filter(pk=pk).first()
    if company is None:
        raise NotFound()
    wanted = 'active' if active else 'suspended'
    if company.status == wanted:
        return company
    if active and not has_admin(company.id):
        raise ValidationError('Impossible de réactiver une entreprise sans administrateur actif.')
    before = {'status': company.status}
    company.status = wanted
    company.save(update_fields=['status'])
    PlatformAuditLog.objects.create(actor=actor, source='session', target_company=company,
        action='company.activated' if active else 'company.suspended', reason=reason,
        before_data=before, after_data={'status': wanted})
    return company


@transaction.atomic
def change_user(actor, pk, active, reason):
    lock_platform()
    actor = require_platform(actor)
    target = User.objects.select_for_update().filter(pk=pk).first()
    if target is None:
        raise NotFound()
    if target.pk == actor.pk and not active:
        raise ValidationError('Vous ne pouvez pas désactiver votre propre compte.')
    if target.is_active == active:
        return target
    if not active:
        if target.is_superuser and target.is_staff and not User.objects.filter(is_superuser=True, is_staff=True, is_active=True).exclude(pk=target.pk).exists():
            raise ValidationError('La plateforme doit conserver un super-administrateur actif.')
        # Même verrou société que les mutations de memberships/rôles normales.
        ids = list(Membership.objects.filter(user=target).values_list('company_id', flat=True))
        companies = list(Company.objects.select_for_update().filter(id__in=ids).order_by('id'))
        for company in companies:
            if company.status == 'active' and not has_admin(company.id, target.pk):
                raise ValidationError('Ce compte est le dernier administrateur actif d’une entreprise. Attribuez d’abord ce rôle à un autre membre.')
    target.is_active = active
    target.save(update_fields=['is_active'])
    PlatformAuditLog.objects.create(actor=actor, source='session', target_user=target,
        action='user.activated' if active else 'user.deactivated', reason=reason,
        before_data={'is_active': not active}, after_data={'is_active': active})
    return target
