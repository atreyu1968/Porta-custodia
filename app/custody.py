"""Authenticated at-rest document encryption with separately managed AES-256-GCM key.

Document hash always records SHA-256 of original plaintext. Ciphertext is prefixed
with a versioned magic plus a random 12-byte nonce, and bound to the document ID
independent UUID via encrypted object name as associated data.
"""
import base64
import hashlib
import os
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PREFIX=b'PCAES01\x00'


def key_from_environment():
    path=os.environ.get('PORTACUSTODIA_KEY_FILE','').strip()
    if not path:
        return None
    content=Path(path).read_text(encoding='ascii').strip()
    try:
        key=base64.b64decode(content,validate=True)
    except Exception as e:
        raise RuntimeError('La clave documental no tiene formato base64 válido.') from e
    if len(key)!=32:
        raise RuntimeError('La clave documental debe tener 32 bytes.')
    return key


def encrypt_document(blob,filename,key):
    nonce=os.urandom(12)
    return PREFIX+nonce+AESGCM(key).encrypt(nonce,blob,filename.encode('ascii'))


def decrypt_document(blob,filename,key):
    if not key:
        raise RuntimeError('No se ha configurado la clave de custodia.')
    if not blob.startswith(PREFIX) or len(blob)<len(PREFIX)+12+16:
        raise ValueError('Formato de documento cifrado incorrecto.')
    start=len(PREFIX)
    nonce=blob[start:start+12]
    return AESGCM(key).decrypt(nonce,blob[start+12:],filename.encode('ascii'))


def document_bytes(path, record, key=None):
    stored=path.read_bytes()
    if record['encryption']=='aes256gcm':
        clear=decrypt_document(stored,record['stored_name'],key)
    elif record['encryption']=='none':
        clear=stored
    else:
        raise ValueError('Cifrado documental desconocido.')
    if hashlib.sha256(clear).hexdigest()!=record['sha256']:
        raise ValueError('El contenido no coincide con la huella original.')
    return clear
