"""Kalenderfeed (iCal/.ics), fx fra DBU KampKlar eller klubbens kalender: parser + sikker hentning.

Hentning sker kun over https, kun til offentlige IP-adresser (ingen intern adresse/localhost/link-local), maks. 1 MB, kort timeout
og højst 3 omdirigeringer (hver kontrolleres igen). URL'en kan kun sættes af chef-træner/administrator.
"""
import datetime
import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request

MAX_BYTES = 1024 * 1024
TIMEOUT = 8


class FeedError(Exception):
    pass


def _public_host(host):
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise FeedError("Adressen kunne ikke slås op.") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise FeedError("Adressen peger på en ikke-offentlig adresse og afvises.")


def check_url(url):
    p = urllib.parse.urlparse(url or "")
    if p.scheme != "https" or not p.hostname or p.username or p.password or (p.port not in (None, 443)):
        raise FeedError("Kalenderadressen skal være en https-adresse.")
    _public_host(p.hostname)
    return url


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def fetch(url):
    """Henter feedet som tekst. Fejl → FeedError med generisk tekst (aldrig svar-indhold)."""
    opener = urllib.request.build_opener(_NoRedirect)
    for _ in range(4):
        check_url(url)
        req = urllib.request.Request(url, headers={"User-Agent": "TeamUdvikling-kalender/1.0", "Accept": "text/calendar,*/*"})
        try:
            with opener.open(req, timeout=TIMEOUT) as r:
                data = r.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise FeedError("Kalenderen er for stor.")
                return data.decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308) and exc.headers.get("Location"):
                url = urllib.parse.urljoin(url, exc.headers["Location"])
                continue
            raise FeedError(f"Kalenderen svarede med fejl ({exc.code}).") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise FeedError("Kalenderen kunne ikke hentes.") from exc
    raise FeedError("For mange omdirigeringer.")


def _unfold(text):
    out = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def _unescape(v):
    return v.replace("\\n", " ").replace("\\N", " ").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def _date(value):
    v = value.strip()
    try:
        return datetime.datetime.strptime(v[:8], "%Y%m%d").date()
    except ValueError:
        return None


def parse(text):
    """[{uid, summary, day (YYYY-MM-DD), time (HH:MM|''), location}] sorteret efter dato. Ukendte/ugyldige hændelser springes over."""
    events, cur = [], None
    for line in _unfold(text):
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT" and cur is not None:
            d = _date(cur.get("DTSTART", ""))
            if d and not cur.get("STATUS", "").upper().startswith("CANCEL"):
                raw = cur["DTSTART"].strip()
                t = raw[9:11] + ":" + raw[11:13] if len(raw) >= 13 and raw[8] == "T" else ""
                events.append(dict(uid=cur.get("UID", "")[:120], summary=_unescape(cur.get("SUMMARY", ""))[:120], day=d.isoformat(), time=t,
                                   location=_unescape(cur.get("LOCATION", ""))[:120]))
            cur = None
        elif cur is not None and ":" in line:
            name, _, val = line.partition(":")
            cur.setdefault(name.split(";")[0].upper(), val)
    return sorted(events, key=lambda e: (e["day"], e["time"]))


def kind_of(summary):
    s = (summary or "").lower()
    return "match" if any(w in s for w in ("kamp", "match", "turnering", "stævne", " vs ", " mod ")) else "training"
