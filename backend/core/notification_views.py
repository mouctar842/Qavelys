from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from .pagination import paginate
from .notifications import access, visible, sync, data


class PrivateView(APIView):
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        return response


class Inbox(PrivateView):
    def get(self, request, company_id):
        member = access(request.user, company_id)
        query = visible(member)
        unread = query.filter(read_at__isnull=True).count()
        state = request.query_params.get('state', 'all')
        if state not in ['all', 'unread', 'read']: raise ValidationError('Filtre de lecture invalide.')
        if state != 'all': query = query.filter(read_at__isnull=state == 'unread')
        search = request.query_params.get('search', '').strip()[:200]
        if search: query = query.filter(Q(title__icontains=search) | Q(message__icontains=search))
        class Output:
            def __init__(self, rows, many): self.data = [data(obj) for obj in rows]
        response = paginate(request, query.select_related('approval_request', 'crm_activity').order_by('-created_at', '-id'), Output)
        response.data['unread_count'] = unread
        return response


class Summary(PrivateView):
    def get(self, request, company_id):
        member = access(request.user, company_id)
        return Response({'unread_count': visible(member).filter(read_at__isnull=True).count()})


class Sync(PrivateView):
    def post(self, request, company_id): return Response({'created': sync(request.user, company_id)})


class Read(PrivateView):
    @transaction.atomic
    def post(self, request, company_id, pk):
        member = access(request.user, company_id, True)
        obj = visible(member).filter(pk=pk).first()
        if obj is None: raise NotFound()
        read = serializers.BooleanField().run_validation(request.data.get('read'))
        if read != bool(obj.read_at):
            obj.read_at = timezone.now() if read else None
            obj.save(update_fields=['read_at'])
        return Response(data(obj))


class ReadAll(PrivateView):
    @transaction.atomic
    def post(self, request, company_id):
        member = access(request.user, company_id, True)
        count = visible(member).filter(read_at__isnull=True).update(read_at=timezone.now())
        return Response({'marked_read': count})
