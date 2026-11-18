import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
import pytest
from django.db import IntegrityError, close_old_connections, transaction
from django.test import Client
from core.administration import set_module
from core.models import AuditLog, Membership, MembershipRole, Module, ModuleDependency, Role, RolePermission, User
from core.services import create_company
from people.models import Department, Employee, EmployeeMission

pytestmark = pytest.mark.django_db


def post(client, path, data):
    csrf = client.get('/api/v1/auth/csrf/').json()['csrfToken']
    return client.post(path, data=json.dumps(data), content_type='application/json', HTTP_X_CSRFTOKEN=csrf)


@pytest.fixture
def team():
    user = User.objects.create_user('team-admin@example.com', 'Long-password!2026', full_name='Responsable test', email_verified=True)
    company = create_company(user, uuid4(), {'name': 'Équipe test', 'country_code': 'FR', 'currency_code': 'EUR'})[0]
    # TransactionTestCase vide les données de migration après chaque test concurrent.
    # Reconstruire uniquement le catalogue requis par cette fixture, comme les domaines existants.
    module, _ = Module.objects.get_or_create(code='hr', defaults={'name': 'Équipe et missions', 'status': 'available'})
    ModuleDependency.objects.get_or_create(module=module, required_module=Module.objects.get(code='core'))
    set_module(user, company.pk, 'hr', True)
    client = Client(enforce_csrf_checks=True); client.force_login(user)
    return user, company, client, f'/api/v1/companies/{company.pk}/hr/'


def create(client, base, resource, **data):
    response = post(client, base + resource + '/', {'request_key': str(uuid4()), **data})
    assert response.status_code == 201, response.content
    return response.json()


def test_employee_without_account_department_search_update_and_archive(team):
    user, company, client, base = team
    users, members, assignments = User.objects.count(), Membership.objects.count(), MembershipRole.objects.count()
    department = create(client, base, 'departments', name='Atelier')
    employee = create(client, base, 'employees', staff_code='EMP-01', full_name='Aminata Diallo', department_id=department['id'], job_title='Technicienne', responsibilities='Contrôler les produits')
    assert employee['membership_id'] is None
    assert employee['department_name'] == 'Atelier'
    result = client.get(base + 'employees/', {'search': 'Atelier', 'department': department['id']})
    assert result.status_code == 200 and result.json()['count'] == 1
    assert result['Cache-Control'] == 'private, no-store'
    assert client.get(base + 'employees/', {'ordering': '--full_name'}).status_code == 400
    assert client.get(base + 'employees/', {'page': 'invalid'}).status_code == 400
    updated = post(client, base + f"employees/{employee['id']}/", {'version': 1, 'staff_code': 'EMP-01', 'full_name': 'Aminata Diallo', 'job_title': 'Cheffe atelier'})
    assert updated.status_code == 200 and updated.json()['version'] == 2
    assert post(client, base + f"employees/{employee['id']}/archive/", {'version': 2}).status_code == 200
    assert client.get(base + 'employees/').json()['count'] == 0
    assert client.get(base + 'employees/', {'state': 'archived'}).json()['count'] == 1
    assert (User.objects.count(), Membership.objects.count(), MembershipRole.objects.count()) == (users, members, assignments)
    assert User.objects.get(pk=user.pk).full_name == 'Responsable test'
    assert AuditLog.objects.filter(company=company, action='hr.employee_archive').exists()


def test_membership_link_is_optional_unique_and_does_not_change_access(team):
    user, company, client, base = team
    member = Membership.objects.get(company=company, user=user)
    employee = create(client, base, 'employees', staff_code='LINK', full_name='Nom local de fiche', membership_id=str(member.pk))
    from core.audit_presentation import present
    event = AuditLog.objects.get(company=company, action='hr.employee_created')
    assert {'label': 'Lien vers un accès Qavelys', 'before': 'Sans accès lié', 'after': 'Accès lié'} in present(event)['changes']
    assert post(client, base + 'employees/', {'request_key': str(uuid4()), 'staff_code': 'DUP', 'full_name': 'Duplicate', 'membership_id': str(member.pk)}).status_code == 400
    assert post(client, base + f"employees/{employee['id']}/archive/", {'version': 1}).status_code == 200
    member.refresh_from_db(); user.refresh_from_db()
    assert member.status == 'active' and user.is_active
    assert user.full_name == 'Responsable test'
    assert client.get('/api/v1/auth/me/').status_code == 200


