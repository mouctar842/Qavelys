from django.db import models
from core.models import Membership
from reference.models import CompanyEntity, Partner

STAGES = [('new', 'Nouveau'), ('qualified', 'Qualifié'), ('proposal', 'Proposition'), ('won', 'Gagné'), ('lost', 'Perdu')]


class Lead(CompanyEntity):
    partner = models.ForeignKey(Partner, null=True, blank=True, on_delete=models.PROTECT)
    title = models.CharField(max_length=200)
    stage = models.CharField(max_length=20, choices=STAGES, default='new')
    owner = models.ForeignKey(Membership, on_delete=models.PROTECT)
    expected_revenue = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    probability = models.PositiveSmallIntegerField(default=0)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['id', 'company'], name='lead_id_company_unique'), models.CheckConstraint(condition=models.Q(expected_revenue__gte=0, probability__gte=0, probability__lte=100), name='lead_revenue_probability_valid')]
        indexes = [models.Index(fields=['company', 'stage', 'created_at']), models.Index(fields=['company', 'owner'])]


class CRMActivity(CompanyEntity):
    lead = models.ForeignKey(Lead, on_delete=models.PROTECT)
    assigned_to = models.ForeignKey(Membership, on_delete=models.PROTECT)
    type = models.CharField(max_length=20, choices=[('call', 'Appel'), ('email', 'E-mail'), ('meeting', 'Rendez-vous'), ('task', 'Tâche')])
    due_at = models.DateTimeField()
    status = models.CharField(max_length=20, default='planned', choices=[('planned', 'Planifiée'), ('done', 'Terminée'), ('cancelled', 'Annulée')])
    description = models.TextField()
    class Meta:
        constraints = [models.UniqueConstraint(fields=['id', 'company'], name='crm_activity_id_company_uq')]
        indexes = [models.Index(fields=['company', 'status', 'due_at']), models.Index(fields=['company', 'lead'])]
