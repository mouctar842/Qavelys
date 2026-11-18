from django.db import DatabaseError, connection
from django.db.migrations.executor import MigrationExecutor
from django.http import JsonResponse
from django.views.decorators.http import require_GET


def ready():
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            if cursor.fetchone() != (1,):
                return False
        executor = MigrationExecutor(connection)
        return not executor.migration_plan(executor.loader.graph.leaf_nodes())
    except Exception:
        return False


def result(healthy):
    response = JsonResponse({'status': 'ok' if healthy else 'unavailable'}, status=200 if healthy else 503)
    response['Cache-Control'] = 'no-store'
    return response


@require_GET
def live(request):
    return result(True)


@require_GET
def readiness(request):
    return result(ready())
