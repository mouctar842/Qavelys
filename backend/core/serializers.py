from rest_framework import serializers
from .models import Company, Membership, Role


class CompanySerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()
    def get_logo_url(self, obj):
        from .branding import logo_url
        return logo_url(obj)
    class Meta:
        model = Company
        fields = ['id', 'name', 'slug', 'country_code', 'currency_code', 'sector', 'status', 'logo_url']
        read_only_fields = ['id', 'slug', 'status']
    country_code = serializers.RegexField(r'^[A-Z]{2}$')
    currency_code = serializers.RegexField(r'^[A-Z]{3}$')


class MembershipSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='user.full_name')
    email = serializers.EmailField(source='user.email')
    roles = serializers.SerializerMethodField()
    def get_roles(self, obj):
        return [{'id': link.role_id, 'name': link.role.name, 'is_system': link.role.is_system} for link in obj.membershiprole_set.all()]
    class Meta:
        model = Membership
        fields = ['id', 'full_name', 'email', 'status', 'joined_at', 'roles']


class RoleSerializer(serializers.ModelSerializer):
    permission_codes = serializers.SerializerMethodField()
    def get_permission_codes(self, obj):
        return sorted(link.permission_id for link in obj.rolepermission_set.all())
    class Meta:
        model = Role
        fields = ['id', 'name', 'is_system', 'permission_codes']
