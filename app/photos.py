"""Spillerbilleder: valider, beskær til kvadrat, fjern EXIF/GPS (genkodning) og lav miniature. Ingen filer på disken – billedet gemmes i databasen
og slettes automatisk sammen med spilleren. Kun JPEG/PNG/WebP accepteres; indholdet afgøres af Pillow, aldrig af filnavn eller Content-Type."""
import io

from PIL import Image, ImageOps

MAX_UPLOAD = 12 * 1024 * 1024        # bytes (en moderne telefonfoto)
MAX_PIXELS = 40_000_000              # afviser dekompressionsbomber, før billedet dekodes
MIN_SIDE = 64
FULL, THUMB = 480, 96
ALLOWED = {"JPEG", "PNG", "WEBP"}
Image.MAX_IMAGE_PIXELS = MAX_PIXELS * 2


class PhotoError(ValueError):
    """Brugerfejl med en dansk besked, som kan vises direkte."""


def _jpeg(img, size):
    out = io.BytesIO()
    # Centrering lidt over midten, så ansigter på portrætbilleder ikke beskæres væk. Ingen exif/icc videregives.
    ImageOps.fit(img, (size, size), Image.LANCZOS, centering=(0.5, 0.35)).save(out, "JPEG", quality=85, optimize=True)
    return out.getvalue()


def process(data):
    """Returnerer (stor, miniature) som JPEG-bytes. Rejser PhotoError ved ugyldige billeder."""
    if not data:
        raise PhotoError("Vælg en billedfil.")
    if len(data) > MAX_UPLOAD:
        raise PhotoError("Billedet er for stort (maks. 12 MB).")
    try:
        img = Image.open(io.BytesIO(data))
        fmt, (w, h) = img.format, img.size
    except Exception:
        raise PhotoError("Filen er ikke et billede, der kan læses.")
    if fmt not in ALLOWED:
        raise PhotoError("Kun JPEG-, PNG- og WebP-billeder kan bruges.")
    if w * h > MAX_PIXELS:
        raise PhotoError("Billedet har for mange pixels.")
    if min(w, h) < MIN_SIDE:
        raise PhotoError("Billedet er for lille.")
    try:
        if fmt == "JPEG":
            img.draft("RGB", (FULL * 2, FULL * 2))           # dekod i lavere opløsning: hurtigt og sparer hukommelse
        img = ImageOps.exif_transpose(img)                    # respekter kameraets rotation, før metadata smides væk
        if img.mode in ("RGBA", "LA", "P"):
            rgba = img.convert("RGBA")
            bg = Image.new("RGB", rgba.size, (255, 255, 255))
            bg.paste(rgba, mask=rgba.split()[3])
            img = bg
        else:
            img = img.convert("RGB")
        return _jpeg(img, FULL), _jpeg(img, THUMB)
    except PhotoError:
        raise
    except Exception:
        raise PhotoError("Billedet kunne ikke behandles.")


def process_free(data, max_side=600):
    """Maskot-/illustrationsbillede: samme kontrol som spillerbilleder, men uden beskæring (bevarer formatet). Returnerer JPEG-bytes (hvid baggrund)."""
    if not data:
        raise PhotoError("Vælg en billedfil.")
    if len(data) > MAX_UPLOAD:
        raise PhotoError("Billedet er for stort (maks. 12 MB).")
    try:
        img = Image.open(io.BytesIO(data))
        fmt, (w, h) = img.format, img.size
    except Exception:
        raise PhotoError("Filen er ikke et billede, der kan læses.")
    if fmt not in ALLOWED:
        raise PhotoError("Kun JPEG-, PNG- og WebP-billeder kan bruges.")
    if w * h > MAX_PIXELS:
        raise PhotoError("Billedet har for mange pixels.")
    if min(w, h) < MIN_SIDE:
        raise PhotoError("Billedet er for lille.")
    try:
        img = ImageOps.exif_transpose(img)
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[3])
        bg.thumbnail((max_side, max_side), Image.LANCZOS)
        out = io.BytesIO()
        bg.save(out, "JPEG", quality=88, optimize=True)
        return out.getvalue()
    except Exception:
        raise PhotoError("Billedet kunne ikke behandles.")
