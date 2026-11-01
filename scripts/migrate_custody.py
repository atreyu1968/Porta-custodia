"""Operator-run migration for v0.1 plaintext records to AES-256-GCM.

Create a verified backup first. Each document is atomically updated in the DB
only after encrypted ciphertext is durably stored. Avoid running with live writes.
"""
import argparse
import hashlib
import os
import uuid
from pathlib import Path
from app.database import db,initialize
from app.custody import key_from_environment, encrypt_document
from app.main import audit

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');args=p.parse_args()
    base=Path(os.environ.get('PORTACUSTODIA_DATA','./data')).resolve()
    database=base/'portacustodia.sqlite3'
    initialize(database)
    key=key_from_environment()
    if not key:raise SystemExit('Falta PORTACUSTODIA_KEY_FILE.')
    with db(database) as c:
        pending=c.execute("SELECT id FROM documents WHERE encryption='none'").fetchall()
    print(f'Hay {len(pending)} documentos antiguos sin cifrar.')
    if not args.apply:
        print('No se realizaron cambios. Detenga el servicio, haga copia verificada y vuelva a ejecutar --apply.')
        raise SystemExit(0)
    for item in pending:
        # One transaction per file, original survives up until commit.
        old_to_remove=None
        with db(database,write=True) as c:
            doc=c.execute('SELECT * FROM documents WHERE id=?',(item['id'],)).fetchone()
            if not doc or doc['encryption']!='none':continue
            original=base/'private_documents'/doc['stored_name']
            data=original.read_bytes()
            if hashlib.sha256(data).hexdigest()!=doc['sha256']:
                raise RuntimeError(f'Huella incorrecta del documento {doc["id"]}.')
            newname=f'{uuid.uuid4().hex}.enc'
            target=base/'private_documents'/newname
            ciphertext=encrypt_document(data,newname,key)
            with target.open('xb') as f:
                os.chmod(target,0o600);f.write(ciphertext);f.flush();os.fsync(f.fileno())
            try:
                c.execute("UPDATE documents SET stored_name=?,encryption='aes256gcm' WHERE id=?",(newname,doc['id']))
                audit(c,None,'documento_cifrado','documento',doc['id'],{'sha256':doc['sha256']})
            except Exception:
                target.unlink(missing_ok=True)
                raise
            old_to_remove=original
        if old_to_remove:
            old_to_remove.unlink()
    print('Conversión completada. Crear nueva copia cifrada y comprobar la restauración.')
