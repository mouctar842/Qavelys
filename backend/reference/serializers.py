from decimal import Decimal
from rest_framework import serializers
from .models import Partner, Product, ProductCategory, Tax, UnitOfMeasure


class PartnerSerializer(serializers.ModelSerializer):
    delivery_address = serializers.CharField(max_length=2000, allow_blank=True, required=False)
    customer_notes = serializers.CharField(max_length=2000, allow_blank=True, required=False)
    supplier_notes = serializers.CharField(max_length=2000, allow_blank=True, required=False)
    class Meta:
        model = Partner
        fields = ['id', 'name', 'email', 'phone', 'address', 'customer_reference', 'supplier_reference', 'delivery_address', 'customer_notes', 'supplier_notes', 'is_customer', 'is_supplier', 'status', 'created_at', 'updated_at']
        read_only_fields = ['id', 'status', 'created_at', 'updated_at']
    def validate(self, data):
        customer = data.get('is_customer', getattr(self.instance, 'is_customer', True))
        supplier = data.get('is_supplier', getattr(self.instance, 'is_supplier', False))
        if not customer and not supplier:
            raise serializers.ValidationError('Un contact doit être client, fournisseur ou les deux.')
        return data


class CategorySerializer(serializers.ModelSerializer):
    parent_id = serializers.UUIDField(required=False, allow_null=True)
    class Meta:
        model = ProductCategory
        fields = ['id', 'name', 'parent_id']
        read_only_fields = ['id']
        validators = []


class TaxSerializer(serializers.ModelSerializer):
    rate = serializers.DecimalField(max_digits=9, decimal_places=4, min_value=Decimal('0'), max_value=Decimal('100'))
    class Meta:
        model = Tax
        fields = ['id', 'name', 'rate', 'active']
        read_only_fields = ['id', 'active']
        validators = []


class UnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnitOfMeasure
        fields = ['id', 'name', 'symbol', 'category']


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True, allow_null=True)
    unit_name = serializers.CharField(source='unit.name', read_only=True)
    category_id = serializers.UUIDField(required=False, allow_null=True)
    unit_id = serializers.UUIDField()
    tax_ids = serializers.ListField(child=serializers.UUIDField(), required=False, write_only=True)
    taxes = serializers.SerializerMethodField()
    sale_price = serializers.DecimalField(max_digits=20, decimal_places=6, min_value=Decimal('0'))
    cost_price = serializers.DecimalField(max_digits=20, decimal_places=6, min_value=Decimal('0'))
    class Meta:
        model = Product
        fields = ['id', 'sku', 'name', 'description', 'type', 'category_id', 'category_name', 'unit_id', 'unit_name', 'sale_price', 'cost_price', 'active', 'tax_ids', 'taxes', 'created_at', 'updated_at']
        read_only_fields = ['id', 'active', 'created_at', 'updated_at']
        validators = []
    def validate_sku(self, value):
        return value.strip().upper()
    def get_taxes(self, obj):
        return [{'id': link.tax_id, 'name': link.tax.name, 'rate': str(link.tax.rate), 'active': link.tax.active} for link in obj.producttax_set.all()]
