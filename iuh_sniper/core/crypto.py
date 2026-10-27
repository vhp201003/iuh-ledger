"""
IUH Password Encryption Engine
Replicates client-side PMTEncryptData using AES-128-CBC with PBKDF2 key derivation.
"""

import hashlib
import binascii
import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding

IUH_IV_HEX = "e84ad660c4721ae0e84ad660c4721ae0"
IUH_PBKDF2_SALT = b"CryptographyPMT-EMS"
IUH_PBKDF2_ITERATIONS = 1000
IUH_KEY_LENGTH = 16  # 128 bits = 16 bytes

def encrypt_iuh_password(raw_password: str, private_key: str) -> str:
    """
    Encrypts raw student password with the dynamic server-issued private_key.
    Returns Base64-encoded ciphertext matching CryptoJS output.
    """
    iv = binascii.unhexlify(IUH_IV_HEX)
    key = hashlib.pbkdf2_hmac(
        "sha1",
        private_key.encode("utf-8"),
        IUH_PBKDF2_SALT,
        IUH_PBKDF2_ITERATIONS,
        dklen=IUH_KEY_LENGTH
    )
    
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(raw_password.encode("utf-8")) + padder.finalize()
    
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()
    
    return base64.b64encode(ciphertext).decode("utf-8")
