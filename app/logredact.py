"""Fjerner engangstokens fra adgangsloggen. Links til nulstilling, invitation og spillerskema virker, indtil de er brugt/udløbet,
så de må ikke kunne læses i container-loggen (Dockhand, docker logs) eller i Referer-feltet."""
import re

_TOKEN = re.compile(r"(/(?:nulstil|invitation|svar)/)[^/?#\s\"]+")


def redact(text):
    return _TOKEN.sub(r"\1…", text) if isinstance(text, str) else text


def redact_atoms(atoms):
    """gunicorns log-felter: r = forespørgselslinje, U = sti, f = Referer, plus alle headers ({…}i)."""
    return {k: redact(v) for k, v in atoms.items()}
