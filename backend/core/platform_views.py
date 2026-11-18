from django.db.models import Count, Q
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Company, Membership, Module, PlatformAuditLog, User
from .platform_services import change_company, change_user, require_platform


class PlatformView(APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        require_platform(request.user)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response


def listing(request, query, render, ordering, default):
    try:
        page = int(request.query_params.get('page', 1))
        size = int(request.query_params.get('page_size', 25))
        if page < 1 or not 1 <= size <= 100:
            raise ValueError()
    except ValueError:
        raise ValidationError('Pagination invalide.')
    order = request.query_params.get('ordering', default)
    if order not in ordering:
        raise ValidationError('Tri invalide.')
    query = query.order_by(order, 'id')
    return Response({'count': query.count(), 'page': page, 'page_size': size,
        'results': [render(row) for row in query[(page - 1) * size:page * size]]})


def search(request):
    return request.query_params.get('search', '').strip()[:100]


def company_data(row):
    return {'id': row.id, 'name': row.name, 'status': row.status, 'country_code': row.country_code,
        'currency_code': row.currency_code, 'created_at': row.created_at,
        'owner_email': row.created_by.email, 'member_count': row.member_count}


def user_data(row):
    return {'id': row.id, 'email': row.email, 'full_name': row.full_name, 'is_active': row.is_active,
        'is_platform_admin': row.is_staff and row.is_superuser, 'email_verified': row.email_verified,
        'created_at': row.created_at, 'last_login': row.last_login}


class Overview(PlatformView):
    def get(self, request):
        return Response({'companies': Company.objects.count(), 'active_companies': Company.objects.filter(status='active').count(),
            'users': User.objects.count(), 'active_users': User.objects.filter(is_active=True).count(),
            'available_modules': Module.objects.filter(status='available').count()})


class Companies(PlatformView):
    def get(self, request):
        query = Company.objects.select_related('created_by').annotate(member_count=Count('membership'))
        term = search(request)
        if term:
            query = query.filter(Q(name__icontains=term) | Q(created_by__email__icontains=term))
        status = request.query_params.get('status', '')
        if status not in ('', 'active', 'suspended'):
            raise ValidationError('Statut invalide.')
        if status:
            query = query.filter(status=status)
        return listing(request, query, company_data, ['name', '-name', 'created_at', '-created_at'], 'name')


class Users(PlatformView):
    def get(self, request):
        query = User.objects.all()
        term = search(request)
        if term:
            query = query.filter(Q(email__icontains=term) | Q(full_name__icontains=term))
        status = request.query_params.get('status', '')
        if status not in ('', 'active', 'inactive'):
            raise ValidationError('Statut invalide.')
        if status:
            query = query.filter(is_active=status == 'active')
        return listing(request, query, user_data, ['email', '-email', 'created_at', '-created_at'], 'email')


class Reason(serializers.Serializer):
    reason = serializers.CharField(min_length=8, max_length=1000, trim_whitespace=True)


class CompanyAction(PlatformView):
    def post(self, request, pk, action):
        data = Reason(data=request.data); data.is_valid(raise_exception=True)
        row = change_company(request.user, pk, action == 'activate', data.validated_data['reason'])
        return Response({'id': row.id, 'status': row.status})


class UserAction(PlatformView):
    def post(self, request, pk, action):
        data = Reason(data=request.data); data.is_valid(raise_exception=True)
        row = change_user(request.user, pk, action == 'activate', data.validated_data['reason'])
        return Response(user_data(row))


class Modules(PlatformView):
    def get(self, request):
        query = Module.objects.annotate(enabled_companies=Count('companymodule', filter=Q(companymodule__enabled=True, companymodule__company__status='active')))
        if search(request):
            query = query.filter(Q(code__icontains=search(request)) | Q(name__icontains=search(request)))
        return listing(request, query, lambda row: {'id': row.id, 'code': row.code, 'name': row.name, 'description': row.description, 'status': row.status, 'enabled_companies': row.enabled_companies}, ['name', '-name', 'code', '-code'], 'name')


class Audit(PlatformView):
    def get(self, request):
        query = PlatformAuditLog.objects.select_related('actor', 'target_company', 'target_user')
        term = search(request)
        if term:
            query = query.filter(Q(action__icontains=term) | Q(reason__icontains=term) | Q(target_company__name__icontains=term) | Q(target_user__email__icontains=term))
        return listing(request, query, lambda row: {'id': row.id, 'created_at': row.created_at, 'action': row.action,
            'actor': row.actor.email if row.actor else 'Commande opérateur', 'source': row.source, 'reason': row.reason,
            'target': row.target_company.name if row.target_company else row.target_user.email,
            'before_data': row.before_data, 'after_data': row.after_data}, ['created_at', '-created_at'], '-created_at')
