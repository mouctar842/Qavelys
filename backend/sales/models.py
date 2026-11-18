from django.db import models
from core.order_models import OrderBase, OrderLineBase


class SalesOrder(OrderBase):
    lead = models.ForeignKey('crm.Lead', null=True, blank=True, on_delete=models.PROTECT)


class SalesOrderLine(OrderLineBase):
    order = models.ForeignKey(SalesOrder, related_name='lines', on_delete=models.PROTECT)
