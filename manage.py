"""Initial administration user provisioning (never a hard-coded default account)."""
import argparse
import getpass
import re
from app.database import initialize,db
from app.main import PH, audit, utcnow
from app.contact import valid_staff_email
import os
from pathlib import Path

p=argparse.ArgumentParser(description='Administración de PortaCustodia')
p.add_argument('action',choices=['create-admin','check-audit'])
p.add_argument('--username',default='administrador')
p.add_argument('--name',default='Administrador/a del centro')
p.add_argument('--email',default='',help='Correo institucional del administrador (@canariaseducacion.es)')
args=p.parse_args()
path=Path(os.environ.get('PORTACUSTODIA_DATA','./data')).resolve()/'portacustodia.sqlite3'
initialize(path)
if args.action=='create-admin':
    if not re.fullmatch(r'[a-z0-9._-]{3,100}',args.username):raise SystemExit('Usuario no válido.')
    if args.email and not valid_staff_email(args.email):raise SystemExit('Utilice un correo @canariaseducacion.es válido.')
    password=getpass.getpass('Contraseña inicial (mínimo 12 caracteres): ')
    if len(password)<12:raise SystemExit('Contraseña demasiado corta.')
    with db(path,write=True) as c:
        existing=c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        if existing:raise SystemExit('Ya existen usuarios. Alta o restablecimiento desde la aplicación.')
        c.execute('INSERT INTO users(username,full_name,role,institutional_email,password_hash,must_change) VALUES(?,?,?,?,?,1)',
                  (args.username,args.name,'admin',args.email.lower(),PH.hash(password)))
        uid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
        audit(c,uid,'cuenta_administrador_inicial','usuario',uid)
    print('Administrador creado. Se exigirá cambio de contraseña al iniciar sesión.')
else:
    from app.main import verify_audit
    with db(path) as c:
        good,broken=verify_audit(c)
    print('Cadena íntegra.' if good else f'INCIDENCIA: cadena alterada en evento {broken}.')
    if not good:raise SystemExit(1)
