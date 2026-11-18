import hashlib
import io
import json
import re
import pytest
from django.core import mail
from django.core.management import call_command, CommandError
from django.test import Client
from core.models import EmailVerification, LoginAttempt, User

pytestmark = pytest.mark.django_db


def post(client, route, data):
    token = client.get('/api/v1/auth/csrf/').json()['csrfToken']
    return client.post('/api/v1/auth/' + route + '/', data=json.dumps(data), content_type='application/json', HTTP_X_CSRFTOKEN=token)


def test_local_mail_delivery_and_unverified_login_do_not_lock_account(settings, tmp_path):
    settings.DEBUG = True
    settings.EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
    settings.EMAIL_FILE_PATH = tmp_path
    client = Client(enforce_csrf_checks=True)
    credentials = {'email': 'local@example.com', 'password': 'Long-password!2026'}
    response = post(client, 'register', {**credentials, 'full_name': 'Utilisateur local'})
    assert response.status_code == 202
    assert '.local/emails' in response.json()['detail']
    files = list(tmp_path.iterdir())
    assert len(files) == 1
    token = re.search(r'#token=([^\s]+)', files[0].read_text(encoding='utf-8'))[1]
    assert token not in response.content.decode()
    for _ in range(6):
        pending = post(client, 'login', credentials)
        assert pending.status_code == 403
        assert pending.json()['code'] == 'email_not_verified'
    assert LoginAttempt.objects.get().failures == 0
    assert post(client, 'verify-email', {'token': token}).status_code == 200
    assert post(client, 'login', credentials).status_code == 200


def test_email_verification_clears_previous_login_lock(settings):
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    client = Client(enforce_csrf_checks=True)
    credentials = {'email': 'locked@example.com', 'password': 'Long-password!2026'}
    assert post(client, 'register', {**credentials, 'full_name': 'Compte bloqué'}).status_code == 202
    token = re.search(r'#token=([^\s]+)', mail.outbox[0].body)[1]
    for _ in range(5):
        assert post(client, 'login', {**credentials, 'password': 'incorrect'}).status_code == 400
    assert post(client, 'login', credentials).status_code == 429
    assert post(client, 'verify-email', {'token': token}).status_code == 200
    assert LoginAttempt.objects.get().failures == 0
    assert post(client, 'login', credentials).status_code == 200


def test_resend_command_sends_new_token_without_activating_account(settings):
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    user = User.objects.create_user('resend@example.com', 'Long-password!2026')
    output = io.StringIO()
    call_command('resend_verification', user.email.upper(), stdout=output)
    user.refresh_from_db()
    assert not user.email_verified
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [user.email]
    token = re.search(r'#token=([^\s]+)', mail.outbox[0].body)[1]
    assert EmailVerification.objects.get().token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert token not in output.getvalue()


@pytest.mark.parametrize('flags', [{'email_verified': True}, {'is_active': False}])
def test_resend_command_refuses_verified_or_inactive_account(settings, flags):
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    user = User.objects.create_user('refused@example.com', 'Long-password!2026', **flags)
    with pytest.raises(CommandError):
        call_command('resend_verification', user.email)
    assert not EmailVerification.objects.exists()
