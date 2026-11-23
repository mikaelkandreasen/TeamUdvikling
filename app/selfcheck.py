"""Driftstjek: farlige eller ufuldstændige indstillinger, som ikke giver fejl, men svækker sikkerheden. Vises i Administration og logges ved start."""
import os
import time


def run(config):
    """Liste af (niveau, tekst), niveau = 'fejl' | 'advarsel'."""
    out = []
    public = (config.get("PUBLIC_URL") or "").strip()
    https = public.startswith("https://")
    if https and not config.get("SESSION_COOKIE_SECURE"):
        out.append(("fejl", "PUBLIC_URL er https, men COOKIE_SECURE=0: login-cookien kan sendes ukrypteret. Sæt COOKIE_SECURE=1."))
    if https and not config.get("TRUSTED_PROXIES"):
        out.append(("fejl", "PUBLIC_URL er https (bag proxy/Cloudflare), men TRUSTED_PROXIES=0: alle brugere ser ud til at komme fra samme IP, "
                            "så én angribers forkerte forsøg kan spærre alle ude. Sæt TRUSTED_PROXIES=1."))
    if not os.environ.get("SECRET_KEY"):
        out.append(("advarsel", "SECRET_KEY ligger som fil i /data sammen med databasen. Sæt den som miljøvariabel i Dockhand, "
                                "så en kopi af volumen ikke også giver nøglen til at forfalske logins."))
    if not os.environ.get("TOTP_KEY"):
        out.append(("advarsel", "TOTP_KEY ligger som fil i /data. Kopiér indholdet af /data/totp_key (præcis samme nøgle – ellers holder alles 2FA op med at virke) "
                                "til miljøvariablen TOTP_KEY, gem den uden for backupperne, og slet filen. Ellers kan en volumen-kopi også dekryptere 2FA-nøglerne."))
    bdir = config.get("BACKUP_DIR") or ""
    try:
        files = sorted((f for f in os.listdir(bdir) if f.startswith(("teamudvikling-", "u11-")) and f.endswith(".db")), key=lambda f: f.split("-", 1)[1])
        newest = os.path.getmtime(os.path.join(bdir, files[-1])) if files else 0
    except OSError:
        newest = 0
    if not newest or time.time() - newest > 2 * 86400:
        out.append(("advarsel", "Ingen backup de seneste 2 døgn i /data/backups."))
    if newest and os.environ.get("BACKUP_OFFSITE") != "1":
        out.append(("advarsel", "Backupperne ligger på samme disk som databasen. Kopiér dem krypteret til et andet sted (se docs/BACKUP.md), og sæt BACKUP_OFFSITE=1, når det er på plads."))
    return out
