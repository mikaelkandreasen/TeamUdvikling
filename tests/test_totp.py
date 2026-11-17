import base64

from app import totp


def test_rfc6238_sha1_vector():
    secret = base64.b32encode(b"12345678901234567890").decode()
    assert totp.hotp(secret, 59 // 30, digits=8) == "94287082"
    assert totp.hotp(secret, 1111111109 // 30, digits=8) == "07081804"


def test_verify_window_and_replay():
    s = totp.new_secret()
    t = 1_700_000_000
    code = totp.totp(s, t)
    step = totp.verify(s, code, 0, t=t)
    assert step == t // 30
    assert totp.verify(s, code, step, t=t) is None          # replay afvist
    assert totp.verify(s, totp.totp(s, t + 30), 0, t=t) is not None   # ±1 tidstrin tilladt
    assert totp.verify(s, totp.totp(s, t + 120), 0, t=t) is None
    assert totp.verify(s, "abc123", 0, t=t) is None
