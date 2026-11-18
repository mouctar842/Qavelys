import hashlib
import json
from uuid import UUID
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from core.administration import audit, locked_company, require_module
from core.models import Membership
from core.services import permissions_for, require_membership
from .models import Department, Employee, EmployeeMission
from .serializers import RESOURCES, render


class Conflict(APIException):
    status_code = 409
    default_detail = 'La fiche a changé. Rechargez-la avant de réessayer.'


def configuration(resource):
    if resource not in RESOURCES: raise NotFound()
    return RESOURCES[resource]


def access(user, company_id, resource, manage=False):
    _, _, kind = configuration(resource)
    member = require_membership(user, company_id, f'hr.{kind}.view')
    if manage: require_membership(user, company_id, f'hr.{kind}.manage')
    require_module(company_id, 'hr')
    return member


def query_for(resource, company_id):
    model, _, _ = configuration(resource)
    query = model.objects.filter(company_id=company_id)
    if model is Employee: query = query.select_related('department', 'membership')
    if model is EmployeeMission: query = query.select_related('employee')
    return query


def validate_relations(user, company, resource, data, obj=None):
    if resource == 'departments':
        if Department.objects.filter(company=company, name__iexact=data['name']).exclude(pk=obj.pk if obj else None).exists():
            raise ValidationError({'name': 'Un département porte déjà ce nom.'})
    if resource == 'employees':
        if Employee.objects.filter(company=company, staff_code=data['staff_code']).exclude(pk=obj.pk if obj else None).exists():
            raise ValidationError({'staff_code': 'Ce matricule existe déjà dans cette entreprise.'})
        department = data.get('department_id')
        if department and (obj is None or department != obj.department_id) and not Department.objects.filter(company=company, pk=department, status='active').exists():
            raise ValidationError({'department_id': 'Département actif introuvable dans cette entreprise.'})
        member_id = data.get('membership_id')
        if member_id and (obj is None or member_id != obj.membership_id):
            require_membership(user, company.pk, 'members.view')
            if not Membership.objects.filter(company=company, pk=member_id, status='active', user__is_active=True).exists():
                raise ValidationError({'membership_id': 'Accès actif introuvable dans cette entreprise.'})
        if member_id and Employee.objects.filter(company=company, membership_id=member_id).exclude(pk=obj.pk if obj else None).exists():
            raise ValidationError({'membership_id': 'Cet accès est déjà lié à une fiche employé.'})
    if resource == 'missions':
        employee = data['employee_id']
        if (obj is None or employee != obj.employee_id) and not Employee.objects.filter(company=company, pk=employee, status='active').exists():
            raise ValidationError({'employee_id': 'Employé actif introuvable dans cette entreprise.'})


def expected_version(payload, obj):
    class Version(serializers.Serializer):
        version = serializers.IntegerField(min_value=1)
    data = Version(data=payload); data.is_valid(raise_exception=True)
    if data.validated_data['version'] != obj.version: raise Conflict()


@transaction.atomic
def save(user, company_id, resource, payload, pk=None):
    _, serializer_class, kind = configuration(resource)
    company = locked_company(user, company_id, f'hr.{kind}.manage')
    access(user, company_id, resource, True)
    obj = query_for(resource, company_id).filter(pk=pk).first() if pk else None
    if pk and obj is None: raise NotFound()
    serializer = serializer_class(data=payload); serializer.is_valid(raise_exception=True)
    allowed = set(serializer.fields) | ({'version'} if pk else {'request_key'})
    if set(payload) - allowed: raise ValidationError('Champ non modifiable ou inconnu.')
    data = dict(serializer.validated_data)
    if pk:
        expected_version(payload, obj)
        if obj.status in ('archived', 'done', 'cancelled'):
            raise ValidationError('Réactivez ou rouvrez cette fiche avant de la modifier.')
    else:
        try: key = UUID(str(payload.get('request_key', '')))
        except ValueError: raise ValidationError({'request_key': 'Une clé UUID est obligatoire.'})
        digest = hashlib.sha256(json.dumps(data, cls=DjangoJSONEncoder, sort_keys=True).encode()).hexdigest()
        previous = query_for(resource, company_id).filter(request_key=key).first()
        if previous:
            if previous.payload_hash != digest: raise Conflict('Cette clé a déjà été utilisée avec un autre contenu.')
            return previous, False
    validate_relations(user, company, resource, data, obj)
    before = render(obj) if obj else {}
    if obj:
        for field, value in data.items(): setattr(obj, field, value)
        obj.version += 1
        obj.save()
    else:
        obj = RESOURCES[resource][0].objects.create(company=company, request_key=key, payload_hash=digest, **data)
    obj = query_for(resource, company_id).get(pk=obj.pk)
    audit(company, user, f'hr.{kind}_updated' if pk else f'hr.{kind}_created', obj, before, render(obj))
    return obj, not bool(pk)


class PeopleView(APIView):
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response


