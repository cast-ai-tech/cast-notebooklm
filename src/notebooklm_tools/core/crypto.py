"""AES-256-GCM encryption for credentials at rest.

Python port of roomi-fields/notebooklm-mcp's src/accounts/crypto.ts (MIT
licensed, see CREDITS.md). Same key-resolution hierarchy and the same
"<iv_hex>:<tag_hex>:<ciphertext_hex>" interchange format; the nonce length
is 12 bytes (96 bits) here instead of that project's 16, following the
AES-GCM nonce size recommended by NIST SP 800-38D and used by
`cryptography`'s AESGCM helper -- this is a from-scratch Python
implementation, not wire-compatible with the TypeScript original.

Key resolution order:
1. CAST_NLM_ENCRYPTION_KEY env var (64 hex chars = 256 bits)
2. <storage_dir>/encryption.key (64 hex chars, created on first use)
3. Freshly generated random key, persisted to that file (mode 0o600)

There is no password-derived key (no PBKDF2/scrypt) -- the key is either
supplied directly via env var or is opaque random material. Losing the key
file without a backed-up env var value makes existing encrypted credentials
unrecoverable; callers are warned about this when a key is first generated.
"""

import logging
import os
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

KEY_LENGTH = 32  # 256-bit key
NONCE_LENGTH = 12  # 96-bit nonce, recommended size for AES-GCM
TAG_LENGTH = 16  # 128-bit auth tag, appended by AESGCM.encrypt()
KEY_ENV_VAR = "CAST_NLM_ENCRYPTION_KEY"
KEY_FILE_NAME = "encryption.key"


class EncryptionKeyError(Exception):
    """Raised when the encryption key or an encrypted payload is malformed."""


def _key_file_path() -> Path:
    from notebooklm_tools.utils.config import get_storage_dir

    return get_storage_dir() / KEY_FILE_NAME


def _parse_hex_key(hex_key: str, *, source: str) -> bytes:
    try:
        key = bytes.fromhex(hex_key.strip())
    except ValueError as e:
        raise EncryptionKeyError(f"{source} must be {KEY_LENGTH * 2} hex characters") from e
    if len(key) != KEY_LENGTH:
        raise EncryptionKeyError(
            f"{source} must decode to {KEY_LENGTH} bytes (256 bits), got {len(key)}"
        )
    return key


def _load_key_from_file(path: Path) -> bytes | None:
    if not path.exists():
        return None
    return _parse_hex_key(path.read_text(encoding="utf-8"), source=str(path))


def _generate_and_persist_key(path: Path) -> bytes:
    key = os.urandom(KEY_LENGTH)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        f = os.fdopen(fd, "w", encoding="utf-8")
    except BaseException:
        os.close(fd)
        raise
    with f:
        f.write(key.hex())
    logger.warning(
        f"Generated new credential encryption key at {path}. "
        "Back up this file (or set CAST_NLM_ENCRYPTION_KEY) -- losing it makes "
        "existing encrypted credentials unrecoverable."
    )
    return key


def get_encryption_key() -> bytes:
    """Resolve the AES-256 key: env var -> key file -> generate+persist."""
    env_key = os.environ.get(KEY_ENV_VAR)
    if env_key:
        return _parse_hex_key(env_key, source=KEY_ENV_VAR)

    path = _key_file_path()
    key = _load_key_from_file(path)
    if key is not None:
        return key

    return _generate_and_persist_key(path)


def encrypt(plaintext: str, key: bytes | None = None) -> str:
    """Encrypt plaintext, returning '<iv_hex>:<tag_hex>:<ciphertext_hex>'."""
    key = key if key is not None else get_encryption_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(NONCE_LENGTH)
    ct_with_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    ciphertext, tag = ct_with_tag[:-TAG_LENGTH], ct_with_tag[-TAG_LENGTH:]
    return f"{nonce.hex()}:{tag.hex()}:{ciphertext.hex()}"


def decrypt(token: str, key: bytes | None = None) -> str:
    """Decrypt a '<iv_hex>:<tag_hex>:<ciphertext_hex>' token back to plaintext."""
    key = key if key is not None else get_encryption_key()
    parts = token.split(":")
    if len(parts) != 3:
        raise EncryptionKeyError("Malformed encrypted payload: expected 'iv:tag:ciphertext'")
    nonce_hex, tag_hex, ct_hex = parts
    try:
        nonce = bytes.fromhex(nonce_hex)
        tag = bytes.fromhex(tag_hex)
        ciphertext = bytes.fromhex(ct_hex)
    except ValueError as e:
        raise EncryptionKeyError("Malformed encrypted payload: expected hex segments") from e

    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext + tag, None)
    except InvalidTag as e:
        raise EncryptionKeyError(
            "Failed to decrypt credential payload: authentication tag mismatch "
            "(wrong encryption key, or the data was tampered with/corrupted)"
        ) from e
    return plaintext.decode("utf-8")


def verify_encryption() -> bool:
    """Round-trip self-test. Mirrors roomi-fields' verifyEncryption()."""
    probe = "cast-notebooklm-encryption-selftest"
    return decrypt(encrypt(probe)) == probe
