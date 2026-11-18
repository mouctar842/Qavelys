import hashlib
import io
import json
import re
import runpy
import smtplib
import socketserver
import ssl
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command
from django.test import Client

from core.mail_delivery import MailDeliveryUnavailable, send_mail
from core.models import AuditLog, CompanyInvitation, EmailVerification, Role, User
from core.services import create_company
from core.verification import send_verification

pytestmark = pytest.mark.django_db
PASSWORD = 'Long-password!2026'


def post(client, path, data):
    csrf = client.get('/api/v1/auth/csrf/').json()['csrfToken']
    return client.post('/api/v1/' + path + '/', data=json.dumps(data),
                       content_type='application/json', HTTP_X_CSRFTOKEN=csrf)


@contextmanager
def smtp_server(settings, reject=False, stall=False):
    """Vraie connexion SMTP loopback, jamais d’envoi externe."""
    stop = threading.Event()

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.connection.settimeout(3)
            if stall:
                stop.wait(3)
                return
            self.wfile.write(b'220 localhost test SMTP\r\n')
            while line := self.rfile.readline():
                verb = line.split(b' ', 1)[0].strip().upper()
                if verb in (b'EHLO', b'HELO'):
                    self.wfile.write(b'250 localhost\r\n')
                elif verb == b'RCPT' and self.server.reject:
                    self.wfile.write(b'550 private-provider-detail-secret\r\n')
                elif verb == b'DATA':
                    self.wfile.write(b'354 send data\r\n')
                    body = []
                    while (chunk := self.rfile.readline()) not in (b'.\r\n', b''):
                        body.append(chunk)
                    self.server.messages.append(b''.join(body))
                    self.wfile.write(b'250 accepted\r\n')
                elif verb == b'QUIT':
                    self.wfile.write(b'221 bye\r\n')
                    return
                else:
                    self.wfile.write(b'250 ok\r\n')

    class Server(socketserver.ThreadingTCPServer):
        daemon_threads = True

    server = Server(('127.0.0.1', 0), Handler)
    server.reject, server.messages = reject, []
    settings.EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    settings.EMAIL_HOST = '127.0.0.1'
    settings.EMAIL_PORT = server.server_address[1]
    settings.EMAIL_HOST_USER = settings.EMAIL_HOST_PASSWORD = ''
    settings.EMAIL_USE_TLS = settings.EMAIL_USE_SSL = False
    settings.EMAIL_TIMEOUT = 0.2 if stall else 2
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        stop.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_smtp_registration_rejection_rollback_then_retry(settings, caplog):
    client = Client(enforce_csrf_checks=True)
    payload = {'email': 'smtp@example.com', 'password': PASSWORD, 'full_name': 'SMTP test'}
    with smtp_server(settings, reject=True) as server:
        response = post(client, 'auth/register', payload)
        assert response.status_code == 503
        assert not User.objects.filter(email=payload['email']).exists()
        assert not EmailVerification.objects.exists()
        assert not server.messages
        assert 'private-provider' not in response.content.decode()
        assert 'private-provider' not in caplog.text
        assert payload['email'] not in caplog.text
        server.reject = False
        assert post(client, 'auth/register', payload).status_code == 202
        assert len(server.messages) == 1
        # Le message est réellement passé sur le socket SMTP.
        token = re.search(rb'#token=([^\s]+)', server.messages[0])[1].decode()
        assert EmailVerification.objects.get().token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert post(client, 'auth/verify-email', {'token': token}).status_code == 200
        assert post(client, 'auth/login', payload).status_code == 200


def test_smtp_greeting_timeout_is_controlled(settings, caplog):
    with smtp_server(settings, stall=True):
        with pytest.raises(MailDeliveryUnavailable):
            send_mail('private subject', 'private body', 'sender@example.com', ['target@example.com'])
    assert 'mail_delivery_unavailable' in caplog.text
    assert 'private' not in caplog.text
    assert 'target@example.com' not in caplog.text


@pytest.mark.parametrize('failure', [
    ConnectionRefusedError('private connection'),
    ssl.SSLCertVerificationError('private certificate'),
    smtplib.SMTPAuthenticationError(535, b'private credentials'),
    smtplib.SMTPServerDisconnected('private disconnect'),
])
def test_network_tls_auth_errors_are_redacted(monkeypatch, caplog, failure):
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr('core.mail_delivery.django_send_mail', fail)
    with pytest.raises(MailDeliveryUnavailable) as caught:
        send_mail('secret subject', 'secret token', 'sender@example.com', ['target@example.com'])
    assert caught.value.status_code == 503
    assert 'private' not in str(caught.value)
    assert 'private' not in caplog.text
    assert 'secret' not in caplog.text


