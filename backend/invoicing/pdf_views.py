from django.http import HttpResponse
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.views import APIView
from core.services import require_membership
from .services import access
from .views import rows
from .pdf import financial_pdf


class FinancialPdf(APIView):
    def get(self, request, company_id, kind, pk):
        access(request.user, company_id, kind)
        require_membership(request.user, company_id, 'invoicing.document.export')
        obj = rows(company_id, kind).filter(pk=pk).first()
        if obj is None: raise NotFound()
        if obj.status != 'validated': raise ValidationError('Seul un document validé peut être exporté.')
        response = HttpResponse(financial_pdf(obj, kind), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{obj.reference}.pdf"'
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response
