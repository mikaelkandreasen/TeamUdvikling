"""gunicorn-opsætning: adgangslog uden engangstokens (se app/logredact.py). Øvrige indstillinger står i Dockerfile (CMD)."""
from gunicorn.glogging import Logger

from app.logredact import redact_atoms


class RedactingLogger(Logger):
    def atoms(self, resp, req, environ, request_time):
        return redact_atoms(super().atoms(resp, req, environ, request_time))


logger_class = RedactingLogger
