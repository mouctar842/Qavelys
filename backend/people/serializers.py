from rest_framework import serializers
from .models import Department, Employee, EmployeeMission


class DepartmentInput(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    description = serializers.CharField(max_length=2000, required=False, allow_blank=True, default='')


class EmployeeInput(serializers.Serializer):
    staff_code = serializers.RegexField(r'^[A-Z0-9_-]{1,40}$', max_length=40)
    full_name = serializers.CharField(max_length=150)
    email = serializers.EmailField(max_length=254, required=False, allow_blank=True, default='')
    phone = serializers.CharField(max_length=40, required=False, allow_blank=True, default='')
    job_title = serializers.CharField(max_length=150, required=False, allow_blank=True, default='')
    responsibilities = serializers.CharField(max_length=4000, required=False, allow_blank=True, default='')
    department_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    membership_id = serializers.UUIDField(required=False, allow_null=True, default=None)


class MissionInput(serializers.Serializer):
    employee_id = serializers.UUIDField()
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(max_length=4000, required=False, allow_blank=True, default='')
    due_date = serializers.DateField(required=False, allow_null=True, default=None)


def render(obj):
    data = {'id': obj.pk, 'version': obj.version, 'status': obj.status, 'created_at': obj.created_at, 'updated_at': obj.updated_at}
    if isinstance(obj, Employee):
        data.update({field: getattr(obj, field) for field in ('staff_code', 'full_name', 'email', 'phone', 'job_title', 'responsibilities', 'department_id', 'membership_id')})
        data.update(department_name=obj.department.name if obj.department else None, membership_status=obj.membership.status if obj.membership else None)
    elif isinstance(obj, Department):
        data.update(name=obj.name, description=obj.description)
    else:
        data.update(employee_id=obj.employee_id, employee_name=obj.employee.full_name, title=obj.title, description=obj.description, due_date=obj.due_date, completed_at=obj.completed_at)
    return data


RESOURCES = {'employees': (Employee, EmployeeInput, 'employee'), 'departments': (Department, DepartmentInput, 'department'), 'missions': (EmployeeMission, MissionInput, 'mission')}
