import uuid
from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.db.models.functions import Lower


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra):
        user = self.model(email=email.strip().lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra):
        extra.update(is_staff=True, is_superuser=True, email_verified=True)
        return self.create_user(email, password, **extra)


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        abstract = True


class User(AbstractBaseUser, PermissionsMixin, UUIDModel):
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)
    USERNAME_FIELD = 'email'
    objects = UserManager()
    class Meta:
        constraints = [models.UniqueConstraint(Lower('email'), name='user_email_ci_unique')]


class Company(UUIDModel):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, max_length=250)
    country_code = models.CharField(max_length=2)
    currency_code = models.CharField(max_length=3)
    sector = models.CharField(max_length=100, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, default='active', choices=[('active', 'Active'), ('suspended', 'Suspendue')])


class CompanySettings(models.Model):
    company = models.OneToOneField(Company, primary_key=True, on_delete=models.PROTECT)
    logo = models.ForeignKey('CompanyLogo', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    timezone = models.CharField(max_length=80, default='UTC')
    locale = models.CharField(max_length=20, default='fr')


class CompanyLogo(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    file = models.FileField(max_length=300)
    sha256 = models.CharField(max_length=64)
    byte_size = models.PositiveIntegerField()
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    class Meta:
        constraints = [models.UniqueConstraint(fields=['id', 'company'], name='company_logo_id_company_uq'), models.CheckConstraint(condition=models.Q(byte_size__gt=0, byte_size__lte=2097152, width__gte=1, width__lte=1024, height__gte=1, height__lte=1024), name='company_logo_dimensions_valid')]


class PlatformAuditLog(UUIDModel):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name='platform_actions')
    source = models.CharField(max_length=20, choices=[('session', 'Session'), ('management', 'Commande opérateur')])
    target_company = models.ForeignKey(Company, null=True, on_delete=models.PROTECT)
    target_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name='platform_history')
    action = models.CharField(max_length=60)
    reason = models.CharField(max_length=1000)
    before_data = models.JSONField(default=dict)
    after_data = models.JSONField(default=dict)
    class Meta:
        constraints = [models.CheckConstraint(condition=(models.Q(target_company__isnull=False, target_user__isnull=True) | models.Q(target_company__isnull=True, target_user__isnull=False)), name='platform_audit_one_target'), models.CheckConstraint(condition=(models.Q(source='session', actor__isnull=False) | models.Q(source='management', actor__isnull=True)), name='platform_audit_actor_source_valid')]
        indexes = [models.Index(fields=['created_at', 'id'])]


class Membership(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, default='active', choices=[('active', 'Actif'), ('suspended', 'Suspendu')])
    joined_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['company', 'user'], name='membership_company_user_unique'), models.UniqueConstraint(fields=['id', 'company'], name='membership_id_company_unique')]
        indexes = [models.Index(fields=['user', 'status'])]


class Role(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    name = models.CharField(max_length=100)
    is_system = models.BooleanField(default=False)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['company', 'name'], name='role_company_name_unique'), models.UniqueConstraint(fields=['id', 'company'], name='role_id_company_unique')]


class Permission(models.Model):
    code = models.CharField(primary_key=True, max_length=100)
    description = models.CharField(max_length=200)


class MembershipRole(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    membership = models.ForeignKey(Membership, on_delete=models.PROTECT)
    role = models.ForeignKey(Role, on_delete=models.PROTECT)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['membership', 'role'], name='membership_role_unique')]


class RolePermission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.PROTECT)
    permission = models.ForeignKey(Permission, on_delete=models.PROTECT)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['role', 'permission'], name='role_permission_unique')]


class CompanyCreation(UUIDModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    key = models.UUIDField()
    payload_hash = models.CharField(max_length=64)
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'key'], name='company_creation_idempotency_unique')]


