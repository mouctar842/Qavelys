import json
import uuid
import pytest
from django.test import Client
from core.models import EmailVerification, User

pytestmark = pytest.mark.django_db


def post(client, route, data, **headers):
    token = client.get('/api/v1/auth/csrf/').json()['csrfToken']
    return client.post('/api/v1/' + route, data=json.dumps(data), content_type='application/json', HTTP_X_CSRFTOKEN=token, **headers)


def test_local_signup_login_and_company_without_verification(settings):
    settings.DEBUG = True
    settings.REQUIRE_EMAIL_VERIFICATION = False
    client = Client(enforce_csrf_checks=True)
    credentials = {'email': 'local-direct@example.com', 'password': 'Long-password!2026'}
    response = post(client, 'auth/register/', {**credentials, 'full_name': 'Local'})
    assert response.status_code == 201
    assert response.json()['authenticated'] is True
    assert client.get('/api/v1/auth/me/').status_code == 200
    assert not EmailVerification.objects.exists()
    account = User.objects.get()
    assert not account.email_verified
    assert not account.is_staff and not account.is_superuser
    company = post(client, 'companies/', {'name': 'Entreprise locale', 'country_code': 'FR', 'currency_code': 'EUR'}, HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
    assert company.status_code == 201
    context = client.get(f'/api/v1/companies/{company.json()["id"]}/context/').json()
    assert 'members.manage' in context['permissions']


def test_duplicate_registration_does_not_authenticate_existing_account(settings):
    settings.DEBUG = True
    settings.REQUIRE_EMAIL_VERIFICATION = False
    user = User.objects.create_user('duplicate@example.com', 'Long-password!2026')
    client = Client(enforce_csrf_checks=True)
    response = post(client, 'auth/register/', {'email': user.email, 'password': 'Another-password!2026', 'full_name': 'Autre personne'})
    assert response.status_code == 202
    assert response.json()['authenticated'] is False
    assert client.get('/api/v1/auth/me/').status_code == 403
    assert User.objects.count() == 1
    user.refresh_from_db()
    assert user.check_password('Long-password!2026')


def test_existing_unverified_account_can_log_in_locally(settings):
    settings.DEBUG = True
    settings.REQUIRE_EMAIL_VERIFICATION = False
    user = User.objects.create_user('existing@example.com', 'Long-password!2026')
    client = Client(enforce_csrf_checks=True)
    assert post(client, 'auth/login/', {'email': user.email, 'password': 'Long-password!2026'}).status_code == 200
    user.refresh_from_db()
    assert not user.email_verified
    settings.REQUIRE_EMAIL_VERIFICATION = True
    assert post(client, 'auth/logout/', {}).status_code == 200
    assert post(client, 'auth/login/', {'email': user.email, 'password': 'Long-password!2026'}).status_code == 403


def test_verification_cannot_be_disabled_outside_debug(settings):
    settings.DEBUG = False
    settings.REQUIRE_EMAIL_VERIFICATION = False
    user = User.objects.create_user('production@example.com', 'Long-password!2026')
    client = Client(enforce_csrf_checks=True)
    assert post(client, 'auth/login/', {'email': user.email, 'password': 'Long-password!2026'}).status_code == 403
    client.force_login(user)
    assert client.get('/api/v1/auth/me/').status_code == 403
    assert post(client, 'companies/', {'name': 'Refusée', 'country_code': 'FR', 'currency_code': 'EUR'}, HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4())).status_code == 403
