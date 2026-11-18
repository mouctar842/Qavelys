from django.db import models
from django.db.models.functions import Lower
from core.models import Membership
from reference.models import CompanyEntity


class TeamEntity(CompanyEntity):
    version = models.PositiveIntegerField(default=1)
    request_key = models.UUIDField()
    payload_hash = models.CharField(max_length=64)
    class Meta:
        abstract = True
        constraints = [models.UniqueConstraint(fields=['id', 'company'], name='%(class)s_tenant_uq'), models.UniqueConstraint(fields=['company', 'request_key'], name='%(class)s_request_uq'), models.CheckConstraint(condition=models.Q(version__gte=1), name='%(class)s_version_positive')]


class Department(TeamEntity):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, default='active')
    class Meta(TeamEntity.Meta):
        abstract = False
        constraints = TeamEntity.Meta.constraints + [models.UniqueConstraint(Lower('name'), 'company', name='department_name_tenant_ci_uq'), models.CheckConstraint(condition=models.Q(status__in=['active', 'archived']), name='department_status_valid')]
        indexes = [models.Index(fields=['company', 'status', 'name'])]


class Employee(TeamEntity):
    staff_code = models.CharField(max_length=40)
    full_name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    job_title = models.CharField(max_length=150, blank=True)
    responsibilities = models.TextField(blank=True)
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.PROTECT)
    membership = models.ForeignKey(Membership, null=True, blank=True, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, default='active')
    class Meta(TeamEntity.Meta):
        abstract = False
        constraints = TeamEntity.Meta.constraints + [models.UniqueConstraint(fields=['company', 'staff_code'], name='employee_staff_tenant_uq'), models.UniqueConstraint(fields=['company', 'membership'], name='employee_membership_tenant_uq'), models.CheckConstraint(condition=models.Q(status__in=['active', 'archived']), name='employee_status_valid')]
        indexes = [models.Index(fields=['company', 'status', 'full_name'])]


class EmployeeMission(TeamEntity):
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name='missions')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, default='todo')
    completed_at = models.DateTimeField(null=True, blank=True)
    class Meta(TeamEntity.Meta):
        abstract = False
        constraints = TeamEntity.Meta.constraints + [models.CheckConstraint(condition=models.Q(status__in=['todo', 'in_progress', 'done', 'cancelled']), name='mission_status_valid'), models.CheckConstraint(condition=(models.Q(status='done', completed_at__isnull=False) | (~models.Q(status='done') & models.Q(completed_at__isnull=True))), name='mission_completion_consistent')]
        indexes = [models.Index(fields=['company', 'status', 'due_date'])]
