"""Firebird Studio Web — backend. Python 3.11+, Flask, official firebird-driver.
Only predefined server-side database profiles are reachable. Never expose Firebird passwords to clients.
"""
import datetime as dt
import decimal
import hmac
import json
import os
import re
import secrets
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from pathlib import PurePosixPath
from functools import wraps

from flask import Flask, jsonify, request, send_from_directory, session

ROOT = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder='static', static_url_path='/static')
app.secret_key = os.environ.get('APP_SECRET_KEY') or secrets.token_hex(32)
app.config.update(
    MAX_CONTENT_LENGTH=1024*512,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE', '1') != '0',
    PERMANENT_SESSION_LIFETIME=dt.timedelta(hours=8),
)

ADMIN_PASSWORD = os.environ.get('APP_ADMIN_PASSWORD', '')
MAX_ROWS = 250
IDENT_RE = re.compile(r'^[^\x00-\x1f\x7f]{1,63}$')
FAILED = defaultdict(deque)


def configs():
    """Support one connection or predefined named connections; no arbitrary client host targets."""
    raw = os.environ.get('FIREBIRD_CONNECTIONS_JSON', '').strip()
    if raw:
        try:
            entries = json.loads(raw)
            if not isinstance(entries, list):
                return {}
        except (ValueError, TypeError):
            return {}
    elif os.environ.get('FIREBIRD_DATABASE'):
        entries = [{
            'name': os.environ.get('FIREBIRD_NAME', 'Principal'),
            'host': os.environ.get('FIREBIRD_HOST', '127.0.0.1'),
            'port': os.environ.get('FIREBIRD_PORT', '3050'),
            'database': os.environ['FIREBIRD_DATABASE'],
            'user': os.environ.get('FIREBIRD_USER', 'SYSDBA'),
            'password': os.environ.get('FIREBIRD_PASSWORD', ''),
        }]
    else:
        entries = []
    result = {}
    for item in entries:
        if not isinstance(item, dict):
            continue
        name = str(item.get('name', '')).strip()
        if name and name not in result and item.get('database') and item.get('host'):
            result[name] = item
    return result


def active_config():
    names = configs()
    if not names:
        raise ValueError('Nenhum banco Firebird configurado no servidor. Consulte o README.')
    current = session.get('connection')
    return names.get(current) or next(iter(names.values()))


def active_name():
    c = active_config()
    return str(c.get('name'))


def quote_ident(name):
    if not isinstance(name, str) or not IDENT_RE.fullmatch(name) or name.strip() != name:
        raise ValueError('Nome de objeto inválido.')
    return '"' + name.replace('"', '""') + '"'


def db_connection_for(profile):
    from firebird.driver import connect, driver_config
    # driver_config is shared; guard against modifying defaults on each request:
    # all backends use registered names? use direct single profile with a synchronized lock.
    import threading
    global _connect_lock
    with _connect_lock:
        driver_config.server_defaults.host.value = str(profile.get('host', '127.0.0.1'))
        driver_config.server_defaults.port.value = str(profile.get('port', 3050))
        driver_config.db_defaults.charset.value = str(profile.get('charset', 'UTF8'))
        con = connect(str(profile['database']), user=str(profile.get('user', 'SYSDBA')),
                      password=str(profile.get('password', '')))
    return con


import threading
_connect_lock = threading.RLock()


@contextmanager
def database():
    con = db_connection_for(active_config())
    try:
        yield con
    finally:
        try:
            con.close()
        except Exception:
            pass


def clean(value):
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (dt.date, dt.time, dt.datetime)):
        return value.isoformat(sep=' ') if isinstance(value, dt.datetime) else value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f'[BINÁRIO: {len(value)} bytes]'
    if isinstance(value, str):
        return value[:12000] + ('…' if len(value)>12000 else '')
    if hasattr(value, 'read'):
        return '[BLOB — visualização indisponível]'
    return str(value)[:12000]


def fetch(cur, limit=MAX_ROWS):
    columns = [str(d[0]).strip() for d in (cur.description or [])]
    rows = [[clean(v) for v in row] for row in cur.fetchmany(limit+1)]
    truncated = len(rows) > limit
    return {'columns': columns, 'rows': rows[:limit], 'truncated': truncated}