class Listing(PeopleView):
    def get(self, request, company_id, resource):
        access(request.user, company_id, resource)
        query = query_for(resource, company_id)
        search = request.query_params.get('search', '').strip()[:200]
        if search:
            if resource == 'employees':
                query = query.filter(Q(full_name__icontains=search) | Q(staff_code__icontains=search) | Q(email__icontains=search) | Q(job_title__icontains=search) | Q(department__name__icontains=search))
            elif resource == 'missions': query = query.filter(Q(title__icontains=search) | Q(employee__full_name__icontains=search))
            else: query = query.filter(name__icontains=search)
        state = request.query_params.get('state', 'todo' if resource == 'missions' else 'active')
        states = ('todo', 'in_progress', 'done', 'cancelled', 'all') if resource == 'missions' else ('active', 'archived', 'all')
        if state not in states: raise ValidationError('État invalide.')
        if state != 'all': query = query.filter(status=state)
        for field, target in [('department', 'employees'), ('employee', 'missions')]:
            if resource == target and request.query_params.get(field):
                try: value = UUID(request.query_params[field])
                except ValueError: raise ValidationError('Filtre invalide.')
                query = query.filter(**{field + '_id': value})
        order = request.query_params.get('ordering', 'title' if resource == 'missions' else 'full_name' if resource == 'employees' else 'name')
        fields = {'employees': ('full_name', 'staff_code', 'created_at'), 'departments': ('name', 'created_at'), 'missions': ('title', 'due_date', 'created_at')}[resource]
        if order not in {*fields, *('-' + field for field in fields)}: raise ValidationError('Tri invalide.')
        try:
            page = int(request.query_params.get('page', 1))
            if page < 1: raise ValueError()
        except ValueError: raise ValidationError('Page invalide.')
        return Response({'count': query.count(), 'results': [render(obj) for obj in query.order_by(order, 'id')[(page - 1) * 25:page * 25]]})

    def post(self, request, company_id, resource):
        obj, created = save(request.user, company_id, resource, request.data)
        return Response(render(obj), status=201 if created else 200)


class Detail(PeopleView):
    def get(self, request, company_id, resource, pk):
        access(request.user, company_id, resource)
        obj = query_for(resource, company_id).filter(pk=pk).first()
        if obj is None: raise NotFound()
        return Response(render(obj))

    def post(self, request, company_id, resource, pk):
        obj, _ = save(request.user, company_id, resource, request.data, pk)
        return Response(render(obj))


class Action(PeopleView):
    @transaction.atomic
    def post(self, request, company_id, resource, pk, action):
        _, _, kind = configuration(resource)
        company = locked_company(request.user, company_id, f'hr.{kind}.manage')
        access(request.user, company_id, resource, True)
        obj = query_for(resource, company_id).filter(pk=pk).first()
        if obj is None: raise NotFound()
        expected_version(request.data, obj)
        if set(request.data) != {'version'}: raise ValidationError('Seule la version est attendue.')
        transitions = {'start': (('todo',), 'in_progress'), 'complete': (('todo', 'in_progress'), 'done'), 'cancel': (('todo', 'in_progress'), 'cancelled'), 'reopen': (('done', 'cancelled'), 'todo')} if resource == 'missions' else {'archive': (('active',), 'archived'), 'restore': (('archived',), 'active')}
        if action not in transitions: raise NotFound()
        sources, target = transitions[action]
        if obj.status == target: return Response(render(obj))
        if obj.status not in sources: raise ValidationError('Transition non autorisée.')
        before = render(obj)
        obj.status = target; obj.version += 1
        if resource == 'missions': obj.completed_at = timezone.now() if target == 'done' else None
        obj.save()
        audit(company, request.user, f'hr.{kind}_{action}', obj, before, render(obj))
        return Response(render(obj))


class Lookups(PeopleView):
    def get(self, request, company_id):
        member = require_membership(request.user, company_id, 'company.view')
        require_module(company_id, 'hr')
        rights = permissions_for(member)
        if not any(f'hr.{kind}.manage' in rights and f'hr.{kind}.view' in rights for kind in ('employee', 'mission')):
            raise PermissionDenied('Accès insuffisant aux sélections RH.')
        result = {}
        if 'hr.employee.manage' in rights and 'hr.employee.view' in rights:
            result['departments'] = list(Department.objects.filter(company_id=company_id, status='active').order_by('name').values('id', 'name'))
            if 'members.view' in rights:
                result['memberships'] = [{'id': row.pk, 'name': row.user.full_name, 'email': row.user.email} for row in Membership.objects.filter(company_id=company_id, status='active', user__is_active=True).select_related('user').order_by('user__full_name')]
        if 'hr.mission.manage' in rights and 'hr.mission.view' in rights:
            result['employees'] = list(Employee.objects.filter(company_id=company_id, status='active').order_by('full_name').values('id', 'full_name', 'staff_code'))
        return Response(result)
