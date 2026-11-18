from decimal import Decimal
from django.conf import settings
from django.db import models
from core.models import Company, UUIDModel


class CompanyEntity(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True


class Partner(CompanyEntity):
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.TextField(blank=True)
    customer_reference = models.CharField(max_length=80, blank=True, db_default='')
    supplier_reference = models.CharField(max_length=80, blank=True, db_default='')
    delivery_address = models.TextField(blank=True, db_default='')
    customer_notes = models.TextField(blank=True, db_default='')
    supplier_notes = models.TextField(blank=True, db_default='')
    is_customer = models.BooleanField(default=True)
    is_supplier = models.BooleanField(default=False)
    status = models.CharField(max_length=20, default='active', choices=[('active', 'Actif'), ('archived', 'Archivé')])
    class Meta:
        constraints = [models.UniqueConstraint(fields=['id', 'company'], name='partner_id_company_unique'), models.CheckConstraint(condition=models.Q(is_customer=True) | models.Q(is_supplier=True), name='partner_customer_or_supplier')]
        indexes = [models.Index(fields=['company', 'status', 'name'])]


class ProductCategory(CompanyEntity):
    name = models.CharField(max_length=100)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['id', 'company'], name='category_id_company_unique'), models.UniqueConstraint(fields=['company', 'name'], name='category_company_name_unique')]


class UnitOfMeasure(UUIDModel):
    name = models.CharField(max_length=80)
    symbol = models.CharField(max_length=20, unique=True)
    category = models.CharField(max_length=40)


class Tax(CompanyEntity):
    name = models.CharField(max_length=100)
    rate = models.DecimalField(max_digits=9, decimal_places=4)
    active = models.BooleanField(default=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['id', 'company'], name='tax_id_company_unique'), models.UniqueConstraint(fields=['company', 'name'], name='tax_company_name_unique'), models.CheckConstraint(condition=models.Q(rate__gte=0, rate__lte=100), name='tax_rate_percentage')]


class Product(CompanyEntity):
    sku = models.CharField(max_length=80)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    type = models.CharField(max_length=20, choices=[('stockable', 'Stockable'), ('consumable', 'Consommable'), ('service', 'Service')])
    category = models.ForeignKey(ProductCategory, null=True, blank=True, on_delete=models.PROTECT)
    unit = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT)
    sale_price = models.DecimalField(max_digits=20, decimal_places=6, default=Decimal('0'))
    cost_price = models.DecimalField(max_digits=20, decimal_places=6, default=Decimal('0'))
    active = models.BooleanField(default=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['id', 'company'], name='product_id_company_unique'), models.UniqueConstraint(fields=['company', 'sku'], name='product_company_sku_unique'), models.CheckConstraint(condition=models.Q(sale_price__gte=0, cost_price__gte=0), name='product_nonnegative_prices')]
        indexes = [models.Index(fields=['company', 'active', 'name'])]


class ProductTax(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    tax = models.ForeignKey(Tax, on_delete=models.PROTECT)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['product', 'tax'], name='product_tax_unique')]


class ProductPriceHistory(CompanyEntity):
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    old_sale_price = models.DecimalField(max_digits=20, decimal_places=6)
    new_sale_price = models.DecimalField(max_digits=20, decimal_places=6)
    old_cost_price = models.DecimalField(max_digits=20, decimal_places=6)
    new_cost_price = models.DecimalField(max_digits=20, decimal_places=6)
    class Meta:
        indexes = [models.Index(fields=['company', 'product', 'created_at'])]
