from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
import pytest
from django.db import close_old_connections
from rest_framework.exceptions import APIException
from core.models import AuditLog, Company, Membership, MembershipRole, Role, User
from core.services import create_company, suspend_member
from core.administration import next_reference

pytestmark = pytest.mark.django_db(transaction=True)


def test_document_sequences_do_not_collide_under_concurrency():
    user = User.objects.create_user('sequence@example.com', 'Long-password!2026', email_verified=True)
    company, _ = create_company(user, uuid4(), {'name': 'Séquences', 'country_code': 'GN', 'currency_code': 'GNF'})
    barrier = Barrier(4)
    def run(_):
        close_old_connections()
        try:
            barrier.wait(timeout=15)
            return next_reference(company, 'invoice')
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=4) as pool:
        references = list(pool.map(run, range(4)))
    assert sorted(references) == ['FAC-000001', 'FAC-000002', 'FAC-000003', 'FAC-000004']


def test_concurrent_company_creation_is_idempotent():
    user = User.objects.create_user('concurrent@example.com', 'Long-password!2026', email_verified=True)
    barrier = Barrier(2)
    key = uuid4()

    def run():
        close_old_connections()
        try:
            account = User.objects.get(pk=user.pk)
            barrier.wait(timeout=15)
            company, created = create_company(account, key, {'name': 'Concurrent', 'country_code': 'FR', 'currency_code': 'EUR'})
            return company.id, created
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(), range(2)))
    assert results[0][0] == results[1][0]
    assert sorted(result[1] for result in results) == [False, True]
    assert Company.objects.count() == 1
    assert AuditLog.objects.filter(action='company.created').count() == 1


def test_concurrent_admin_suspensions_keep_one_active_admin():
    first = User.objects.create_user('first@example.com', 'Long-password!2026', email_verified=True)
    second = User.objects.create_user('second@example.com', 'Long-password!2026', email_verified=True)
    company, _ = create_company(first, uuid4(), {'name': 'Concurrent', 'country_code': 'FR', 'currency_code': 'EUR'})
    second_member = Membership.objects.create(user=second, company=company)
    MembershipRole.objects.create(company=company, membership=second_member, role=Role.objects.get(company=company, is_system=True))
    first_member = Membership.objects.get(company=company, user=first)
    barrier = Barrier(2)

    def run(pair):
        close_old_connections()
        try:
            user_id, member_id = pair
            account = User.objects.get(pk=user_id)
            barrier.wait(timeout=15)
            try:
                suspend_member(account, company.id, member_id)
                return 'suspended'
            except APIException:
                return 'refused'
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, [(first.id, first_member.id), (second.id, second_member.id)]))
    assert sorted(results) == ['refused', 'suspended']
    assert Membership.objects.filter(company=company, status='active').count() == 1
