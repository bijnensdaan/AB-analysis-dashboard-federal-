"""Credentials uitsluitend uit procesomgeving/.env; legacy bestand blijft ongewijzigd."""
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re

ANALYSIS = Path(__file__).resolve().parents[3]


class ConfigurationError(ValueError):
    pass


def read_env(path):
    """Eerste legacy waarde wint, gelijk aan de bestaande db-helper; geen waarden loggen."""
    values, duplicates = {}, set()
    if not path.exists():
        return values, ()
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if stripped.startswith('export '):
            stripped = stripped[7:]
        if '=' not in stripped:
            continue
        key, value = stripped.split('=', 1)
        key, value = key.strip(), value.strip()
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key):
            continue
        # Canonieke AB_* waarden mogen geciteerd zijn; geen shellinterpolatie.
        if value[:1] in ('"', "'"):
            match = re.fullmatch(r'''(['"])(.*?)\1\s*(?:#.*)?''', value)
            if not match:
                raise ConfigurationError('Ongeldige geciteerde waarde voor ' + key + '.')
            value = match.group(2)
        elif key.upper().startswith('AB_'):
            value = re.split(r'\s+#', value, maxsplit=1)[0].rstrip()
        else:
            value = value.split()[0] if value.split() else ''
        normalized = key.upper()
        if normalized in values:
            duplicates.add(normalized)
        else:
            values[normalized] = value
    return values, tuple(sorted(duplicates))


@dataclass(frozen=True)
class Settings:
    host: str = field(repr=False)
    user: str = field(repr=False)
    password: str = field(repr=False)
    port: int = 25060
    sslmode: str = 'require'
    register_database: str = 'admin_burden_classifications'
    corpus_database: str = 'riavectors'
    timeout_ms: int = 30000
    duplicate_keys: tuple[str, ...] = ()

    @classmethod
    def load(cls, env_path=None, environ=None):
        values, duplicates = read_env(Path(env_path) if env_path else ANALYSIS / '.env')
        process = {k.upper(): v for k, v in (os.environ if environ is None else environ).items()}

        def pick(canonical, *legacy, default=''):
            # Expliciete AB_* instelling heeft voorrang op generieke legacy namen.
            if canonical in process:
                return process[canonical]
            if canonical in values:
                return values[canonical]
            pg_name = {'AB_DB_HOST':'PGHOST', 'AB_DB_PORT':'PGPORT', 'AB_DB_USER':'PGUSER',
                       'AB_DB_PASSWORD':'PGPASSWORD', 'AB_DB_SSLMODE':'PGSSLMODE'}.get(canonical)
            if pg_name and process.get(pg_name):
                return process[pg_name]
            # USER/USERNAME uit het OS zijn geen databasecredentials.
            for key in legacy:
                if values.get(key):
                    return values[key]
            return default

        try:
            settings = cls(host=pick('AB_DB_HOST', 'HOST'), user=pick('AB_DB_USER', 'USER', 'USERNAME'),
                           password=pick('AB_DB_PASSWORD', 'PASSWORD'),
                           port=int(pick('AB_DB_PORT', 'PORT', default='25060')),
                           sslmode=pick('AB_DB_SSLMODE', 'SSLMODE', default='require'),
                           register_database=pick('AB_REGISTER_DATABASE', default='admin_burden_classifications'),
                           corpus_database=pick('AB_CORPUS_DATABASE', default='riavectors'),
                           timeout_ms=int(pick('AB_QUERY_TIMEOUT_MS', default='30000')), duplicate_keys=duplicates)
        except ValueError:
            raise ConfigurationError('Poort en querytimeout moeten geldige gehele getallen zijn.') from None
        if not 1 <= settings.port <= 65535 or not 1000 <= settings.timeout_ms <= 300000:
            raise ConfigurationError('Ongeldige poort of querytimeout (1000–300000 ms).')
        if settings.sslmode not in ('require', 'verify-ca', 'verify-full'):
            raise ConfigurationError('Gebruik sslmode require, verify-ca of verify-full.')
        return settings

    def validate_connection(self):
        if not all((self.host, self.user, self.password, self.register_database, self.corpus_database)):
            raise ConfigurationError('Verbindingsinstellingen ontbreken; vul AB_DB_HOST, AB_DB_USER en AB_DB_PASSWORD in.')

    def cache_identity(self):
        """Bron/account onderscheiden zonder credentials in cachemetadata op te slaan."""
        identity = (self.host, self.port, self.user, self.register_database, self.corpus_database)
        return hashlib.sha256(json.dumps(identity).encode()).hexdigest()