def test_mission_lifecycle_and_archiving_employee_preserves_work(team):
    _, _, client, base = team
    employee = create(client, base, 'employees', staff_code='WORK', full_name='Employé terrain')
    mission = create(client, base, 'missions', employee_id=employee['id'], title='Contrôle atelier', due_date='2026-12-01')
    assert mission['status'] == 'todo' and mission['completed_at'] is None
    assert post(client, base + f"missions/{mission['id']}/start/", {'version': 1}).json()['status'] == 'in_progress'
    assert post(client, base + f"employees/{employee['id']}/archive/", {'version': 1}).status_code == 200
    done = post(client, base + f"missions/{mission['id']}/complete/", {'version': 2})
    assert done.status_code == 200 and done.json()['completed_at']
    assert post(client, base + f"missions/{mission['id']}/", {'version': 3, 'employee_id': employee['id'], 'title': 'Réécriture interdite'}).status_code == 400
    reopened = post(client, base + f"missions/{mission['id']}/reopen/", {'version': 3})
    assert reopened.json()['status'] == 'todo' and reopened.json()['completed_at'] is None
    assert post(client, base + f"missions/{mission['id']}/cancel/", {'version': 4}).json()['status'] == 'cancelled'
    assert post(client, base + 'missions/', {'request_key': str(uuid4()), 'employee_id': employee['id'], 'title': 'Nouvelle mission'}).status_code == 400


def test_department_archival_keeps_assignments_but_blocks_new_ones(team):
    _, _, client, base = team
    department = create(client, base, 'departments', name='Support')
    employee = create(client, base, 'employees', staff_code='SUP', full_name='Support test', department_id=department['id'])
    assert post(client, base + f"departments/{department['id']}/archive/", {'version': 1}).status_code == 200
    assert client.get(base + f"employees/{employee['id']}/").json()['department_name'] == 'Support'
    assert post(client, base + 'employees/', {'request_key': str(uuid4()), 'staff_code': 'SUP2', 'full_name': 'Autre', 'department_id': department['id']}).status_code == 400


def test_replays_versions_uniqueness_and_forbidden_fields(team):
    _, company, client, base = team
    payload = {'request_key': str(uuid4()), 'staff_code': 'ONCE', 'full_name': 'Création unique'}
    first = post(client, base + 'employees/', payload)
    assert first.status_code == 201
    assert post(client, base + 'employees/', payload).status_code == 200
    assert post(client, base + 'employees/', {**payload, 'full_name': 'Autre contenu'}).status_code == 409
    assert post(client, base + 'employees/', {**payload, 'request_key': str(uuid4())}).status_code == 400
    path = base + f"employees/{first.json()['id']}/"
    assert post(client, path, {'version': 99, 'staff_code': 'ONCE', 'full_name': 'Périmé'}).status_code == 409
    assert post(client, path, {'version': 1, 'staff_code': 'ONCE', 'full_name': 'Interdit', 'status': 'archived'}).status_code == 400
    assert AuditLog.objects.filter(company=company, action='hr.employee_created').count() == 1
    create(client, base, 'departments', name='Qualité')
    assert post(client, base + 'departments/', {'request_key': str(uuid4()), 'name': 'qualité'}).status_code == 400


def test_foreign_relations_objects_and_database_constraints(team):
    user, company, client, base = team
    other = create_company(user, uuid4(), {'name': 'Autre équipe', 'country_code': 'FR', 'currency_code': 'EUR'})[0]
    foreign_department = Department.objects.create(company=other, request_key=uuid4(), payload_hash='x', name='Secret')
    foreign_member = Membership.objects.get(company=other, user=user)
    foreign_employee = Employee.objects.create(company=other, request_key=uuid4(), payload_hash='x', staff_code='SECRET', full_name='Employé privé')
    for field, value in [('department_id', str(foreign_department.pk)), ('membership_id', str(foreign_member.pk))]:
        assert post(client, base + 'employees/', {'request_key': str(uuid4()), 'staff_code': 'CROSS', 'full_name': 'Interdit', field: value}).status_code == 400
    assert post(client, base + 'missions/', {'request_key': str(uuid4()), 'title': 'Interdit', 'employee_id': str(foreign_employee.pk)}).status_code == 400
    assert client.get(base + f'employees/{foreign_employee.pk}/').status_code == 404
    assert client.get(base + 'employees/', {'search': 'Employé privé', 'state': 'all'}).json()['count'] == 0
    with pytest.raises(IntegrityError), transaction.atomic():
        Employee.objects.create(company=company, request_key=uuid4(), payload_hash='x', staff_code='X', full_name='Interdit', department=foreign_department)
    with pytest.raises(IntegrityError), transaction.atomic():
        Employee.objects.create(company=company, request_key=uuid4(), payload_hash='x', staff_code='Y', full_name='Interdit', membership=foreign_member)
    with pytest.raises(IntegrityError), transaction.atomic():
        EmployeeMission.objects.create(company=company, request_key=uuid4(), payload_hash='x', title='Interdit', employee=foreign_employee)


