from decimal import Decimal
from rest_framework import serializers


class ExactDecimalField(serializers.DecimalField):
    def to_internal_value(self, data):
        if isinstance(data, (float, bool)):
            raise serializers.ValidationError('Transmettre une chaîne décimale exacte, jamais un float.')
        return super().to_internal_value(data)


class OrderLineInput(serializers.Serializer):
    product_id = serializers.UUIDField()
    description = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    quantity = ExactDecimalField(max_digits=20, decimal_places=6, min_value=Decimal('0.000001'))
    unit_price = ExactDecimalField(max_digits=20, decimal_places=6, min_value=Decimal(0), required=False)
    discount_rate = ExactDecimalField(max_digits=9, decimal_places=4, min_value=Decimal(0), max_value=Decimal(100), default=Decimal(0))
    tax_rate = ExactDecimalField(max_digits=9, decimal_places=4, min_value=Decimal(0), max_value=Decimal(100), required=False)


class OrderInput(serializers.Serializer):
    request_key = serializers.UUIDField(required=False)
    version = serializers.IntegerField(min_value=1, required=False)
    partner_id = serializers.UUIDField()
    warehouse_id = serializers.UUIDField()
    lead_id = serializers.UUIDField(allow_null=True, required=False)
    order_date = serializers.DateField()
    notes = serializers.CharField(allow_blank=True, max_length=10000, default='')
    lines = OrderLineInput(many=True, allow_empty=False, max_length=200)


class VersionInput(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)


def line_data(line):
    return {field: str(getattr(line, field)) if isinstance(getattr(line, field), Decimal) else getattr(line, field) for field in ['id', 'position', 'product_id', 'product_name', 'product_type', 'unit_name', 'description', 'quantity', 'unit_price', 'discount_rate', 'tax_rate', 'line_total', 'line_tax']}
