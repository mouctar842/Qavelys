from django.db import transaction
from django.db.models import Q
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from core.administration import audit, locked_company, require_module
from core.models import AuditLog, Membership
from core.services import require_membership
from reference.models import Partner
from reference.serializers import PartnerSerializer
from .models import CRMActivity, Lead, STAGES
from .serializers import ActivitySerializer, LeadSerializer


def access(user, company_id, manage=False, lock=False):
    permission = 'crm.manage' if manage else 'crm.view'
    if lock:
        company = locked_company(user, company_id, permission)
    else:
        company = require_membership(user, company_id, permission).company
    require_module(company_id, 'crm')
    return company


def leads(company_id):
    return Lead.objects.filter(company_id=company_id).select_related('partner', 'owner__user')


def activities(company_id):
    return CRMActivity.objects.filter(company_id=company_id).select_related('lead', 'assigned_to__user')


def get_lead(company_id, pk):
    obj = leads(company_id).filter(pk=pk).first()
    if obj is None: raise NotFound()
    return obj


def paginate(request, query, serializer):
    try:
        page = max(1, int(request.query_params.get('page', 1)))
        size = min(100, max(1, int(request.query_params.get('page_size', 25))))
    except ValueError:
        raise ValidationError('Pagination invalide.')
    return Response({'count': query.count(), 'page': page, 'page_size': size, 'results': serializer(query[(page - 1) * size:page * size], many=True).data})


class LeadsView(APIView):
    def get(self, request, company_id):
        access(request.user, company_id)
        query = leads(company_id)
        search = request.query_params.get('search', '').strip()[:200]
        if search: query = query.filter(Q(title__icontains=search) | Q(partner__name__icontains=search))
        if request.query_params.get('stage'):
            if request.query_params['stage'] not in dict(STAGES): raise ValidationError('Étape inconnue.')
            query = query.filter(stage=request.query_params['stage'])
        if request.query_params.get('owner'):
            owner = serializers.UUIDField().run_validation(request.query_params['owner'])
            query = query.filter(owner_id=owner)
        return paginate(request, query.order_by('-created_at', '-id'), LeadSerializer)
    @transaction.atomic
    def post(self, request, company_id):
        company = access(request.user, company_id, True, True)
        serializer = LeadSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        data.setdefault('owner_id', require_membership(request.user, company_id, 'crm.manage').id)
        validate_relations(company_id, data)
        obj = Lead.objects.create(company=company, **data)
        obj = get_lead(company_id, obj.pk)
        audit(company, request.user, 'crm.lead_created', obj, after=LeadSerializer(obj).data)
        return Response(LeadSerializer(obj).data, status=201)


def validate_relations(company_id, data, current=None, activity=False):
    member_field = 'assigned_to_id' if activity else 'owner_id'
    if member_field in data and (not current or data[member_field] != getattr(current, member_field)) and not Membership.objects.filter(company_id=company_id, pk=data[member_field], status='active').exists():
        raise ValidationError({member_field: 'Collaborateur actif introuvable dans cette entreprise.'})
    if not activity and data.get('partner_id') and not Partner.objects.filter(company_id=company_id, pk=data['partner_id'], status='active').exists():
        raise ValidationError({'partner_id': 'Contact actif introuvable dans cette entreprise.'})
    if activity and 'lead_id' in data and not Lead.objects.filter(company_id=company_id, pk=data['lead_id']).exists():
        raise ValidationError({'lead_id': 'Prospect introuvable dans cette entreprise.'})


class LeadDetail(APIView):
    def get(self, request, company_id, pk):
        access(request.user, company_id)
        return Response(LeadSerializer(get_lead(company_id, pk)).data)


class LeadAction(APIView):
    @transaction.atomic
    def post(self, request, company_id, pk, action):
        company = access(request.user, company_id, True, True)
        obj = get_lead(company_id, pk)
        before = LeadSerializer(obj).data
        if action == 'update':
            serializer = LeadSerializer(obj, data=request.data, partial=True); serializer.is_valid(raise_exception=True)
            data = dict(serializer.validated_data); validate_relations(company_id, data, obj)
            for field, value in data.items(): setattr(obj, field, value)
        elif action == 'move':
            class Move(serializers.Serializer): stage = serializers.ChoiceField(choices=STAGES)
            serializer = Move(data=request.data); serializer.is_valid(raise_exception=True)
            if obj.stage == serializer.validated_data['stage']: return Response(LeadSerializer(obj).data)
            obj.stage = serializer.validated_data['stage']
        elif action == 'convert-customer':
            require_membership(request.user, company_id, 'contacts.manage')
            require_module(company_id, 'contacts')
            if obj.partner_id:
                partner = obj.partner
                if partner.status != 'active': raise ValidationError('Le contact rattaché est archivé.')
                if partner.is_customer: return Response(LeadSerializer(obj).data)
                if not partner.is_customer:
                    partner.is_customer = True; partner.save(update_fields=['is_customer', 'updated_at'])
                    audit(company, request.user, 'contacts.converted_customer', partner, after={'is_customer': True})
            else:
                serializer = PartnerSerializer(data=request.data); serializer.is_valid(raise_exception=True)
                data = dict(serializer.validated_data); data['is_customer'] = True
                partner = Partner.objects.create(company=company, **data)
                audit(company, request.user, 'contacts.created_from_lead', partner, after=PartnerSerializer(partner).data)
                obj.partner = partner
        else: raise NotFound()
        obj.save()
        obj = get_lead(company_id, pk)
        audit(company, request.user, 'crm.lead_' + action.replace('-', '_'), obj, before, LeadSerializer(obj).data)
        return Response(LeadSerializer(obj).data)


