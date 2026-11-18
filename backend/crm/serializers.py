from decimal import Decimal
from rest_framework import serializers
from .models import CRMActivity, Lead


class LeadSerializer(serializers.ModelSerializer):
    partner_id = serializers.UUIDField(required=False, allow_null=True)
    owner_id = serializers.UUIDField(required=False)
    partner_name = serializers.CharField(source='partner.name', read_only=True, allow_null=True)
    partner_is_customer = serializers.BooleanField(source='partner.is_customer', read_only=True, allow_null=True)
    owner_name = serializers.CharField(source='owner.user.full_name', read_only=True)
    expected_revenue = serializers.DecimalField(max_digits=20, decimal_places=6, min_value=Decimal(0), required=False)
    probability = serializers.IntegerField(min_value=0, max_value=100, required=False)
    class Meta:
        model = Lead
        fields = ['id', 'title', 'stage', 'partner_id', 'partner_name', 'partner_is_customer', 'owner_id', 'owner_name', 'expected_revenue', 'probability', 'created_at', 'updated_at']
        read_only_fields = ['id', 'stage', 'created_at', 'updated_at']


class ActivitySerializer(serializers.ModelSerializer):
    lead_id = serializers.UUIDField()
    assigned_to_id = serializers.UUIDField(required=False)
    assigned_to_name = serializers.CharField(source='assigned_to.user.full_name', read_only=True)
    lead_title = serializers.CharField(source='lead.title', read_only=True)
    class Meta:
        model = CRMActivity
        fields = ['id', 'lead_id', 'lead_title', 'assigned_to_id', 'assigned_to_name', 'type', 'due_at', 'status', 'description', 'created_at', 'updated_at']
        read_only_fields = ['id', 'status', 'created_at', 'updated_at']
