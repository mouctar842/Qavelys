from rest_framework.exceptions import ValidationError
from rest_framework.response import Response


def paginate(request, query, serializer):
    try:
        page = max(1, int(request.query_params.get('page', 1)))
        size = min(100, max(1, int(request.query_params.get('page_size', 25))))
    except ValueError:
        raise ValidationError('Pagination invalide.')
    return Response({'count': query.count(), 'page': page, 'page_size': size, 'results': serializer(query[(page - 1) * size:page * size], many=True).data})