def test_zero_delivery_is_not_reported_as_success(monkeypatch):
    monkeypatch.setattr('core.mail_delivery.django_send_mail', lambda *a, **kw: 0)
    with pytest.raises(MailDeliveryUnavailable):
        send_mail('subject', 'body', 'sender@example.com', ['target@example.com'])


@pytest.mark.parametrize('overrides', [
    {'EMAIL_TIMEOUT': '0'}, {'EMAIL_TIMEOUT': '-1'},
    {'EMAIL_TIMEOUT': 'nan'}, {'EMAIL_TIMEOUT': 'inf'},
    {'EMAIL_USE_TLS': '1', 'EMAIL_USE_SSL': '1'},
])
def test_invalid_transport_configuration_is_rejected(monkeypatch, overrides):
    monkeypatch.setenv('EMAIL_USE_TLS', '0')
    monkeypatch.setenv('EMAIL_USE_SSL', '0')
    monkeypatch.setenv('EMAIL_TIMEOUT', '10')
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ValueError):
        runpy.run_path(str(Path(__file__).resolve().parents[1] / 'config' / 'settings.py'))


def test_resend_and_operator_failure_preserve_old_verification(settings):
    user = User.objects.create_user('resend-smtp@example.com', PASSWORD)
    with smtp_server(settings) as server:
        send_verification(user)
        previous = EmailVerification.objects.get()
        server.reject = True
        client = Client(enforce_csrf_checks=True)
        response = post(client, 'auth/resend-verification', {'email': user.email, 'password': PASSWORD})
        assert response.status_code == 503
        with pytest.raises(CommandError, match='temporairement indisponible'):
            call_command('resend_verification', user.email, stdout=io.StringIO())
        assert list(EmailVerification.objects.values_list('pk', flat=True)) == [previous.pk]
        token = re.search(rb'#token=([^\s]+)', server.messages[0])[1].decode()
        assert post(client, 'auth/verify-email', {'token': token}).status_code == 200


def test_reset_failure_keeps_neutral_response_password_and_session(settings):
    user = User.objects.create_user('reset-smtp@example.com', PASSWORD, email_verified=True)
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    original_password = user.password
    with smtp_server(settings, reject=True) as server:
        known = post(client, 'auth/password-reset', {'email': user.email})
        unknown = post(client, 'auth/password-reset', {'email': 'absent@example.com'})
        assert known.status_code == unknown.status_code == 202
        assert known.json() == unknown.json()
        assert client.get('/api/v1/auth/me/').status_code == 200
        user.refresh_from_db()
        assert user.password == original_password
        server.reject = False
        assert post(client, 'auth/password-reset', {'email': user.email}).status_code == 202
        assert len(server.messages) == 1


def test_invitation_failure_and_resend_preserve_old_link(settings):
    owner = User.objects.create_user('owner-smtp@example.com', PASSWORD, email_verified=True)
    company = create_company(owner, uuid.uuid4(), {'name': 'SMTP company', 'country_code': 'FR', 'currency_code': 'EUR'})[0]
    role = Role.objects.get(company=company, is_system=True)
    client = Client(enforce_csrf_checks=True)
    client.force_login(owner)
    path = f'companies/{company.pk}/invitations'
    payload = {'email': 'guest@example.com', 'role_ids': [str(role.pk)]}
    with smtp_server(settings, reject=True) as server:
        assert post(client, path, payload).status_code == 503
        assert not CompanyInvitation.objects.filter(company=company).exists()
        assert not AuditLog.objects.filter(company=company, action='invitation.created').exists()
        server.reject = False
        response = post(client, path, payload)
        assert response.status_code == 201
        invitation = CompanyInvitation.objects.get(pk=response.json()['id'])
        original = invitation.token_hash, invitation.expires_at
        server.reject = True
        assert post(client, f'{path}/{invitation.pk}/resend', {}).status_code == 503
        invitation.refresh_from_db()
        assert (invitation.token_hash, invitation.expires_at) == original
        assert not AuditLog.objects.filter(company=company, action='invitation.resend').exists()
