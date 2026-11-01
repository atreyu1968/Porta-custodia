"""Regression tests for handwritten signing and the school's institutional mail domain."""
from datetime import date, timedelta
from email import policy
from email.parser import BytesParser
import sqlite3

import pytest
from fastapi.testclient import TestClient
from app.contact import configured_sender, valid_staff_email
from app.database import db, initialize
from app.main import PH, create_app, audit, utcnow
from tests.test_workflow import PASSWORD, login, post, seed_lending
from app.followup import generate_followups


def test_domain_and_sender_are_strict(monkeypatch,tmp_path):
    assert valid_staff_email('usuario@canariaseducacion.es')
    assert valid_staff_email('usuario.prueba@canariaseducacion.es')
    for wrong in ('usuario@gmail.com','usuario@sub.canariaseducacion.es',
                  'a@canariaseducacion.es\nBcc:otro@example.com', 'usuario@canariaseducacion.es.evil.example', ''):
        assert not valid_staff_email(wrong)
    monkeypatch.setenv('PORTACUSTODIA_CORREO_ORIGEN','suplantado@gmail.com')
    with pytest.raises(RuntimeError,match='canariaseducacion.es'):
        create_app(tmp_path/'bad',secure_cookie=False)
    monkeypatch.setenv('PORTACUSTODIA_CORREO_ORIGEN','departamento@canariaseducacion.es')
    assert configured_sender()=='departamento@canariaseducacion.es'


def test_users_domain_validation_and_migration(tmp_path):
    dbfile=tmp_path/'old-users.sqlite3'
    c=sqlite3.connect(dbfile)
    c.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, role TEXT, tutor_group TEXT, password_hash TEXT, must_change INTEGER, active INTEGER, created_at TEXT)')
    c.execute("INSERT INTO users VALUES (1,'before','Antes','admin','','hash',0,1,'2026-11-01')")
    c.commit();c.close()
    initialize(dbfile)
    with db(dbfile) as c:
        assert c.execute('SELECT institutional_email FROM users WHERE id=1').fetchone()['institutional_email']==''
    # New database permits assigning an institutional email to new staff accounts.
    app=create_app(tmp_path/'new',secure_cookie=False)
    with db(app.state.dbpath,write=True) as c:
        c.execute("INSERT INTO users(username,full_name,role,password_hash,must_change) VALUES(?,?,?,?,0)",
                  ('admin','Administrador','admin',PH.hash(PASSWORD)))
    with TestClient(app) as client:
        csrf=login(client)
        ordinary={'username':'usuario1','full_name':'Personal de prueba','role':'tic','password':PASSWORD}
        bad=post(client,'/usuarios',csrf,{**ordinary,'institutional_email':'personal@ejemplo.com'})
        assert bad.status_code==303
        assert 'canariaseducacion.es' in bad.headers['location']
        with db(app.state.dbpath) as c:
            assert c.execute("SELECT COUNT(*) FROM users WHERE username='usuario1'").fetchone()[0]==0
        good=post(client,'/usuarios',csrf,{**ordinary,'institutional_email':'personal@canariaseducacion.es'})
        assert good.status_code==303
        with db(app.state.dbpath) as c:
            assert c.execute("SELECT institutional_email FROM users WHERE username='usuario1'").fetchone()[0]=='personal@canariaseducacion.es'
        changed=post(client,'/usuarios/2/correo',csrf,{'institutional_email':'personal.nuevo@canariaseducacion.es'})
        assert changed.status_code==303
        with db(app.state.dbpath) as c:
            assert c.execute('SELECT institutional_email FROM users WHERE id=2').fetchone()[0]=='personal.nuevo@canariaseducacion.es'


def test_eml_draft_from_institutional_account_and_no_mail_for_minors(tmp_path,monkeypatch):
    monkeypatch.setenv('PORTACUSTODIA_CORREO_ORIGEN','pruebas@canariaseducacion.es')
    app=create_app(tmp_path/'data',secure_cookie=False)
    with db(app.state.dbpath,write=True) as c:
        c.execute("INSERT INTO users(username,full_name,role,password_hash,must_change) VALUES(?,?,?,?,0)",
                  ('admin','Administrador','admin',PH.hash(PASSWORD)))
    with TestClient(app) as client:
        csrf=login(client)
        seed_lending(client,csrf)
        with db(app.state.dbpath,write=True) as c:
            c.execute("UPDATE loans SET due_date=?,state='activo',activated_at=? WHERE id=1",
                      ((date.today()+timedelta(days=15)).isoformat(),utcnow()))
            c.execute("UPDATE devices SET status='prestado' WHERE id=1")
            assert generate_followups(c,date.today(),audit,utcnow())==1
        draft=client.get('/agenda/1/borrador.eml')
        assert draft.status_code==200
        parsed=BytesParser(policy=policy.default).parsebytes(draft.content)
        assert parsed['From']=='pruebas@canariaseducacion.es'
        assert parsed['To']=='alumna@example.edu'   # Student contacts need not have the staff domain.
        assert 'BORRADOR PENDIENTE' in parsed.get_content()
        with db(app.state.dbpath,write=True) as c:
            c.execute('UPDATE students SET minor=1 WHERE id=1')
        minor_draft=client.get('/agenda/1/borrador.eml')
        minor=BytesParser(policy=policy.default).parsebytes(minor_draft.content)
        assert minor['From']=='pruebas@canariaseducacion.es'
        assert minor['To'] is None  # Current minor status takes precedence for correspondence.
        with db(app.state.dbpath) as c:
            assert c.execute('SELECT COUNT(*) FROM notices').fetchone()[0]==0
            assert c.execute("SELECT COUNT(*) FROM audit WHERE action='borrador_correo_descargado'").fetchone()[0]==2
