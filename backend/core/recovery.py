"""Sauvegardes opérateur privées et restaurations uniquement dans une nouvelle cible."""
import csv
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import uuid
import zipfile
from datetime import datetime, timezone
import psycopg
from psycopg import sql
from django.conf import settings
from django.core.management.base import CommandError


ROOT = settings.BASE_DIR.parent


def identifier():
    return datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S') + '_' + uuid.uuid4().hex[:8]


def private_directory(path):
    path.mkdir(parents=True, exist_ok=False, mode=0o700)
    if os.name == 'nt':
        identity = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'], capture_output=True, check=True, text=True)
        sid = next(csv.reader(identity.stdout.strip().splitlines()))[-1]
        if not re.fullmatch(r'S-1-[0-9-]+', sid): raise CommandError('Identité Windows indéterminée.')
        result = subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r', f'*{sid}:(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'], capture_output=True)
        if result.returncode: raise CommandError('Impossible de protéger le dossier de sauvegarde.')
    return path


def config():
    db = settings.DATABASES['default']
    if db['ENGINE'] != 'django.db.backends.postgresql': raise CommandError('PostgreSQL obligatoire.')
    return {'host': '127.0.0.1' if db['HOST'] == 'localhost' else db['HOST'], 'port': str(db.get('PORT') or '5432'), 'user': db['USER'], 'password': db['PASSWORD'], 'dbname': db['NAME'], 'connect_timeout': 5}


def tool(name):
    local = settings.BASE_DIR.parent / '.local' / 'postgres' / 'pgsql' / 'bin' / (name + '.exe')
    found = str(local) if os.name == 'nt' and local.is_file() else shutil.which(name)
    if not found: raise CommandError(f'Outil PostgreSQL manquant : {name}.')
    return found


def run_tool(name, cfg, database, arguments, folder):
    environment = os.environ.copy()
    environment.update(PGPASSWORD=cfg['password'], PGCLIENTENCODING='UTF8', PGCONNECT_TIMEOUT='5')
    command = [tool(name), '--host', cfg['host'], '--port', cfg['port'], '--username', cfg['user'], '--no-password', '--dbname', database, *arguments]
    with (folder / f'{name}.log').open('wb') as log:
        result = subprocess.run(command, env=environment, stdout=log, stderr=log, timeout=1800)
    if result.returncode: raise CommandError(f'{name} a échoué. Consulter le journal privé dans le dossier opérateur.')


def digest_stream(stream):
    total = 0; digest = hashlib.sha256()
    while block := stream.read(1024 * 1024): digest.update(block); total += len(block)
    return {'sha256': digest.hexdigest(), 'size': total}


def digest_file(path):
    with path.open('rb') as file: return digest_stream(file)


def safe_media_name(name):
    path = PurePosixPath(name)
    if not name or path.is_absolute() or '\\' in name or ':' in name or any(part in ('', '.', '..') for part in name.split('/')):
        raise CommandError('Chemin média non autorisé.')
    reserved = {'CON', 'PRN', 'AUX', 'NUL', *[f'COM{i}' for i in range(1, 10)], *[f'LPT{i}' for i in range(1, 10)]}
    if any(part.rstrip(' .') != part or part.split('.')[0].upper() in reserved for part in path.parts): raise CommandError('Chemin média non portable.')
    return path


def database_facts(conn):
    conn.execute("SET LOCAL TIME ZONE 'UTC'")
    tables = {}; sequences = {}
    with conn.cursor() as cursor:
        cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
        names = [row[0] for row in cursor.fetchall()]
    for name in names:
        count = 0; digest = hashlib.sha256()
        with conn.cursor(name='backup_' + uuid.uuid4().hex) as cursor:
            cursor.execute(sql.SQL('SELECT to_jsonb(t)::text FROM {} t ORDER BY to_jsonb(t)::text COLLATE "C"').format(sql.Identifier('public', name)))
            for row in cursor:
                payload = row[0].encode('utf-8'); digest.update(len(payload).to_bytes(8, 'big')); digest.update(payload); count += 1
        tables[name] = {'rows': count, 'sha256': digest.hexdigest()}
    with conn.cursor() as cursor:
        cursor.execute("SELECT sequencename FROM pg_sequences WHERE schemaname='public' ORDER BY sequencename")
        names = [row[0] for row in cursor.fetchall()]
        for name in names:
            cursor.execute(sql.SQL('SELECT last_value, is_called FROM {}').format(sql.Identifier('public', name)))
            sequences[name] = list(cursor.fetchone())
    return {'tables': tables, 'sequences': sequences}


def verify_sequence_positions(conn):
    # Les séquences ne sont pas MVCC : leur valeur peut avancer pendant pg_dump.
    # Vérifier qu’aucune clé restaurée ne dépasse le prochain compteur utilisable.
    rows = conn.execute("SELECT c.relname, a.attname, pg_get_serial_sequence(format('%I.%I', n.nspname, c.relname), a.attname) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_attribute a ON a.attrelid=c.oid WHERE n.nspname='public' AND c.relkind='r' AND a.attnum>0 AND NOT a.attisdropped AND a.atttypid IN ('int4'::regtype,'int8'::regtype)").fetchall()
    for table, column, sequence in rows:
        if not sequence: continue
        value, called = conn.execute(sql.SQL('SELECT last_value, is_called FROM {}').format(sql.Identifier(*sequence.split('.')))).fetchone()
        maximum = conn.execute(sql.SQL('SELECT max({}) FROM {}').format(sql.Identifier(column), sql.Identifier('public', table))).fetchone()[0]
        if maximum is not None and (value < maximum or (value == maximum and not called)): raise CommandError('Une séquence restaurée précède les clés existantes.')


def database_locale(conn):
    with conn.cursor() as cursor:
        cursor.execute("SELECT pg_encoding_to_char(encoding), datcollate, datctype, datlocprovider, COALESCE(to_jsonb(d)->>'datlocale', to_jsonb(d)->>'daticulocale'), to_jsonb(d)->>'daticurules' FROM pg_database d WHERE datname=current_database()")
        keys = ['encoding', 'collate', 'ctype', 'provider', 'locale', 'rules']
        return dict(zip(keys, cursor.fetchone()))


def referenced_media(conn):
    with conn.cursor() as cursor:
        cursor.execute('SELECT file, sha256, byte_size FROM core_companylogo ORDER BY file')
        return {name: {'sha256': sha, 'size': size} for name, sha, size in cursor.fetchall()}


def backup():
    cfg = config(); folder = private_directory(ROOT / '.local' / 'backups' / identifier())
    # Le dump et les empreintes utilisent exactement le même snapshot PostgreSQL.
    with psycopg.connect(**cfg) as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        snapshot = conn.execute('SELECT pg_export_snapshot()').fetchone()[0]
        locale = database_locale(conn)
        run_tool('pg_dump', cfg, cfg['dbname'], ['--format=custom', '--no-owner', '--no-acl', '--no-tablespaces', '--lock-wait-timeout=10000', '--snapshot', snapshot, '--file', str(folder / 'database.dump')], folder)
        facts = database_facts(conn)
        references = referenced_media(conn)
    files = {}; root = Path(settings.MEDIA_ROOT)
    if root.is_symlink(): raise CommandError('Le stockage média ne doit pas être un lien symbolique.')
    with zipfile.ZipFile(folder / 'media.zip', 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(root.rglob('*')) if root.exists() else []:
            if file.is_symlink(): raise CommandError('Lien symbolique refusé dans les médias.')
            if not file.is_file(): continue
            name = file.relative_to(root).as_posix(); safe_media_name(name)
            archive.write(file, name)
            files[name] = digest_file(file)
    for name, expected in references.items():
        if files.get(name) != expected: raise CommandError('Un média référencé est absent ou altéré. Sauvegarde non validée.')
    manifest = {'format': 1, 'created_at': datetime.now(timezone.utc).isoformat(), 'source_database': cfg['dbname'], 'locale': locale, 'database': digest_file(folder / 'database.dump'), 'media_archive': digest_file(folder / 'media.zip'), 'media_files': files, 'referenced_media': references, 'facts': facts}
    (folder / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    validate_bundle(folder)
    return folder


def validate_bundle(folder):
    folder = Path(folder).resolve()
    allowed = (ROOT / '.local' / 'backups').resolve()
    if not folder.is_relative_to(allowed) or folder == allowed: raise CommandError('Choisir un dossier de sauvegarde local sous .local/backups.')
    if (folder / 'manifest.json').is_symlink(): raise CommandError('Manifeste non autorisé.')
    try:
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        if manifest['format'] != 1: raise ValueError()
        for name, key in [('database.dump', 'database'), ('media.zip', 'media_archive')]:
            file = folder / name
            if file.is_symlink() or digest_file(file) != manifest[key]: raise ValueError()
        with zipfile.ZipFile(folder / 'media.zip') as archive:
            names = archive.namelist()
            if len(names) != len(set(name.casefold() for name in names)) or set(names) != set(manifest['media_files']): raise ValueError()
            for info in archive.infolist():
                safe_media_name(info.filename)
                expected = manifest['media_files'][info.filename]
                if info.file_size != expected['size'] or info.external_attr >> 16 & 0o170000 == 0o120000: raise ValueError()
                with archive.open(info) as file:
                    if digest_stream(file) != expected: raise ValueError()
        for name, expected in manifest['referenced_media'].items():
            if manifest['media_files'].get(name) != expected: raise ValueError()
        if not isinstance(manifest['facts']['tables'], dict) or manifest['locale']['provider'] not in ('c', 'i', 'b'): raise ValueError()
        return manifest
    except (OSError, KeyError, TypeError, ValueError, zipfile.BadZipFile):
        raise CommandError('Sauvegarde invalide ou altérée ; aucune restauration autorisée.')


def create_target(cfg, target, locale):
    if cfg['host'] not in ('127.0.0.1', '::1') or not re.fullmatch(r'qavelys_restore_[0-9]{14}_[0-9a-f]{8}', target) or target == cfg['dbname']:
        raise CommandError('Restauration uniquement dans une nouvelle base locale qavelys_restore_<identifiant>.')
    with psycopg.connect(**{**cfg, 'dbname': 'postgres'}, autocommit=True) as conn:
        if conn.execute('SELECT 1 FROM pg_database WHERE datname=%s', [target]).fetchone(): raise CommandError('La cible existe déjà : refus de remplacer ses données.')
        command = sql.SQL('CREATE DATABASE {} TEMPLATE template0 ENCODING {} LC_COLLATE {} LC_CTYPE {}').format(sql.Identifier(target), sql.Literal(locale['encoding']), sql.Literal(locale['collate']), sql.Literal(locale['ctype']))
        provider = {'c': 'libc', 'i': 'icu', 'b': 'builtin'}[locale['provider']]
        command += sql.SQL(' LOCALE_PROVIDER {}').format(sql.SQL(provider))
        if provider != 'libc': command += sql.SQL(' {} {}').format(sql.SQL('ICU_LOCALE' if provider == 'icu' else 'BUILTIN_LOCALE'), sql.Literal(locale['locale']))
        if provider == 'icu' and locale.get('rules'): command += sql.SQL(' ICU_RULES {}').format(sql.Literal(locale['rules']))
        conn.execute(command)


def restore(folder, target=None):
    folder = Path(folder).resolve(); manifest = validate_bundle(folder); cfg = config()
    target = target or 'qavelys_restore_' + identifier()
    # Tous les refus de destination doivent précéder la création de la cible.
    if cfg['host'] not in ('127.0.0.1', '::1') or not re.fullmatch(r'qavelys_restore_[0-9]{14}_[0-9a-f]{8}', target) or target == cfg['dbname']: raise CommandError('Cible de restauration interdite.')
    output = private_directory(ROOT / '.local' / 'restores' / target.removeprefix('qavelys_restore_'))
    create_target(cfg, target, manifest['locale'])
    run_tool('pg_restore', cfg, target, ['--single-transaction', '--exit-on-error', '--no-owner', '--no-acl', '--no-tablespaces', str(folder / 'database.dump')], output)
    media = output / 'media'; media.mkdir(mode=0o700)
    with zipfile.ZipFile(folder / 'media.zip') as archive:
        for info in archive.infolist():
            file = media.joinpath(*safe_media_name(info.filename).parts)
            if not file.resolve().is_relative_to(media.resolve()): raise CommandError('Chemin média hors cible.')
            file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with archive.open(info) as source, file.open('xb') as destination: shutil.copyfileobj(source, destination)
            if digest_file(file) != manifest['media_files'][info.filename]: raise CommandError('Média restauré invalide.')
    with psycopg.connect(**{**cfg, 'dbname': target}) as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        facts = database_facts(conn)
        if facts['tables'] != manifest['facts']['tables'] or set(facts['sequences']) != set(manifest['facts']['sequences']): raise CommandError('Le contenu restauré ne correspond pas au snapshot.')
        verify_sequence_positions(conn)
        with conn.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM pg_constraint WHERE connamespace='public'::regnamespace AND contype IN ('f','c') AND NOT convalidated")
            if cursor.fetchone()[0] != 0: raise CommandError('Des contraintes restaurées ne sont pas validées.')
        if referenced_media(conn) != manifest['referenced_media']: raise CommandError('Références médias restaurées incohérentes.')
    report = {'database': target, 'media_root': str(media), 'verified': True, 'tables': len(manifest['facts']['tables']), 'media_files': len(manifest['media_files'])}
    (output / 'verified.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report