def error_reply(exc, status=400):
    # Errors from Firebird can include full file paths and sensitive info. Avoid returning these to unauthenticated users.
    return jsonify(error=str(exc)[:500]), status


@app.after_request
def headers(resp):
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['Referrer-Policy'] = 'same-origin'
    resp.headers['X-Frame-Options'] = 'DENY'
    resp.headers['Cache-Control'] = 'no-store' if request.path.startswith('/api/') else 'public, max-age=3600'
    resp.headers['Content-Security-Policy'] = "default-src 'self'; connect-src 'self'; img-src 'self' data: blob:; font-src 'self'; style-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    return resp


@app.route('/')
def index():
    return send_from_directory(ROOT, 'index.html')


@app.route('/api/status')
def status():
    profiles = configs()
    authed = bool(ADMIN_PASSWORD and session.get('authenticated'))
    return jsonify(authenticated=authed, configured=bool(profiles), profiles=list(profiles) if authed else [],
                   active=active_name() if authed and profiles else None,
                   csrf=session.get('csrf') if authed else None, mode='real' if authed and profiles else 'demo')


def same_origin():
    origin = request.headers.get('Origin')
    if not origin:
        return True
    from urllib.parse import urlparse
    parsed = urlparse(origin)
    return parsed.netloc == request.host and parsed.scheme in ('https', 'http')


@app.before_request
def protect_origin():
    if request.path.startswith('/api/') and request.method not in ('GET', 'HEAD', 'OPTIONS') and not same_origin():
        return jsonify(error='Origem da requisição não permitida.'), 403


@app.post('/api/login')
def login():
    if not ADMIN_PASSWORD:
        return jsonify(error='Configure APP_ADMIN_PASSWORD no servidor antes de acessar bancos reais.'), 503
    ip = request.remote_addr or 'unknown'
    attempts = FAILED[ip]
    now = time.monotonic()
    while attempts and now - attempts[0] > 300:
        attempts.popleft()
    if len(attempts) >= 8:
        return jsonify(error='Muitas tentativas. Aguarde 5 minutos.'), 429
    submitted = (request.get_json(silent=True) or {}).get('password', '')
    if not isinstance(submitted, str) or not hmac.compare_digest(submitted, ADMIN_PASSWORD):
        attempts.append(now)
        return jsonify(error='Senha incorreta.'), 401
    attempts.clear()
    session.clear()
    session['authenticated'] = True
    session['csrf'] = secrets.token_urlsafe(32)
    session.permanent = True
    return status()