class ActivitiesView(APIView):
    def get(self, request, company_id):
        access(request.user, company_id)
        query = activities(company_id)
        if request.query_params.get('lead'):
            lead_id = serializers.UUIDField().run_validation(request.query_params['lead'])
            get_lead(company_id, lead_id)
            query = query.filter(lead_id=lead_id)
        status = request.query_params.get('status')
        if status:
            if status not in ('planned', 'done', 'cancelled'): raise ValidationError('Statut inconnu.')
            query = query.filter(status=status)
        return paginate(request, query.order_by('due_at', 'id'), ActivitySerializer)
    @transaction.atomic
    def post(self, request, company_id):
        company = access(request.user, company_id, True, True)
        serializer = ActivitySerializer(data=request.data); serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        data.setdefault('assigned_to_id', require_membership(request.user, company_id, 'crm.manage').id)
        validate_relations(company_id, data, activity=True)
        obj = CRMActivity.objects.create(company=company, **data)
        obj = activities(company_id).get(pk=obj.pk)
        audit(company, request.user, 'crm.activity_created', obj, after=ActivitySerializer(obj).data)
        return Response(ActivitySerializer(obj).data, status=201)


class ActivityAction(APIView):
    @transaction.atomic
    def post(self, request, company_id, pk, action):
        company = access(request.user, company_id, True, True)
        obj = activities(company_id).filter(pk=pk).first()
        if obj is None: raise NotFound()
        before = ActivitySerializer(obj).data
        target = {'complete': 'done', 'cancel': 'cancelled'}.get(action)
        if target and obj.status == target: return Response(before)
        if obj.status != 'planned': raise ValidationError('Cette activité n’est plus modifiable.')
        if action == 'update':
            serializer = ActivitySerializer(obj, data=request.data, partial=True); serializer.is_valid(raise_exception=True)
            data = dict(serializer.validated_data); validate_relations(company_id, data, obj, activity=True)
            if 'lead_id' in data and data['lead_id'] != obj.lead_id:
                raise ValidationError('Une activité ne peut pas être déplacée vers un autre prospect.')
            for field, value in data.items(): setattr(obj, field, value)
        elif target: obj.status = target
        else: raise NotFound()
        obj.save()
        obj = activities(company_id).get(pk=obj.pk)
        audit(company, request.user, 'crm.activity_' + action, obj, before, ActivitySerializer(obj).data)
        return Response(ActivitySerializer(obj).data)


class LeadHistory(APIView):
    def get(self, request, company_id, pk):
        access(request.user, company_id)
        get_lead(company_id, pk)
        activity_ids = CRMActivity.objects.filter(company_id=company_id, lead_id=pk).values('id')
        query = AuditLog.objects.filter(company_id=company_id).filter(Q(entity_type='Lead', entity_id=pk) | Q(entity_type='CRMActivity', entity_id__in=activity_ids)).select_related('actor').order_by('-created_at', '-id')
        try: page = max(1, int(request.query_params.get('page', 1)))
        except ValueError: raise ValidationError('Page invalide.')
        return Response({'count': query.count(), 'results': [{'id': item.id, 'action': item.action, 'actor': item.actor.full_name, 'created_at': item.created_at, 'before_data': item.before_data, 'after_data': item.after_data} for item in query[(page - 1) * 25:page * 25]]})


class Lookups(APIView):
    def get(self, request, company_id):
        access(request.user, company_id)
        search = request.query_params.get('search', '').strip()[:100]
        return Response({'members': [{'id': member.id, 'name': member.user.full_name} for member in Membership.objects.filter(company_id=company_id, status='active').select_related('user').order_by('user__full_name')], 'partners': list(Partner.objects.filter(company_id=company_id, status='active', name__icontains=search).order_by('name').values('id', 'name')[:100]), 'stages': [{'code': code, 'name': label} for code, label in STAGES]})
