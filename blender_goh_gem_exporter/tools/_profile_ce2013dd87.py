from __future__ import annotations

import base64 as _b64
import importlib.resources as _res
import json as _json
import zlib as _zlib

_M = bytes.fromhex('474f4831330a4633ac2cd2b6d86665cf')
_K = bytes.fromhex('e20e7891dad05e65448f86e8832305eaaf91f0375f2ef0f03e48a599f52fe8ea')
_N = bytes.fromhex('c2cf0842b3b9f689b62b86a21d569579')
_C = 'profile_ce2013dd87.bin'
_P = None


def _fold(data: bytes) -> bytes:
    import hashlib as _hashlib
    state = int.from_bytes(_hashlib.sha256(_K + _N).digest()[:8], "little")
    out = bytearray(len(data))
    for index, byte in enumerate(data):
        state = (state * 6364136223846793005 + 1442695040888963407 + index) & ((1 << 64) - 1)
        out[index] = byte ^ _K[index % len(_K)] ^ ((state >> ((index & 7) * 8)) & 0xFF)
    return bytes(out)


def _items() -> dict[str, str]:
    global _P
    if _P is None:
        package_root = __package__.rsplit(".", 1)[0]
        raw = (_res.files(package_root) / "resources" / _C).read_bytes()
        if not raw.startswith(_M):
            raise ImportError("GOH profile cache mismatch")
        _P = _json.loads(_zlib.decompress(_fold(raw[len(_M):])).decode("utf-8"))
    return _P


def attach(module_name: str, namespace: dict[str, object]) -> None:
    short_name = module_name.rsplit(".", 1)[-1]
    encoded = _items().get(short_name)
    if encoded is None:
        raise ImportError(f"GOH profile cache is missing {short_name}")
    namespace.setdefault("__package__", module_name.rsplit(".", 1)[0])
    namespace["__file__"] = f"<{module_name}>"
    source = _b64.b64decode(encoded.encode("ascii")).decode("utf-8")
    exec(compile(source, namespace["__file__"], "exec"), namespace)