def test_read_only_rights_module_suspension_csrf_and_global_flags(team):
    user, company, client, base = team
    reader = User.objects.create_user('hr-reader@example.com', 'Long-password!2026', email_verified=True)
    member = Membership.objects.create(company=company, user=reader)
    role = Role.objects.create(company=company, name='Lecteur RH')
    MembershipRole.objects.create(company=company, membership=member, role=role)
    for code in ('company.view', 'hr.employee.view'):
        RolePermission.objects.create(role=role, permission_id=code)
    limited = Client(enforce_csrf_checks=True); limited.force_login(reader)
    assert limited.get(base + 'employees/').status_code == 200
    assert limited.get(base + 'missions/').status_code == 403
    assert limited.get(base + 'lookups/').status_code == 403
    assert post(limited, base + 'employees/', {'request_key': str(uuid4()), 'staff_code': 'X', 'full_name': 'Interdit'}).status_code == 403
    assert client.post(base + 'employees/', data='{}', content_type='application/json').status_code == 403
    employee = create(client, base, 'employees', staff_code='KEEP', full_name='Conservé')
    set_module(user, company.pk, 'hr', False)
    assert client.get(base + 'employees/').status_code == 403
    assert Employee.objects.filter(pk=employee['id']).exists()
    set_module(user, company.pk, 'hr', True)
    company.status = 'suspended'; company.save(update_fields=['status'])
    assert client.get(base + 'employees/').status_code == 403
    outsider = User.objects.create_superuser('outsider-hr@example.com', 'Long-password!2026')
    limited.force_login(outsider)
    assert limited.get(base + 'employees/').status_code == 403


def test_lookup_link_permission_and_inactive_membership(team):
    user, company, client, base = team
    member = Membership.objects.get(company=company, user=user)
    member.status = 'suspended'; member.save(update_fields=['status'])
    assert client.get(base + 'lookups/').status_code == 403
    member.status = 'active'; member.save(update_fields=['status'])
    rows = client.get(base + 'lookups/').json()
    assert rows['memberships'][0]['id'] == str(member.pk)
    assert rows['employees'] == []
    role = Role.objects.get(company=company, is_system=True, name='Administrateur')
    RolePermission.objects.filter(role=role, permission_id='members.view').delete()
    assert 'memberships' not in client.get(base + 'lookups/').json()
    assert post(client, base + 'employees/', {'request_key': str(uuid4()), 'staff_code': 'NO-LINK', 'full_name': 'Lien interdit', 'membership_id': str(member.pk)}).status_code == 403


@pytest.mark.django_db(transaction=True)
def test_concurrent_employee_creation_and_stale_edit(team):
    user, company, _, base = team
    key = str(uuid4())
    def race(operation):
        barrier = Barrier(2)
        def run(index):
            close_old_connections()
            try:
                client = Client(enforce_csrf_checks=True); client.force_login(User.objects.get(pk=user.pk))
                barrier.wait(timeout=20)
                return operation(client, index)
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as executor:
            return list(executor.map(run, range(2)))
    results = race(lambda client, _: post(client, base + 'employees/', {'request_key': key, 'staff_code': 'RACE', 'full_name': 'Concurrent'}).status_code)
    assert sorted(results) == [200, 201]
    employee = Employee.objects.get(company=company, staff_code='RACE')
    edits = race(lambda client, index: post(client, base + f'employees/{employee.pk}/', {'version': 1, 'staff_code': 'RACE', 'full_name': f'Concurrent {index}'}).status_code)
    assert sorted(edits) == [200, 409]
    assert AuditLog.objects.filter(company=company, action='hr.employee_created').count() == 1
