import hashlib
import io
import uuid
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import FileResponse
from django.utils.cache import patch_vary_headers
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from .administration import audit, locked_company
from .models import CompanyLogo, CompanySettings
from .services import require_membership

MAX_BYTES = 2 * 1024 * 1024


def logo_url(company):
    try:
        logo_id = company.companysettings.logo_id
    except CompanySettings.DoesNotExist:
        return None
    return f'/api/v1/companies/{company.id}/logo/{logo_id}/' if logo_id else None


def normalize_logo(upload):
    if upload is None or upload.size > MAX_BYTES:
        raise ValidationError({'logo': 'Choisissez une image de 2 Mio maximum.'})
    raw = upload.read(MAX_BYTES + 1)
    if not raw or len(raw) > MAX_BYTES:
        raise ValidationError({'logo': 'Image vide ou trop volumineuse.'})
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in ('PNG', 'JPEG', 'WEBP') or getattr(source, 'n_frames', 1) != 1:
                    raise ValueError()
                if not (1 <= source.width <= 4096 and 1 <= source.height <= 4096):
                    raise ValueError()
                source.load()
                pixels = ImageOps.exif_transpose(source).convert('RGBA')
                pixels.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
                clean = Image.new('RGBA', pixels.size)
                clean.paste(pixels)
                result = io.BytesIO()
                clean.save(result, format='PNG')
                data = result.getvalue()
                if len(data) > MAX_BYTES:
                    raise ValueError()
                return data, clean.width, clean.height
    except (OSError, UnidentifiedImageError, ValueError, Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise ValidationError({'logo': 'Image invalide. PNG, JPEG ou WebP fixe, 4096 × 4096 pixels maximum.'})


class LogoUpload(APIView):
    parser_classes = [MultiPartParser]

    @transaction.atomic
    def post(self, request, company_id):
        company = locked_company(request.user, company_id, 'company.manage')
        if set(request.data.keys()) != {'logo'} or len(request.FILES.getlist('logo')) != 1:
            raise ValidationError({'logo': 'Envoyez un seul fichier dans le champ logo.'})
        data, width, height = normalize_logo(request.FILES.get('logo'))
        obj = CompanySettings.objects.select_for_update().get(company=company)
        old_id = str(obj.logo_id) if obj.logo_id else None
        asset = CompanyLogo(company=company, uploaded_by=request.user, sha256=hashlib.sha256(data).hexdigest(), byte_size=len(data), width=width, height=height)
        try:
            asset.file.save(f'companies/{company.id}/logos/{uuid.uuid4().hex}.png', ContentFile(data), save=False)
        except OSError:
            error = APIException('Le stockage du logo est indisponible. Réessayez.')
            error.status_code = 503
            raise error
        asset.save()
        obj.logo = asset
        obj.save(update_fields=['logo'])
        # Actualiser la relation en mémoire avant de calculer l’URL.
        company.companysettings = obj
        audit(company, request.user, 'company.logo_uploaded', company, {'logo_id': old_id}, {'logo_id': str(asset.id), 'sha256': asset.sha256})
        return Response({'logo_url': logo_url(company)}, status=201)


class LogoContent(APIView):
    def get(self, request, company_id, logo_id):
        require_membership(request.user, company_id, 'company.view')
        asset = CompanyLogo.objects.filter(id=logo_id, company_id=company_id, company__companysettings__logo_id=logo_id).first()
        if asset is None:
            raise NotFound()
        try:
            file = asset.file.open('rb')
        except OSError:
            raise NotFound('Logo indisponible.')
        response = FileResponse(file, content_type='image/png')
        response['Cache-Control'] = 'private, no-store'
        response['Content-Security-Policy'] = "default-src 'none'; sandbox"
        response['X-Content-Type-Options'] = 'nosniff'
        response['Cross-Origin-Resource-Policy'] = 'same-origin'
        patch_vary_headers(response, ['Cookie'])
        return response
