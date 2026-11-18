"""Créer uniquement une nouvelle base PostgreSQL locale de test, sans suppression."""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
import psycopg
from PIL import Image
from psycopg import sql

root = Path(__file__).resolve().parent.parent
database = os.environ.get('POSTGRES_DB', '')
run_id = os.environ.get('QAVELYS_E2E_RUN_ID', '')
if os.environ.get('QAVELYS_E2E') != '1' or not re.fullmatch(r'qavelys_e2e_[a-z0-9_]{1,45}', database): raise SystemExit('Base E2E dédiée obligatoire.')
if not re.fullmatch(r'[a-zA-Z0-9_-]+', run_id): raise SystemExit('Identifiant E2E invalide.')
host = os.environ.get('POSTGRES_HOST', 'localhost')
if host not in ['localhost', '127.0.0.1', '::1']: raise SystemExit('Seul PostgreSQL local est autorisé pour ce lanceur E2E.')
output = root / '.local' / 'e2e-runs' / run_id
output.mkdir(parents=True, exist_ok=False)
with psycopg.connect(dbname='postgres', user=os.environ['POSTGRES_USER'], password=os.environ['POSTGRES_PASSWORD'], host=host, port=os.environ.get('POSTGRES_PORT', '5432'), autocommit=True) as connection:
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1 FROM pg_database WHERE datname=%s', [database])
        if cursor.fetchone(): raise SystemExit('La base existe déjà : refus de la réutiliser ou de la supprimer.')
        cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
(output / 'run.json').write_text(json.dumps({'run_id': run_id, 'database': database, 'created_at': datetime.now(timezone.utc).isoformat(), 'frontend_port': os.environ['QAVELYS_E2E_FRONTEND_PORT'], 'backend_port': os.environ['QAVELYS_E2E_BACKEND_PORT'], 'retained': True}, indent=2), encoding='utf-8')
print(f'Base E2E créée et conservée : {database}')
Image.new('RGBA', (96, 64), (109, 93, 245, 255)).save(output / 'logo-input.png')
