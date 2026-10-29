import os
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from src.config import settings

def _get_key_bytes() -> bytes:
    key_str = settings.app_encryption_key
    try:
        if len(key_str) == 64:
            return bytes.fromhex(key_str)
    except ValueError:
        pass
    return hashlib.sha256(key_str.encode("utf-8")).digest()

def encrypt_text(plaintext: str) -> bytes:
    key = _get_key_bytes()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return nonce + ciphertext

def decrypt_text(ciphertext_bytes: bytes) -> str:
    key = _get_key_bytes()
    aesgcm = AESGCM(key)
    nonce = ciphertext_bytes[:12]
    data = ciphertext_bytes[12:]
    decrypted = aesgcm.decrypt(nonce, data, None)
    return decrypted.decode("utf-8")