def authorized(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not ADMIN_PASSWORD or not session.get('authenticated'):
            return jsonify(error='Autentique-se para acessar o banco real.'), 401
        if request.method not in ('GET', 'HEAD') and not hmac.compare_digest(
            request.headers.get('X-CSRF-Token', ''), session.get('csrf', 'not-set')):
            return jsonify(error='Token de segurança inválido. Atualize a página.'), 403
        return fn(*args, **kwargs)
    return wrapped


@app.post('/api/logout')
@authorized
def logout():
    session.clear()
    return jsonify(ok=True)


@app.post('/api/connection')
@authorized
def select_connection():
    name = (request.get_json(silent=True) or {}).get('name')
    if name not in configs():
        return jsonify(error='Conexão desconhecida.'), 400
    session['connection'] = name
    return jsonify(ok=True, active=name)


@app.get('/api/ping')
@authorized
def ping():
    try:
        with database() as con:
            c = con.cursor()
            c.execute('SELECT CURRENT_TIMESTAMP FROM RDB$DATABASE')
            row = c.fetchone()
            return jsonify(ok=True, time=clean(row[0]), active=active_name())
    except Exception as exc:
        return error_reply(exc, 502)


OBJECT_QUERIES = {
    'tables': "SELECT TRIM(RDB$RELATION_NAME) FROM RDB$RELATIONS WHERE COALESCE(RDB$SYSTEM_FLAG,0)=0 AND RDB$VIEW_BLR IS NULL ORDER BY 1",
    'views': "SELECT TRIM(RDB$RELATION_NAME) FROM RDB$RELATIONS WHERE COALESCE(RDB$SYSTEM_FLAG,0)=0 AND RDB$VIEW_BLR IS NOT NULL ORDER BY 1",
    'procedures': "SELECT TRIM(RDB$PROCEDURE_NAME) FROM RDB$PROCEDURES WHERE COALESCE(RDB$SYSTEM_FLAG,0)=0 ORDER BY 1",
    'triggers': "SELECT TRIM(RDB$TRIGGER_NAME) FROM RDB$TRIGGERS WHERE COALESCE(RDB$SYSTEM_FLAG,0)=0 ORDER BY 1",
    'sequences': "SELECT TRIM(RDB$GENERATOR_NAME) FROM RDB$GENERATORS WHERE COALESCE(RDB$SYSTEM_FLAG,0)=0 ORDER BY 1",
    'domains': "SELECT TRIM(RDB$FIELD_NAME) FROM RDB$FIELDS WHERE COALESCE(RDB$SYSTEM_FLAG,0)=0 ORDER BY 1",
    'indexes': "SELECT TRIM(I.RDB$INDEX_NAME) FROM RDB$INDICES I JOIN RDB$RELATIONS R ON R.RDB$RELATION_NAME=I.RDB$RELATION_NAME WHERE COALESCE(R.RDB$SYSTEM_FLAG,0)=0 ORDER BY 1"
}


@app.get('/api/schema')
@authorized
def schema():
    try:
        with database() as con:
            cur = con.cursor()
            result = {}
            for category, sql in OBJECT_QUERIES.items():
                cur.execute(sql)
                result[category] = [r[0] for r in cur.fetchall()]
            con.rollback()
            return jsonify(objects=result, connection=active_name())
    except Exception as exc:
        return error_reply(exc, 502)


def table_metadata(con, name):
    cur = con.cursor()
    cur.execute("""SELECT TRIM(RF.RDB$FIELD_NAME), F.RDB$FIELD_TYPE, F.RDB$FIELD_SUB_TYPE,
            F.RDB$FIELD_LENGTH, F.RDB$FIELD_PRECISION, F.RDB$FIELD_SCALE,
            RF.RDB$NULL_FLAG, F.RDB$CHARACTER_LENGTH, RF.RDB$FIELD_POSITION,
            RF.RDB$DEFAULT_SOURCE
        FROM RDB$RELATION_FIELDS RF
        JOIN RDB$FIELDS F ON F.RDB$FIELD_NAME=RF.RDB$FIELD_SOURCE
        WHERE RF.RDB$RELATION_NAME=? ORDER BY RF.RDB$FIELD_POSITION""", (name,))
    types = {7:'SMALLINT', 8:'INTEGER', 10:'FLOAT', 12:'DATE',13:'TIME',14:'CHAR',16:'BIGINT',
             23:'BOOLEAN', 27:'DOUBLE PRECISION', 35:'TIMESTAMP',37:'VARCHAR', 261:'BLOB'}
    cols = []
    for n, t, subtype, size, precision, scale, notnull, length, position, default in cur.fetchall():
        typ = types.get(t, f'TYPE {t}')
        if t in (14, 37):
            typ += f'({length or size})'
        if t in (7,8,16) and (subtype or 0) in (1,2) and scale:
            typ = f'{"NUMERIC" if subtype == 1 else "DECIMAL"}({precision or 18},{abs(scale)})'
        cols.append({'name':n,'type':typ,'nullable':not bool(notnull), 'default':clean(default), 'position':position})
    cur.execute("""SELECT TRIM(S.RDB$FIELD_NAME)
        FROM RDB$RELATION_CONSTRAINTS C
        JOIN RDB$INDEX_SEGMENTS S ON S.RDB$INDEX_NAME=C.RDB$INDEX_NAME
        WHERE C.RDB$RELATION_NAME=? AND C.RDB$CONSTRAINT_TYPE='PRIMARY KEY'
        ORDER BY S.RDB$FIELD_POSITION""", (name,))
    pk = [r[0] for r in cur.fetchall()]
    cur.execute("""SELECT TRIM(I.RDB$INDEX_NAME), I.RDB$UNIQUE_FLAG, TRIM(S.RDB$FIELD_NAME)
        FROM RDB$INDICES I JOIN RDB$INDEX_SEGMENTS S ON S.RDB$INDEX_NAME=I.RDB$INDEX_NAME
        WHERE I.RDB$RELATION_NAME=? ORDER BY I.RDB$INDEX_NAME, S.RDB$FIELD_POSITION""", (name,))
    ix = {}
    for ixname, unique, field in cur.fetchall():
        ix.setdefault(ixname, {'name':ixname,'unique':bool(unique),'columns':[]})['columns'].append(field)
    return {'columns':cols, 'pk':pk, 'indexes':list(ix.values())}


@app.get('/api/table/<path:table>')
@authorized
def describe(table):
    try:
        quote_ident(table)
        with database() as con:
            meta = table_metadata(con, table)
            if not meta['columns']:
                return jsonify(error='Tabela ou view não encontrada.'), 404
            con.rollback()
            return jsonify(name=table, **meta)
    except Exception as exc:
        return error_reply(exc)


@app.get('/api/rows/<path:table>')
@authorized
def rows(table):
    try:
        quote_ident(table)
        limit = max(1, min(int(request.args.get('limit', '100')), MAX_ROWS))
        page = max(0, min(int(request.args.get('page','0')), 100000))
        with database() as con:
            meta = table_metadata(con, table)
            if not meta['columns']:
                return jsonify(error='Objeto não encontrado.'), 404
            names = [c['name'] for c in meta['columns']]
            sort = request.args.get('sort', '')
            order = request.args.get('order', 'ASC').upper()
            if sort not in names:
                sort = meta['pk'][0] if meta['pk'] else names[0]
            if order not in ('ASC', 'DESC'):
                order = 'ASC'
            cur = con.cursor()
            # Pagination uses rows(offset+limit+1) rather than unbounded browsing.
            cur.execute(f'SELECT FIRST {limit+1} SKIP {page*limit} * FROM {quote_ident(table)} ORDER BY {quote_ident(sort)} {order}')
            data = fetch(cur, limit)
            con.rollback()
            return jsonify(page=page, limit=limit, sort=sort, order=order, pk=meta['pk'], **data)
    except Exception as exc:
        return error_reply(exc)


@app.post('/api/query')
@authorized
def query():
    data = request.get_json(silent=True) or {}
    sql = data.get('sql', '')
    if isinstance(sql, str):
        sql = sql.strip()
        # Statement terminators belong to isql scripts, not the Firebird API.
        if sql.endswith(';'):
            sql = sql[:-1].rstrip()
    if not isinstance(sql, str) or not 1 <= len(sql.strip()) <= 50000:
        return jsonify(error='SQL vazio ou longo demais (máximo 50.000 caracteres).'), 400
    try:
        with database() as con:
            cur = con.cursor()
            try:
                cur.execute(sql)
                if cur.description:
                    output = fetch(cur)
                    con.commit()  # SELECT EXECUTE PROCEDURE may have side effects
                    return jsonify(ok=True, kind='result', affected=cur.rowcount, **output)
                affected = cur.rowcount
                con.commit()
                return jsonify(ok=True, kind='command', affected=affected, columns=[], rows=[])
            except Exception:
                con.rollback()
                raise
    except Exception as exc:
        return error_reply(exc)


def current_table_meta(con, table):
    quote_ident(table)
    cur = con.cursor()
    cur.execute("SELECT 1 FROM RDB$RELATIONS WHERE RDB$RELATION_NAME=? AND RDB$VIEW_BLR IS NULL AND COALESCE(RDB$SYSTEM_FLAG,0)=0", (table,))
    if not cur.fetchone():
        raise ValueError('A edição está disponível somente para tabelas de usuário.')
    return table_metadata(con, table)


def validate_values(meta, values):
    if not isinstance(values, dict) or not values:
        raise ValueError('Informe pelo menos uma coluna.')
    allowed = {c['name'] for c in meta['columns']}
    if not set(values).issubset(allowed):
        raise ValueError('Uma ou mais colunas não pertencem à tabela.')
    if len(values) > 100:
        raise ValueError('Muitas colunas.')
    return values


@app.post('/api/record/<path:table>')
@authorized
def add_row(table):
    try:
        values = (request.get_json(silent=True) or {}).get('values', {})
        with database() as con:
            meta = current_table_meta(con, table)
            validate_values(meta, values)
            fields = list(values)
            sql = (f'INSERT INTO {quote_ident(table)} (' + ', '.join(quote_ident(x) for x in fields)
                   + ') VALUES (' + ', '.join('?' for _ in fields) + ')')
            try:
                cur=con.cursor(); cur.execute(sql, [values[x] for x in fields]); con.commit()
            except Exception:
                con.rollback(); raise
            return jsonify(ok=True, affected=cur.rowcount)
    except Exception as exc:
        return error_reply(exc)


@app.put('/api/record/<path:table>')
@authorized
def update_row(table):
    try:
        body = request.get_json(silent=True) or {}
        values, key = body.get('values',{}), body.get('key',{})
        with database() as con:
            meta = current_table_meta(con, table)
            validate_values(meta,values)
            if not meta['pk'] or not isinstance(key,dict) or set(key) != set(meta['pk']):
                raise ValueError('É necessária uma chave primária para editar registros com segurança.')
            fields = list(values)
            sql = f'UPDATE {quote_ident(table)} SET ' + ', '.join(quote_ident(x)+'=?' for x in fields)
            sql += ' WHERE ' + ' AND '.join(quote_ident(x)+'=?' for x in meta['pk'])
            try:
                cur=con.cursor(); cur.execute(sql, [values[x] for x in fields]+[key[x] for x in meta['pk']]); con.commit()
            except Exception:
                con.rollback(); raise
            return jsonify(ok=True, affected=cur.rowcount)
    except Exception as exc:
        return error_reply(exc)


@app.delete('/api/record/<path:table>')
@authorized
def delete_row(table):
    try:
        body = request.get_json(silent=True) or {}
        key = body.get('key',{})
        with database() as con:
            meta = current_table_meta(con, table)
            if not meta['pk'] or not isinstance(key,dict) or set(key)!=set(meta['pk']):
                raise ValueError('É necessária uma chave primária para excluir registros com segurança.')
            sql = f'DELETE FROM {quote_ident(table)} WHERE ' + ' AND '.join(quote_ident(x)+'=?' for x in meta['pk'])
            try:
                cur=con.cursor(); cur.execute(sql,[key[x] for x in meta['pk']]); con.commit()
            except Exception:
                con.rollback(); raise
            return jsonify(ok=True, affected=cur.rowcount)
    except Exception as exc:
        return error_reply(exc)


@app.post('/api/create-database')
@authorized
def create_db():
    """Create new Firebird database ONLY in server admin's designated directory."""
    directory = os.environ.get('FIREBIRD_CREATE_DIRECTORY','').strip()
    if not directory:
        return jsonify(error='Criação remota desabilitada. Configure FIREBIRD_CREATE_DIRECTORY no Render.'), 403
    body = request.get_json(silent=True) or {}
    filename = str(body.get('filename','')).strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,48}\.fdb', filename, re.IGNORECASE):
        return jsonify(error='Use apenas letras, números, _ ou -, terminando em .fdb.'), 400
    profile = active_config()
    # The configured directory is a path on the Firebird host, which may run Windows.
    import ntpath
    full_path = (ntpath.join(directory, filename) if ('\\' in directory or re.match(r'^[A-Za-z]:', directory))
                 else str(PurePosixPath(directory) / filename))
    try:
        from firebird.driver import create_database, driver_config
        with _connect_lock:
            driver_config.server_defaults.host.value = str(profile.get('host','127.0.0.1'))
            driver_config.server_defaults.port.value = str(profile.get('port',3050))
            driver_config.db_defaults.charset.value = 'UTF8'
            driver_config.db_defaults.db_charset.value = 'UTF8'
            driver_config.db_defaults.db_sql_dialect.value = 3
            con = create_database(full_path, user=str(profile.get('user','SYSDBA')),
                                  password=str(profile.get('password','')))
        con.close()
        return jsonify(ok=True, database=full_path, message='Banco criado. Cadastre o caminho como conexão nas variáveis do Render para acessá-lo.')
    except Exception as exc:
        return error_reply(exc)


@app.errorhandler(404)
def not_found(_):
    return jsonify(error='Endpoint não encontrado.'), 404


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT','10000')), debug=False)
