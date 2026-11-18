from decimal import Decimal
from rest_framework import serializers
from .models import Warehouse, StockLocation, StockBalance, StockTransfer, StockAdjustment, StockAdjustmentLine, StockMovement


def location_label(location):
    return f'{location.warehouse.code} / {location.name}' if location.warehouse_id else location.name


class WarehouseSerializer(serializers.ModelSerializer):
    code = serializers.RegexField(r'^[A-Z0-9_-]{1,30}$')
    class Meta:
        model = Warehouse
        fields = ['id', 'name', 'code', 'active']
        read_only_fields = ['id', 'active']
        validators = []


class LocationSerializer(serializers.ModelSerializer):
    warehouse_id = serializers.UUIDField()
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True, allow_null=True)
    class Meta:
        model = StockLocation
        fields = ['id', 'name', 'type', 'warehouse_id', 'warehouse_name', 'active']
        read_only_fields = ['id', 'type', 'active']
        validators = []


class BalanceSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name')
    sku = serializers.CharField(source='product.sku')
    location_name = serializers.CharField(source='location.name')
    warehouse_name = serializers.CharField(source='location.warehouse.name')
    available_quantity = serializers.SerializerMethodField()
    def get_available_quantity(self, obj): return format(obj.quantity - obj.reserved_quantity, '.6f')
    class Meta:
        model = StockBalance
        fields = ['id', 'product_id', 'product_name', 'sku', 'location_id', 'location_name', 'warehouse_name', 'quantity', 'reserved_quantity', 'available_quantity']


class TransferSerializer(serializers.ModelSerializer):
    product_id = serializers.UUIDField()
    source_location_id = serializers.UUIDField()
    destination_location_id = serializers.UUIDField()
    product_name = serializers.CharField(source='product.name', read_only=True)
    source_name = serializers.SerializerMethodField()
    destination_name = serializers.SerializerMethodField()
    def get_source_name(self, obj): return location_label(obj.source_location)
    def get_destination_name(self, obj): return location_label(obj.destination_location)
    quantity = serializers.DecimalField(max_digits=20, decimal_places=6, min_value=Decimal('0.000001'))
    class Meta:
        model = StockTransfer
        fields = ['id', 'reference', 'request_key', 'status', 'product_id', 'product_name', 'source_location_id', 'source_name', 'destination_location_id', 'destination_name', 'quantity', 'validated_at', 'created_at']
        read_only_fields = ['id', 'reference', 'status', 'validated_at', 'created_at']
        validators = []


class AdjustmentLineSerializer(serializers.ModelSerializer):
    product_id = serializers.UUIDField()
    product_name = serializers.CharField(source='product.name', read_only=True)
    counted_quantity = serializers.DecimalField(max_digits=20, decimal_places=6, min_value=Decimal(0))
    class Meta:
        model = StockAdjustmentLine
        fields = ['id', 'product_id', 'product_name', 'counted_quantity', 'difference']
        read_only_fields = ['id', 'difference']
        validators = []


class AdjustmentSerializer(serializers.ModelSerializer):
    location_id = serializers.UUIDField()
    location_name = serializers.CharField(source='location.name', read_only=True)
    lines = AdjustmentLineSerializer(many=True, allow_empty=False)
    class Meta:
        model = StockAdjustment
        fields = ['id', 'reference', 'request_key', 'status', 'location_id', 'location_name', 'reason', 'lines', 'validated_at', 'created_at']
        read_only_fields = ['id', 'reference', 'status', 'validated_at', 'created_at']
        validators = []


class MovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name')
    source_name = serializers.SerializerMethodField()
    destination_name = serializers.SerializerMethodField()
    def get_source_name(self, obj): return location_label(obj.source_location)
    def get_destination_name(self, obj): return location_label(obj.destination_location)
    reference = serializers.SerializerMethodField()
    def get_reference(self, obj):
        if obj.transfer_id: return obj.transfer.reference
        if obj.adjustment_line_id: return obj.adjustment_line.adjustment.reference
        if obj.delivery_line_id: return obj.delivery_line.document.reference
        return obj.receipt_line.document.reference
    class Meta:
        model = StockMovement
        fields = ['id', 'product_id', 'product_name', 'source_name', 'destination_name', 'quantity', 'validated_at', 'transfer_id', 'adjustment_line_id', 'delivery_line_id', 'receipt_line_id', 'reference']
