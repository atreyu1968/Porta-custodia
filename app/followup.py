"""Create review tasks from deadlines; never sends messages without human intervention."""
from datetime import date

STAGES = {
    'previo30': ('Preaviso de devolución (30 días)',30),
    'previo15': ('Preaviso de devolución (15 días)',15),
    'previo7': ('Preaviso de devolución (7 días)',7),
    'vencido1': ('Primer seguimiento tras vencimiento',-1),
    'vencido7': ('Segundo seguimiento tras vencimiento',-7),
}


def stage_for(due,now):
    days=(due-now).days
    if days< -6:return 'vencido7'
    if days<0:return 'vencido1'
    if days<=7:return 'previo7'
    if days<=15:return 'previo15'
    if days<=30:return 'previo30'
    return None


def generate_followups(c, now, audit_func, timestamp):
    """Idempotently queue one task per stage and due-date. No delivery takes place."""
    count=0
    loans=c.execute("SELECT id,due_date FROM loans WHERE state='activo'").fetchall()
    for loan in loans:
        stage=stage_for(date.fromisoformat(loan['due_date']),now)
        if stage is None:continue
        exists=c.execute('SELECT id FROM followups WHERE loan_id=? AND stage=? AND deadline_date=?',
                         (loan['id'],stage,loan['due_date'])).fetchone()
        if exists:continue
        c.execute('INSERT INTO followups(loan_id,stage,deadline_date,created_at) VALUES(?,?,?,?)',
                  (loan['id'],stage,loan['due_date'],timestamp))
        item_id=c.execute('SELECT last_insert_rowid()').fetchone()[0]
        audit_func(c,None,'seguimiento_programado','seguimiento',item_id,
                   {'loan_id':loan['id'],'stage':stage,'due_date':loan['due_date'],'not_sent':True})
        count+=1
    return count
