import base64
import os

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


ARGON_TIME = 3
ARGON_MEMORY = 65536
ARGON_PARALLELISM = 2


def encode(data):
    return base64.b64encode(data).decode("ascii")


def decode(data):
    return base64.b64decode(data, validate=True)


def derive_key(password, salt, memory=ARGON_MEMORY):
    return bytearray(hash_secret_raw(password.encode("utf-8"), salt, ARGON_TIME, memory, ARGON_PARALLELISM, 32, Type.ID))


def encrypt(key, plaintext, associated_data):
    nonce = os.urandom(12)
    ciphertext = AESGCM(bytes(key)).encrypt(nonce, plaintext, associated_data)
    return {"nonce": encode(nonce), "data": encode(ciphertext)}


def decrypt(key, record, associated_data):
    return AESGCM(bytes(key)).decrypt(decode(record["nonce"]), decode(record["data"]), associated_data)


def wipe(value):
    if value is not None:
        value[:] = b"\x00" * len(value)
