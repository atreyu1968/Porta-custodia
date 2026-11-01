"""Regression tests: encrypted storage, encrypted backups and manual follow-up queue."""
import base64
import io
import os
from datetime import date,timedelta
from email import policy
from email.parser import BytesParser
from pathlib import Path

from fastapi.testclient import TestClient
from app.main import create_app, PH, audit, utcnow
from app.database import db
from app.followup import generate_followups
from app.custody import PREFIX
from tests.test_workflow import PASSWORD, login, post, seed_lending, valid_signed_pdf


def test_v02_encryption_followup_and_inspection(tmp_path,monkeypatch):
    keyfile=tmp_path/'server.key'
    keyfile.write_text(base64.b64encode(os.urandom(32)).decode('ascii'))
    monkeypatch.setenv('PORTACUSTODIA_KEY_FILE',str(keyfile))
    monkeypatch.setenv('PORTACUSTODIA_REQUIRE_ENCRYPTION','1')
    app=create_app(tmp_path/'appdata',secure_cookie=False)
    with db(app.state.dbpath,write=True) as c:
        c.execute("INSERT INTO users(username,full_name,role,password_hash,must_change) VALUES(?,?,?,?,0)",
                  ('admin','Admin Prueba','admin',PH.hash(PASSWORD)))
    with TestClient(app) as client:
        csrf=login(client)
        seed_lending(client,csrf)
        response=post(client,'/prestamos/1/generar/contrato',csrf)
        assert response.status_code==303
        with db(app.state.dbpath) as c:
            document=c.execute('SELECT * FROM documents LIMIT 1').fetchone()
            assert document['encryption']=='aes256gcm'
            file=(app.state.base/'private_documents'/document['stored_name'])
            assert file.read_bytes().startswith(PREFIX)
            assert b'%PDF-' not in file.read_bytes()[:32]
        response=client.get(f'/documentos/{document["id"]}/descargar')
        assert response.status_code==200
        assert response.content.startswith(b'%PDF-')
        post(client,'/prestamos/1/documentos',csrf,{'category':'contrato_firmado'},
             {'file':('signed.pdf',io.BytesIO(valid_signed_pdf()),'application/pdf')})
        post(client,'/prestamos/1/activar',csrf,{'physical_delivery':'on','two_copies_signed':'on','recipient_copy_delivered':'on','copy_recipient':'alumno'})
        with db(app.state.dbpath,write=True) as c:
            c.execute('UPDATE loans SET due_date=? WHERE id=1',((date.today()+timedelta(days=15)).isoformat(),))
            count=generate_followups(c,date.today(),audit,utcnow())
            assert count==1
            assert generate_followups(c,date.today(),audit,utcnow())==0
            task=c.execute('SELECT * FROM followups').fetchone()
            assert task['stage']=='previo15'
        page=client.get('/agenda')
        assert page.status_code==200 and 'Preaviso de devolución' in page.text
        eml=client.get('/agenda/1/borrador.eml')
        assert eml.status_code==200
        email=BytesParser(policy=policy.default).parsebytes(eml.content)
        assert 'alumna@example.edu' in email['To']
        assert 'PENDIENTE DE REVISIÓN' in email.get_content()
        result=post(client,'/agenda/1/gestionar',csrf,{'status':'gestionada','note':'Se llamó y se informó al alumno',
              'channel':'telefono','recipient':'Alumno/a'})
        assert result.status_code==303
        with db(app.state.dbpath) as c:
            assert c.execute("SELECT status FROM followups WHERE id=1").fetchone()['status']=='gestionada'
            assert c.execute('SELECT COUNT(*) FROM notices').fetchone()[0]==1
        assert post(client,'/prestamos/1/revisiones',csrf,{'result':'incidencia','notes':'Bisagra izquierda defectuosa'}).status_code==303
        with db(app.state.dbpath) as c:
            assert c.execute('SELECT COUNT(*) FROM inspections').fetchone()[0]==1
            assert c.execute('SELECT COUNT(*) FROM incidents').fetchone()[0]==1
        export=client.get('/prestamos/1/expediente.zip')
        assert export.status_code==200
        assert b'MANIFIESTO.json' in export.content

    # Encrypted backup, failure on missing key and normal verification with the right key.
    from scripts import backup as backups
    monkeypatch.setattr(backups,'DATA',app.state.base)
    monkeypatch.setattr(backups,'BACKUPS',tmp_path/'backups')
    saved=backups.backup()
    assert saved.suffix=='.pcbak'
    assert saved.read_bytes().startswith(backups.BACKUP_MAGIC)
    assert not saved.read_bytes().startswith(b'PK')
    backups.verify(saved)
    monkeypatch.delenv('PORTACUSTODIA_KEY_FILE')
    try:
        backups.verify(saved)
    except RuntimeError as error:
        assert 'clave' in str(error)
    else:
        raise AssertionError('Una copia cifrada no debe abrirse sin clave')


def test_v01_schema_migrates_without_removing_rows(tmp_path,monkeypatch):
    import sqlite3
    from app.database import initialize
    database=tmp_path/'v01.db'
    # v0.1-like table containing previous document rows.
    c=sqlite3.connect(database)
    c.execute('CREATE TABLE documents (id INTEGER PRIMARY KEY, loan_id INTEGER, created_by INTEGER, created_at TEXT, category TEXT, original_name TEXT, stored_name TEXT, media_type TEXT, sha256 TEXT, size_bytes INTEGER, generated INTEGER NOT NULL DEFAULT 0)')
    c.execute("INSERT INTO documents VALUES(1,1,1,'today','contrato_firmado','firmado.pdf','abc.pdf','application/pdf','x',12,0)")
    c.commit();c.close()
    initialize(database)
    c=sqlite3.connect(database)
    row=c.execute('SELECT id,encryption FROM documents WHERE id=1').fetchone()
    assert row==(1,'none')
    c.close()
