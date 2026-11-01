"""Coherent verifiable backups; encrypted .pcbak when custody key is configured.

The key lives OUTSIDE the backup. The administrator must back it up securely and
separately. Restore can only be performed by an authorised operator.
"""
import argparse
import hashlib
import io
import json
import os
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.database import connect
from app.custody import key_from_environment, document_bytes
from app.main import verify_audit

BACKUP_MAGIC=b'PCBACK01'
DATA=Path(os.environ.get('PORTACUSTODIA_DATA','./data')).resolve()
BACKUPS=Path(os.environ.get('PORTACUSTODIA_BACKUPS','./backups')).resolve()

def hashbytes(b):return hashlib.sha256(b).hexdigest()

def backup():
    key=key_from_environment()
    if os.environ.get('PORTACUSTODIA_REQUIRE_ENCRYPTION','0')=='1' and not key:
        raise RuntimeError('Copia bloqueada: falta la clave de cifrado obligatoria.')
    BACKUPS.mkdir(parents=True,exist_ok=True)
    os.chmod(BACKUPS,0o700)
    extension='pcbak' if key else 'zip'
    target=BACKUPS/f'portacustodia_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.{extension}'
    with tempfile.TemporaryDirectory() as temporary:
        snapshot=Path(temporary)/'portacustodia.sqlite3'
        source=connect(DATA/'portacustodia.sqlite3')
        try:
            good,broken=verify_audit(source)
            if not good:raise RuntimeError(f'Auditoría alterada en evento #{broken}; intervención necesaria.')
            dest=sqlite3.connect(snapshot)
            try:source.backup(dest)
            finally:dest.close()
        finally:source.close()
        sconn=connect(snapshot)
        try:docs=list(sconn.execute('SELECT stored_name,sha256,encryption FROM documents'))
        finally:sconn.close()
        manifest={'created_at':datetime.now(timezone.utc).isoformat(),'application':'PortaCustodia',
                  'files':[],'encrypted':bool(key),
                  'warning':'Datos personales. Mantener la clave de descifrado separada y protegida.'}
        archive=io.BytesIO()
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            db_bytes=snapshot.read_bytes()
            z.writestr('database/portacustodia.sqlite3',db_bytes)
            manifest['files'].append({'path':'database/portacustodia.sqlite3','sha256':hashbytes(db_bytes),'size':len(db_bytes)})
            for doc in docs:
                path=DATA/'private_documents'/doc['stored_name']
                if not path.is_file():raise RuntimeError(f'Falta documento: {doc["stored_name"]}')
                document_bytes(path,doc,key)  # Verify original SHA-256 AND GCM auth tag.
                stored=path.read_bytes()
                name='private_documents/'+doc['stored_name']
                z.writestr(name,stored)
                manifest['files'].append({'path':name,'sha256':hashbytes(stored),'size':len(stored)})
            z.writestr('MANIFIESTO_COPIA.json',json.dumps(manifest,ensure_ascii=False,indent=2))
        contents=archive.getvalue()
        if key:
            nonce=os.urandom(12)
            contents=BACKUP_MAGIC+nonce+AESGCM(key).encrypt(nonce,contents,BACKUP_MAGIC)
        tmp=target.with_name(target.name+'.part')
        with tmp.open('xb') as f:
            os.chmod(tmp,0o600)
            f.write(contents);f.flush();os.fsync(f.fileno())
        tmp.replace(target)
    verify(target)
    print('Copia generada:',target)
    return target

def opened_archive(path):
    content=Path(path).read_bytes()
    if content.startswith(BACKUP_MAGIC):
        key=key_from_environment()
        if key is None:raise RuntimeError('Falta la clave para verificar una copia cifrada.')
        nonce=content[len(BACKUP_MAGIC):len(BACKUP_MAGIC)+12]
        content=AESGCM(key).decrypt(nonce,content[len(BACKUP_MAGIC)+12:],BACKUP_MAGIC)
    return io.BytesIO(content)

def verify(path):
    with zipfile.ZipFile(opened_archive(path),'r') as z:
        manifest=json.loads(z.read('MANIFIESTO_COPIA.json'))
        for d in manifest['files']:
            if hashbytes(z.read(d['path']))!=d['sha256']:raise RuntimeError('Huella incorrecta: '+d['path'])
        print('Copia verificada:',len(manifest['files']),'archivos; fecha',manifest['created_at'])

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['backup','verify'])
    parser.add_argument('file',nargs='?');args=parser.parse_args()
    if args.command=='backup':backup()
    else:
        if not args.file:parser.error('Indica la ruta del archivo.')
        verify(args.file)
