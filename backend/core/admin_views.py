from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from datetime import date
from uuid import UUID
from django.db.models import Q
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from .administration import (accept_invitation, activate_member, assign_roles, audit, change_invitation,
                             create_invitation, locked_company, save_role, set_module)
from .models import (AuditLog, CompanyInvitation, CompanyModule, CompanySettings, DocumentSequence,
                     MembershipRole, Module, Permission, Role, RolePermission)
from .serializers import MembershipSerializer, RoleSerializer
from .services import require_membership
from .admin_catalog import SEQUENCE_INFO, TEMPLATES, module_for, module_label
from .audit_presentation import present, action_label


class RoleInput(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    permission_codes = serializers.ListField(child=serializers.CharField(max_length=100), allow_empty=True)


class RoleIds(serializers.Serializer):
    role_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)


class InvitationInput(RoleIds):
    email = serializers.EmailField()


class SettingsInput(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    sector = serializers.CharField(max_length=100, allow_blank=True)
    address = serializers.CharField(max_length=2000, allow_blank=True)
    phone = serializers.CharField(max_length=40, allow_blank=True)
    timezone = serializers.CharField(max_length=80)
    locale = serializers.RegexField(r'^[a-z]{2}(?:-[A-Z]{2})?$')
    def validate_timezone(self, value):
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            raise serializers.ValidationError('Fuseau horaire IANA inconnu.')
        return value


def validated(serializer, data):
    instance = serializer(data=data)
    instance.is_valid(raise_exception=True)
    return instance.validated_data


def invitation_data(invitation):
    return {'id': invitation.id, 'email': invitation.email, 'expires_at': invitation.expires_at, 'accepted_at': invitation.accepted_at, 'revoked_at': invitation.revoked_at, 'role_ids': list(invitation.invitationrole_set.values_list('role_id', flat=True))}


class PermissionsView(APIView):
    def get(self, request, company_id):
        require_membership(request.user, company_id, 'roles.view')
        names = dict(Module.objects.values_list('code', 'name'))
        return Response([{**row, 'module_code': module_for(row['code']), 'module_name': module_label(module_for(row['code']), names)} for row in Permission.objects.order_by('code').values('code', 'description')])


class RoleTemplatesView(APIView):
    def get(self, request, company_id):
        require_membership(request.user, company_id, 'roles.view')
        known = set(Permission.objects.values_list('code', flat=True))
        existing = set(Role.objects.filter(company_id=company_id).values_list('name', flat=True))
        return Response([{'code': code, 'name': name, 'permission_codes': sorted(codes & known), 'installed': name in existing} for code, (name, codes) in TEMPLATES.items()])

    @transaction.atomic
    def post(self, request, company_id):
        company = locked_company(request.user, company_id, 'roles.manage')
        code = request.data.get('code')
        if not isinstance(code, str) or code not in TEMPLATES:
            raise ValidationError('Modèle de rôle inconnu.')
        name, codes = TEMPLATES[code]
        existing = Role.objects.filter(company=company, name=name).first()
        if existing:
            return Response(RoleSerializer(existing).data)
        role = Role.objects.create(company=company, name=name)
        codes = sorted(Permission.objects.filter(code__in=codes).values_list('code', flat=True))
        from .models import RolePermission
        RolePermission.objects.bulk_create([RolePermission(role=role, permission_id=code) for code in codes])
        audit(company, request.user, 'role.created', role, after={'name': name, 'permissions': codes, 'template': code})
        return Response(RoleSerializer(role).data, status=201)


class SaveRoleView(APIView):
    def post(self, request, company_id, role_id=None):
        role = save_role(request.user, company_id, validated(RoleInput, request.data), role_id)
        return Response(RoleSerializer(role).data, status=200 if role_id else 201)


class MemberRolesView(APIView):
    def post(self, request, company_id, member_id):
        member = assign_roles(request.user, company_id, member_id, validated(RoleIds, request.data)['role_ids'])
        return Response(MembershipSerializer(member).data)


class ActivateMemberView(APIView):
    def post(self, request, company_id, member_id):
        return Response(MembershipSerializer(activate_member(request.user, company_id, member_id)).data)


class InvitationsView(APIView):
    def get(self, request, company_id):
        require_membership(request.user, company_id, 'members.manage')
        return Response([invitation_data(item) for item in CompanyInvitation.objects.filter(company_id=company_id).order_by('-created_at').prefetch_related('invitationrole_set')])
    def post(self, request, company_id):
        data = validated(InvitationInput, request.data)
        invitation = create_invitation(request.user, company_id, data['email'], data['role_ids'])
        return Response(invitation_data(invitation), status=201)


class InvitationActionView(APIView):
    def post(self, request, company_id, invitation_id, action):
        if action not in ('resend', 'revoke'):
            raise NotFound()
        return Response(invitation_data(change_invitation(request.user, company_id, invitation_id, action)))


class AcceptInvitationView(APIView):
    def post(self, request):
        class Token(serializers.Serializer):
            token = serializers.CharField(max_length=200)
        data = validated(Token, request.data)
        company = accept_invitation(request.user, data['token'])
        return Response({'company_id': company.id, 'detail': 'Vous avez rejoint l’entreprise.'})


class ModulesView(APIView):
    def get(self, request, company_id):
        require_membership(request.user, company_id, 'modules.view')
        enabled = set(CompanyModule.objects.filter(company_id=company_id, enabled=True).values_list('module_id', flat=True))
        return Response([{'code': module.code, 'name': module.name, 'description': module.description, 'status': module.status, 'enabled': module.id in enabled, 'dependencies': [link.required_module.code for link in module.dependencies.all()]} for module in Module.objects.order_by('code').prefetch_related('dependencies__required_module')])


class ModuleActionView(APIView):
    def post(self, request, company_id, code, action):
        if action not in ('enable', 'disable'):
            raise NotFound()
        set_module(request.user, company_id, code, action == 'enable')
        return Response({'detail': 'Configuration des modules enregistrée.'})


class SettingsView(APIView):
    def get(self, request, company_id):
        member = require_membership(request.user, company_id, 'company.view')
        obj = CompanySettings.objects.get(company_id=company_id)
        from .branding import logo_url
        return Response({'name': member.company.name, 'sector': member.company.sector, 'country_code': member.company.country_code, 'currency_code': member.company.currency_code, 'address': obj.address, 'phone': obj.phone, 'timezone': obj.timezone, 'locale': obj.locale, 'logo_url': logo_url(member.company)})
    @transaction.atomic
    def post(self, request, company_id):
        company = locked_company(request.user, company_id, 'company.manage')
        data = validated(SettingsInput, request.data)
        obj = CompanySettings.objects.get(company=company)
        before = {'name': company.name, 'sector': company.sector, 'address': obj.address, 'phone': obj.phone, 'timezone': obj.timezone, 'locale': obj.locale}
        company.name, company.sector = data.pop('name'), data.pop('sector')
        company.save(update_fields=['name', 'sector'])
        for key, value in data.items():
            setattr(obj, key, value)
        obj.save()
        audit(company, request.user, 'company.settings_updated', company, before, {'name': company.name, 'sector': company.sector, **data})
        return self.get(request, company_id)


class AuditView(APIView):
    def get(self, request, company_id):
        membership = require_membership(request.user, company_id, 'audit.view')
        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except ValueError:
            raise ValidationError('Page invalide.')
        base = AuditLog.objects.filter(company_id=company_id)
        query = base.select_related('actor').order_by('-created_at', '-id')
        search = request.query_params.get('search', '').strip()[:100]
        actions = list(base.values_list('action', 'entity_type').distinct())
        if search:
            matches = [code for code, entity in actions if search.casefold() in action_label(code, entity).casefold()]
            query = query.filter(Q(action__icontains=search) | Q(action__in=matches) | Q(actor__full_name__icontains=search) | Q(before_data__icontains=search) | Q(after_data__icontains=search))
        module = request.query_params.get('module', '')
        if module:
            query = query.filter(action__in=[code for code, _ in actions if module_for(code) == module])
        actor = request.query_params.get('actor', '')
        if actor:
            try: actor = UUID(actor)
            except ValueError: raise ValidationError('Auteur invalide.')
            query = query.filter(actor_id=actor)
        try:
            start = date.fromisoformat(request.query_params['start']) if request.query_params.get('start') else None
            end = date.fromisoformat(request.query_params['end']) if request.query_params.get('end') else None
            if start and end and start > end: raise ValueError()
            if start: query = query.filter(created_at__date__gte=start)
            if end: query = query.filter(created_at__date__lte=end)
        except ValueError:
            raise ValidationError('Période invalide.')
        permission_names = dict(Permission.objects.values_list('code', 'description'))
        role_names = {str(key): name for key, name in Role.objects.filter(company_id=company_id).values_list('id', 'name')}
        from .models import Membership
        member_names = {str(key): name for key, name in Membership.objects.filter(company_id=company_id).values_list('id', 'user__full_name')}
        response = Response({'count': query.count(), 'results': [{'id': item.id, 'action': item.action, 'entity_type': item.entity_type, 'entity_id': item.entity_id, 'actor': item.actor.full_name, 'actor_id': item.actor_id, 'company_name': membership.company.name, 'before_data': item.before_data, 'after_data': item.after_data, 'created_at': item.created_at, **present(item, permission_names, role_names, member_names)} for item in query[(page - 1) * 25:page * 25]],
            'filters': {'actors': list(base.order_by('actor__full_name').values('actor_id', 'actor__full_name').distinct()), 'modules': [{'code': code, 'name': module_label(code)} for code in sorted({module_for(action) for action, _ in actions})]}})
        response['Cache-Control'] = 'private, no-store'
        return response


class SequencesView(APIView):
    def get(self, request, company_id):
        membership = require_membership(request.user, company_id, 'sequences.view')
        from .services import permissions_for
        can_manage = 'company.manage' in permissions_for(membership)
        rows = []
        for row in DocumentSequence.objects.filter(company_id=company_id).order_by('document_type').values('document_type', 'prefix', 'next_number'):
            code, label, description = SEQUENCE_INFO.get(row['document_type'], ('core', 'Autre document', 'Séquence complémentaire.'))
            rows.append({**row, 'module_code': code, 'module_name': module_label(code), 'label': label, 'description': description, 'preview': f"{row['prefix']}{row['next_number']:06d}", 'can_edit': can_manage and row['next_number'] == 1 and row['document_type'] in SEQUENCE_INFO})
        return Response(rows)


class SequenceUpdateView(APIView):
    @transaction.atomic
    def post(self, request, company_id, document_type):
        require_membership(request.user, company_id, 'sequences.view')
        company = locked_company(request.user, company_id, 'company.manage')
        class Input(serializers.Serializer):
            prefix = serializers.RegexField(r'^[A-Z0-9-]{1,20}$', max_length=20)
        data = validated(Input, request.data)
        if set(request.data) != {'prefix'}:
            raise ValidationError('Seul le préfixe est configurable ; le compteur est protégé.')
        sequence = DocumentSequence.objects.select_for_update().filter(company=company, document_type=document_type).first()
        if not sequence or document_type not in SEQUENCE_INFO:
            raise NotFound()
        if sequence.next_number != 1:
            raise ValidationError('Le préfixe est protégé après la première émission de document.')
        if sequence.prefix != data['prefix']:
            before = {'prefix': sequence.prefix}
            sequence.prefix = data['prefix']
            sequence.save(update_fields=['prefix'])
            audit(company, request.user, 'sequences.updated', sequence, before, {'prefix': sequence.prefix, 'name': SEQUENCE_INFO[document_type][1]})
        return Response({'prefix': sequence.prefix, 'preview': f'{sequence.prefix}{sequence.next_number:06d}'})
