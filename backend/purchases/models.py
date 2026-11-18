from django.db import models
from core.order_models import OrderBase, OrderLineBase


class PurchaseOrder(OrderBase):
    pass


class PurchaseOrderLine(OrderLineBase):
    order = models.ForeignKey(PurchaseOrder, related_name='lines', on_delete=models.PROTECT)
