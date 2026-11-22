"""Gunicorn starter flere workers samtidig. Opstarten (migrationer, nøglefiler, opsætningskode) må ikke fejle eller give forskellige nøgler."""
import multiprocessing as mp
import os


def _boot(data_dir, q):
    try:
        os.environ["U11_DATA_DIR"] = data_dir
        os.environ.pop("SECRET_KEY", None)
        os.environ.pop("TOTP_KEY", None)
        from app import create_app
        app = create_app({"MAIL_WORKER": "0"})
        q.put(("ok", app.config["SECRET_KEY"], app.config["TOTP_KEY_BYTES"], app.config["SETUP_TOKEN"]))
    except Exception as exc:          # noqa: BLE001
        q.put(("fejl", repr(exc), None, None))


def test_parallel_workers_start_on_fresh_and_on_migrating_database(tmp_path):
    ctx = mp.get_context("fork")
    for round_ in ("frisk", "genstart"):
        q = ctx.Queue()
        procs = [ctx.Process(target=_boot, args=(str(tmp_path), q)) for _ in range(6)]
        for p in procs:
            p.start()
        res = [q.get(timeout=60) for _ in procs]
        for p in procs:
            p.join(30)
        assert all(r[0] == "ok" for r in res), (round_, res)
        assert len({r[1] for r in res}) == 1 and len({r[2] for r in res}) == 1 and len({r[3] for r in res}) == 1, round_
        if round_ == "frisk":                     # simulér en opdatering med ventende migrationer
            import sqlite3
            con = sqlite3.connect(tmp_path / "u11.db")
            con.execute("DELETE FROM schema_migrations WHERE id IN ('012_kamp_ical_uid','013_team_kriterier','014_bruger_sprog')")
            con.commit(); con.close()
