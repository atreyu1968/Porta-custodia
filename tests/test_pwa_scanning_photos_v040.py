"""New v0.4 acceptance tests: mobile scan, photo retention, group ACL, compatibility."""
import io, hashlib, json, sqlite3
from pathlib import Path
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from app.main import create_app, PH
from app.database import db, SCHEMA

PASS='ClaveDePruebasSegura_2026_04'

@pytest.fixture
def users(tmp_path):
    app=create_app(tmp_path,secure_cookie=False)
    with db(app.state.dbpath,True) as c:
        for user,role,group in [('admin','admin',''),('g1','gestor','1GA'),('g2','gestor','2GA'),('t1','tutor','1GA'),('tc','tic',''),('readonly','consulta','')]:
            c.execute('INSERT INTO users(username,full_name,role,tutor_group,password_hash,must_change) VALUES(?,?,?,?,?,0)',
                      (user,user,role,group,PH.hash(PASS)))
        for num in (1,2):
            c.execute('INSERT INTO students(student_ref,full_name,course_group) VALUES(?,?,?)',(f'A{num}',f'Alumna {num}',f'{num}GA'))
            c.execute('INSERT INTO devices(asset_tag,serial_number,brand,model) VALUES(?,?,?,?)',(f'PC-{num}',f'SN-{num}','HP','ProBook'))
        c.execute("""INSERT INTO loans(student_id,device_id,created_by,created_at,due_date,last_modified,state,activated_at)
                   VALUES(1,1,1,'2026-10-30','2027-06-01','2026-10-30','activo','2026-10-30')""")
        c.execute("""INSERT INTO loans(student_id,device_id,created_by,created_at,due_date,last_modified,state,activated_at)
                   VALUES(2,2,1,'2026-10-30','2027-06-01','2026-10-30','activo','2026-10-30')""")
        c.execute("UPDATE devices SET status='prestado'")
    with TestClient(app) as client: yield client,app

def login(client,username):
    client.cookies.clear()
    r=client.post('/login',data={'username':username,'password':PASS},follow_redirects=False)
    assert r.status_code==303
    with db(client.app.state.dbpath) as c:
        row=c.execute('SELECT csrf FROM sessions WHERE user_id=(SELECT id FROM users WHERE username=?) ORDER BY rowid DESC LIMIT 1',(username,)).fetchone()
    return row['csrf']

def picture():
    b=io.BytesIO();Image.new('RGB',(320,200),(160,208,222)).save(b,format='JPEG',exif=Image.Exif().tobytes())
    return b.getvalue()

def upload(client,csrf,device=1,loan='1',category='revision',pic=None):
    return client.post(f'/equipos/{device}/fotos',data={'csrf':csrf,'loan_id':loan,'category':category,'note':'Fotografía externa de prueba'},
        files={'photo':('camara.jpg',io.BytesIO(pic or picture()),'image/jpeg')},follow_redirects=False)

def test_pwa_and_device_scan(users):
    client,_=users;csrf=login(client,'admin')
    html=client.get('/movil').text
    assert 'Escanear un portátil' in html and 'data-scan-photo' in html
    assert client.get('/manifest.webmanifest').json()['start_url']=='/movil'
    assert client.get('/sw.js').status_code==200
    sw=client.get('/sw.js').text
    assert "ASSETS.includes(path)" in sw and 'sensitive content' in sw
    assert client.get('/static/mobile.js').status_code==200
    result=client.get('/api/equipos/buscar?codigo=SN-1').json()
    assert result['found'] and result['id']==1
    assert client.get('/api/equipos/buscar?codigo=unknown').json()['found'] is False
    assert client.get('/equipos/1').status_code==200

