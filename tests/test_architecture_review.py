"""Arkitekturgennemgang (v0.30.0): tokens fjernes fra loggen, driftstjek, backup uden login."""
import os

from app import logredact, selfcheck


def test_tokens_are_removed_from_access_log_fields():
    atoms = {"r": "GET /nulstil/abcDEF123-_x HTTP/1.1", "U": "/invitation/tok123/brugernavn", "f": "https://x.dk/svar/zz99?a=1",
             "q": "", "h": "1.2.3.4", "s": "200"}
    out = logredact.redact_atoms(atoms)
    assert out["r"] == "GET /nulstil/… HTTP/1.1" and out["U"] == "/invitation/…/brugernavn" and out["f"] == "https://x.dk/svar/…?a=1"
    assert out["h"] == "1.2.3.4" and logredact.redact("/players/12/edit") == "/players/12/edit"


def test_selfcheck_flags_dangerous_proxy_settings(tmp_path, monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("TOTP_KEY", raising=False)
    cfg = dict(PUBLIC_URL="https://hold.example", SESSION_COOKIE_SECURE=False, TRUSTED_PROXIES=0, BACKUP_DIR=str(tmp_path))
    txt = " ".join(t for _l, t in selfcheck.run(cfg))
    assert "COOKIE_SECURE=1" in txt and "TRUSTED_PROXIES=1" in txt and "SECRET_KEY" in txt and "TOTP_KEY" in txt and "Ingen backup" in txt
    (tmp_path / "u11-20261122-010101.db").write_text("x")
    monkeypatch.setenv("SECRET_KEY", "x" * 64)
    monkeypatch.setenv("TOTP_KEY", "k")
    monkeypatch.setenv("BACKUP_OFFSITE", "1")
    cfg.update(SESSION_COOKIE_SECURE=True, TRUSTED_PROXIES=1)
    assert selfcheck.run(cfg) == []


def test_selfcheck_is_shown_to_sysadmin_only(app, admin):
    page = admin.get("/admin/").get_data(as_text=True)
    assert "Driftstjek" in page


def test_gunicorn_config_uses_redacting_logger():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    conf = open(os.path.join(root, "gunicorn.conf.py")).read()
    docker = open(os.path.join(root, "Dockerfile")).read()
    assert "logger_class = RedactingLogger" in conf and '"-c", "gunicorn.conf.py"' in docker and "gunicorn.conf.py ./" in docker
