"""Kalenderfeed (iCal/.ics), fx fra DBU KampKlar eller klubbens kalender: parser + sikker hentning.

Hentning sker kun over https, kun til offentlige IP-adresser (ingen intern adresse/localhost/link-local), maks. 1 MB, kort timeout
og højst 3 omdirigeringer (hver kontrolleres igen). URL'en kan kun sættes af chef-træner/administrator.
"""
import datetime
import http.client
import ipaddress
import socket
import ssl
import urllib.parse

MAX_BYTES = 1024 * 1024
TIMEOUT = 8


class FeedError(Exception):
    pass


def _public_host(host):
    """Slår værten op og returnerer en offentlig IP. Afviser, hvis bare én af adresserne er intern."""
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError) as exc:
        raise FeedError("Adressen kunne ikke slås op.") from exc
    ips = []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise FeedError("Adressen peger på en ikke-offentlig adresse og afvises.")
        ips.append(str(ip))
    if not ips:
        raise FeedError("Adressen kunne ikke slås op.")
    return ips[0]


def normalize_url(url):
    """Kalenderlinks fra Apple/Google starter ofte med webcal:// (webcals://) – det er blot https."""
    url = (url or "").strip()
    low = url.lower()
    if low.startswith("webcals://"):
        return "https://" + url[10:]
    if low.startswith("webcal://"):
        return "https://" + url[9:]
    return url


def check_url(url):
    p = urllib.parse.urlsplit(url or "")
    if (p.scheme != "https" or not p.hostname or p.username or p.password or (p.port not in (None, 443))
            or any(ord(c) < 33 for c in url)):
        raise FeedError("Kalenderadressen skal være en https-adresse.")
    _public_host(p.hostname)
    return url


class _PinnedHTTPS(http.client.HTTPSConnection):
    """Forbinder til den IP, der allerede er kontrolleret (ingen nyt DNS-opslag → ingen DNS-rebinding),
    men verificerer certifikatet mod værtsnavnet som normalt."""
    def __init__(self, host, ip):
        super().__init__(host, 443, timeout=TIMEOUT, context=ssl.create_default_context())
        self._ip = ip

    def connect(self):
        sock = socket.create_connection((self._ip, 443), TIMEOUT)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def fetch(url):
    """Henter feedet som tekst. Hver omdirigering kontrolleres igen. Fejl → FeedError med generisk tekst (aldrig svar-indhold)."""
    for _ in range(4):
        check_url(url)
        p = urllib.parse.urlsplit(url)
        ip = _public_host(p.hostname)
        conn = _PinnedHTTPS(p.hostname, ip)
        try:
            conn.request("GET", (p.path or "/") + (f"?{p.query}" if p.query else ""),
                         headers={"User-Agent": "TeamUdvikling-kalender/1.0", "Accept": "text/calendar,*/*"})
            r = conn.getresponse()
            if r.status in (301, 302, 303, 307, 308) and r.getheader("Location"):
                url = urllib.parse.urljoin(url, r.getheader("Location"))
                continue
            if r.status != 200:
                raise FeedError(f"Kalenderen svarede med fejl ({r.status}).")
            data = r.read(MAX_BYTES + 1)
        except (OSError, http.client.HTTPException) as exc:
            raise FeedError("Kalenderen kunne ikke hentes.") from exc
        finally:
            conn.close()
        if len(data) > MAX_BYTES:
            raise FeedError("Kalenderen er for stor.")
        return data.decode("utf-8", "replace")
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
