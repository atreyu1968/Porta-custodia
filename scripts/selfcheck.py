"""Prueba postinstalación aislada: solo utiliza datos ficticios en tempfile."""
from __future__ import annotations
import io,os,tempfile
from datetime import date,timedelta
from pathlib import Path
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from app.main import create_app,PH
from app.database import db


def run():
    # Nunca se emplean la BD ni los archivos de datos operativos.
    env_saved={k:os.environ.get(k) for k in (
        'PORTACUSTODIA_REQUIRE_LEGAL_CONFIG','PORTACUSTODIA_RESPONSABLE_DATOS',
        'PORTACUSTODIA_CONTACTO_DPD','PORTACUSTODIA_PRIVACIDAD_URL','PORTACUSTODIA_RETENCION')}
    os.environ.update(PORTACUSTODIA_REQUIRE_LEGAL_CONFIG='0',
        PORTACUSTODIA_RESPONSABLE_DATOS='ENTIDAD FICTICIA - PRUEBA',
        PORTACUSTODIA_CONTACTO_DPD='dpd@invalid.test',
        PORTACUSTODIA_PRIVACIDAD_URL='https://example.invalid/privacidad',
        PORTACUSTODIA_RETENCION='Prueba temporal que se elimina')
    try:
        with tempfile.TemporaryDirectory(prefix='pc-selfcheck-') as tmp:
            app=create_app(tmp,secure_cookie=False)
            with db(app.state.dbpath,write=True) as c:
                c.execute('INSERT INTO users(username,full_name,role,password_hash,must_change) VALUES(?,?,?,?,0)',
                          ('prueba','Usuario ficticio','admin',PH.hash('ClavePruebaTemporal2026!')))
            with TestClient(app) as client:
                assert client.get('/salud').json()['estado']=='ok'
                assert client.get('/manifest.webmanifest').status_code==200
                assert client.get('/panel',follow_redirects=False).status_code==303
                r=client.post('/login',data={'username':'prueba','password':'ClavePruebaTemporal2026!'},follow_redirects=False)
                assert r.status_code==303 and 'pc_session' in client.cookies
                import hashlib
                with db(app.state.dbpath) as c:
                    sid=hashlib.sha256(client.cookies['pc_session'].encode()).hexdigest()
                    csrf=c.execute('SELECT csrf FROM sessions WHERE token_hash=?',(sid,)).fetchone()['csrf']
                def post(path,fields):
                    r=client.post(path,data=dict(fields,csrf=csrf),follow_redirects=False)
                    assert r.status_code==303,(path,r.status_code,r.text[:100]);return r
                post('/equipos',{'asset_tag':'TEST-001','serial_number':'SERIE-FICTICIA-001',
                                 'brand':'Marca ficticia','model':'Modelo de prueba'})
                post('/alumnos',{'student_ref':'TEST-ALUMNO','full_name':'Persona ficticia',
                                 'course_group':'PRUEBA - NO REAL'})
                post('/prestamos',{'student_id':'1','device_id':'1',
                    'due_date':(date.today()+timedelta(days=65)).isoformat(),
                    'purpose':'Verificación automatizada del instalador','delivery_condition':'Sin desperfectos'})
                assert client.get('/prestamos/1').status_code==200
                assert post('/prestamos/1/generar/contrato',{}).status_code==303
                with db(app.state.dbpath) as c:
                    d=c.execute("SELECT id FROM documents WHERE category='contrato_generado'").fetchone()
                    assert d is not None
                    if app.state.custody_key is not None:
                        detail=c.execute('SELECT encryption,stored_name FROM documents WHERE id=?',(d['id'],)).fetchone()
                        assert detail['encryption']=='aes256gcm', 'El cifrado documental no está activo'
                        assert (app.state.base/'private_documents'/detail['stored_name']).read_bytes().startswith(b'PCAES01')
                content=client.get('/documentos/'+str(d['id'])+'/descargar')
                assert content.status_code==200 and content.content.startswith(b'%PDF-')
                assert client.get('/movil').status_code==200
                assert client.get('/equipos').status_code==200
                assert client.get('/agenda').status_code==200
            print('SELFTEST OK: salud, PWA, autenticación, permisos, inventario, alumno, préstamo, PDF y expediente.')
    finally:
        for k,v in env_saved.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v

if __name__=='__main__':run()
