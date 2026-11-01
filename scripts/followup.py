"""Background local queue generation, not electronic notification or SMTP sender."""
import os
from datetime import date
from pathlib import Path
from app.database import initialize, db
from app.followup import generate_followups
from app.main import audit,utcnow,LOCAL_TZ
from datetime import datetime

if __name__=='__main__':
    path=Path(os.environ.get('PORTACUSTODIA_DATA','./data')).resolve()/'portacustodia.sqlite3'
    initialize(path)
    with db(path,write=True) as c:
        count=generate_followups(c,datetime.now(LOCAL_TZ).date(),audit,utcnow())
    print(f'{count} tareas de revisión nuevas. No se han enviado comunicaciones.')