def test_photos_acl_and_export(users):
    client,app=users;csrf=login(client,'t1')
    assert upload(client,csrf,1,'1').status_code==303
    assert upload(client,csrf,2,'2').status_code==404
    assert upload(client,csrf,1,'',category='inventario').status_code==403
    with db(app.state.dbpath) as c:
        photos=c.execute('SELECT * FROM device_photos').fetchall()
        assert len(photos)==1
        sha=photos[0]['sha256']
        saved=app.state.base/'private_documents'/photos[0]['stored_name']
        assert sha==hashlib.sha256(saved.read_bytes()).hexdigest()
        assert photos[0]['width']==320
    assert client.get('/fotos/1').status_code==200
    assert client.get('/fotos/1').headers['content-type'].startswith('image/jpeg')
    assert client.get('/fotos/2').status_code==404
    assert client.get('/prestamos/2').status_code==404
    assert 'Fotografías de la unidad' in client.get('/prestamos/1').text
    csrf=login(client,'g2')
    assert client.get('/fotos/1').status_code==404
    assert client.get('/prestamos/1/expediente.zip').status_code==404
    assert upload(client,csrf,1,'1').status_code==404
    csrf=login(client,'admin')
    exported=client.get('/prestamos/1/expediente.zip')
    assert exported.status_code==200
    import zipfile
    with zipfile.ZipFile(io.BytesIO(exported.content)) as z:
        manifest=json.loads(z.read('MANIFIESTO.json'))
        assert len(manifest['photos'])==1
        info=manifest['photos'][0]
        assert hashlib.sha256(z.read(info['zip_path'])).hexdigest()==info['sha256']
    saved.write_bytes(b'CORRUPTED')
    assert client.get('/fotos/1').status_code==409
    assert client.get('/prestamos/1/expediente.zip').status_code==409

def test_manager_scoped_actions_and_anti_csrf(users):
    client,app=users;csrf=login(client,'g1')
    assert client.get('/prestamos/nuevo').status_code==200
    assert client.get('/agenda').status_code==200
    assert client.get('/alumnos').status_code==403
    assert client.post('/equipos/1/fotos',data={'csrf':'invalid','loan_id':'1','category':'revision','note':'Al menos cuatro'},
      files={'photo':('a.jpg',picture(),'image/jpeg')}).status_code==403
    # Group 1 manager cannot close other group's loan.
    r=client.post('/prestamos/2/devolver',data={'csrf':csrf,'condition':'Equipo correcto','accessories':'Cargador','result':'correcto'},follow_redirects=False)
    assert r.status_code==404
    # Nor download a draft / modify unrelated agenda tasks.
    assert client.get('/prestamos/2').status_code==404
    csrf=login(client,'readonly')
    assert upload(client,csrf,1,'1').status_code==403

def test_photo_invalid_and_barcode_photo(users):
    client,app=users;csrf=login(client,'admin')
    assert upload(client,csrf,pic=b'not-a-jpeg').status_code==303
    with db(app.state.dbpath) as c:
        assert c.execute('SELECT COUNT(*) FROM device_photos').fetchone()[0]==0
    import qrcode
    image=qrcode.make('SN-1').convert('RGB');image=image.resize((520,520))
    b=io.BytesIO();image.save(b,format='PNG')
    r=client.post('/api/equipos/decodificar-codigo',data={'csrf':csrf},files={'photo':('codigo.png',b.getvalue(),'image/png')})
    assert r.status_code==200,r.text
    assert any(c['value']=='SN-1' for c in r.json()['codes']),r.json()
    # Transient scanning image is never persisted as photographic evidence.
    with db(app.state.dbpath) as c:
        assert c.execute('SELECT COUNT(*) FROM device_photos').fetchone()[0]==0

def test_migrate_v03_users_to_gestor(tmp_path):
    # Mimics the old SQLite role CHECK. Child loan FK remains intact after migration.
    import sys
    schema=SCHEMA.replace("'tutor','gestor','consulta'","'tutor','consulta'")
    target=tmp_path/'portacustodia.sqlite3'; c=sqlite3.connect(target)
    c.executescript(schema)
    c.execute("INSERT INTO users(username,full_name,role,password_hash,must_change) VALUES('admin','Admin','admin','hash',0)")
    c.commit();c.close()
    app=create_app(tmp_path,secure_cookie=False)
    with db(app.state.dbpath,True) as c:
        assert 'gestor' in c.execute("SELECT sql FROM sqlite_master WHERE name='users'").fetchone()['sql']
        c.execute("INSERT INTO users(username,full_name,role,tutor_group,password_hash,must_change) VALUES('prof','Profesor','gestor','1GA','hash',0)")
        assert c.execute('PRAGMA foreign_key_check').fetchone() is None
