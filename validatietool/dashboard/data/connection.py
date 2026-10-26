"""Elke bron wordt in een korte read-only REPEATABLE READ-transactie gelezen."""
from contextlib import contextmanager
from datetime import timezone
from pathlib import Path
import psycopg2

SQL_ROOT = Path(__file__).with_name('sql')
QUERY_NAMES = frozenset(p.stem for p in SQL_ROOT.glob('*.sql'))


class DataSourceError(RuntimeError):
    pass


class ReadSession:
    def __init__(self, connection):
        self.connection = connection
        with connection.cursor() as cur:
            cur.execute("""SELECT current_database(),transaction_timestamp(),
                current_setting('transaction_read_only'),current_setting('transaction_isolation'),
                current_setting('statement_timeout')""")
            database, timestamp, readonly, isolation, timeout = cur.fetchone()
        if readonly != 'on' or isolation != 'repeatable read':
            raise DataSourceError('Read-only REPEATABLE READ is niet afgedwongen.')
        self.metadata = {'database': database, 'snapshot_utc': timestamp.astimezone(timezone.utc).isoformat(),
                         'readonly': True, 'isolation': isolation, 'statement_timeout': timeout}

    def fetch(self, name, parameters=None):
        """Alleen gebundelde, benoemde querybestanden; waarden via SQL-parameters."""
        if name not in QUERY_NAMES:
            raise ValueError('Onbekende dashboardquery.')
        query = (SQL_ROOT / (name + '.sql')).read_text(encoding='utf-8')
        with self.connection.cursor() as cur:
            cur.execute(query, parameters)
            names = [c.name for c in cur.description]
            return [dict(zip(names, row)) for row in cur.fetchall()]


@contextmanager
def read_session(settings, source):
    if source not in ('register', 'corpus'):
        raise ValueError('Onbekende databron.')
    settings.validate_connection()
    con = None
    try:
        con = psycopg2.connect(host=settings.host, port=settings.port, user=settings.user,
            password=settings.password,
            dbname=settings.register_database if source == 'register' else settings.corpus_database,
            sslmode=settings.sslmode, connect_timeout=15, application_name='ab_dashboard_readonly',
            options=f'-c default_transaction_read_only=on -c statement_timeout={settings.timeout_ms} -c lock_timeout=3000')
        con.set_session(readonly=True, isolation_level='REPEATABLE READ', autocommit=False)
        yield ReadSession(con)
    except psycopg2.Error as exc:
        if exc.pgcode == '57014':
            reason = 'query overschreed de tijdslimiet'
        elif 'remaining connection slots' in str(exc):
            reason = 'geen vrije verbindingsplaatsen'
        else:
            reason = 'verbinding of bronquery mislukt'
        raise DataSourceError(source + ': ' + reason + '. Broninstellingen zijn niet gelogd.') from None
    finally:
        if con is not None:
            try:
                con.rollback()
            finally:
                con.close()