class AuditLog(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=100)
    entity_type = models.CharField(max_length=100)
    entity_id = models.UUIDField()
    before_data = models.JSONField(default=dict)
    after_data = models.JSONField(default=dict)
    class Meta:
        indexes = [models.Index(fields=['company', 'created_at'])]


class EmailVerification(UUIDModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True)


class LoginAttempt(models.Model):
    key = models.CharField(primary_key=True, max_length=64)
    failures = models.PositiveIntegerField(default=0)
    window_start = models.DateTimeField()


class AuthThrottle(models.Model):
    key = models.CharField(primary_key=True, max_length=64)
    count = models.PositiveIntegerField(default=0)
    window_start = models.DateTimeField()


class Module(UUIDModel):
    code = models.SlugField(unique=True, max_length=40)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, default='planned', choices=[('available', 'Disponible'), ('planned', 'À venir')])


class CompanyModule(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    module = models.ForeignKey(Module, on_delete=models.PROTECT)
    enabled = models.BooleanField(default=False)
    activated_at = models.DateTimeField(null=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['company', 'module'], name='company_module_unique')]


class ModuleDependency(models.Model):
    module = models.ForeignKey(Module, on_delete=models.PROTECT, related_name='dependencies')
    required_module = models.ForeignKey(Module, on_delete=models.PROTECT, related_name='dependents')
    class Meta:
        constraints = [models.UniqueConstraint(fields=['module', 'required_module'], name='module_dependency_unique'), models.CheckConstraint(condition=~models.Q(module=models.F('required_module')), name='module_no_self_dependency')]


class CompanyInvitation(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    email = models.EmailField()
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True)
    revoked_at = models.DateTimeField(null=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['id', 'company'], name='invitation_id_company_unique'), models.UniqueConstraint(fields=['company', 'email'], condition=models.Q(accepted_at__isnull=True, revoked_at__isnull=True), name='invitation_pending_email_unique')]
        indexes = [models.Index(fields=['company', 'created_at'])]


class InvitationRole(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    invitation = models.ForeignKey(CompanyInvitation, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.PROTECT)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['invitation', 'role'], name='invitation_role_unique')]


class DocumentSequence(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    document_type = models.CharField(max_length=40)
    prefix = models.CharField(max_length=20)
    next_number = models.PositiveBigIntegerField(default=1)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['company', 'document_type'], name='sequence_company_type_unique'), models.CheckConstraint(condition=models.Q(next_number__gte=1), name='sequence_positive_number')]


class Notification(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    recipient = models.ForeignKey(Membership, on_delete=models.PROTECT, related_name='notifications')
    type = models.CharField(max_length=30, choices=[('approval_request', 'Approbation demandée'), ('approval_decision', 'Décision'), ('crm_due', 'Activité échue'), ('invoice_overdue', 'Facture en retard')])
    event_key = models.CharField(max_length=200)
    title = models.CharField(max_length=240)
    message = models.TextField()
    read_at = models.DateTimeField(null=True)
    source_due_at = models.DateTimeField(null=True)
    approval_request = models.ForeignKey('approvals.ApprovalRequest', null=True, on_delete=models.PROTECT)
    crm_activity = models.ForeignKey('crm.CRMActivity', null=True, on_delete=models.PROTECT)
    invoice = models.ForeignKey('invoicing.Invoice', null=True, on_delete=models.PROTECT)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['company', 'recipient', 'event_key'], name='notification_recipient_event_uq'), models.CheckConstraint(condition=(models.Q(type__in=['approval_request', 'approval_decision'], approval_request__isnull=False, crm_activity__isnull=True, invoice__isnull=True) | models.Q(type='crm_due', approval_request__isnull=True, crm_activity__isnull=False, invoice__isnull=True, source_due_at__isnull=False) | models.Q(type='invoice_overdue', approval_request__isnull=True, crm_activity__isnull=True, invoice__isnull=False)), name='notification_source_valid')]
        indexes = [models.Index(fields=['company', 'recipient', 'read_at', 'created_at'])]
