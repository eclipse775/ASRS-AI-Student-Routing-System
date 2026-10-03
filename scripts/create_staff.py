"""Create an explicitly authorized staff/admin account using a local password prompt."""
import argparse
import getpass
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.database import connection,initialize,utc_now
from app.security import hash_password
from app.university import staff_email_allowed


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name',required=True)
    parser.add_argument('--email',required=True)
    parser.add_argument('--role',choices=['support','admin'],required=True)
    parser.add_argument('--database',default=str(ROOT/'instance/routing.sqlite3'))
    args=parser.parse_args()
    email=args.email.strip().lower()
    if not 2<=len(args.name.strip())<=80 or not staff_email_allowed(email,args.role):
        raise SystemExit('Use helpdesk@sdu.edu.kz for support or a named @sdu.edu.kz administrator address.')
    password=getpass.getpass('Password (10-128 characters): ')
    if not 10<=len(password.strip())<=128 or password!=getpass.getpass('Confirm password: '):
        raise SystemExit('Password length or confirmation is invalid.')
    initialize(args.database)
    with connection(args.database) as db:
        if db.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone():
            raise SystemExit('This account already exists. No role was changed.')
        db.execute('INSERT INTO users (name,email,password_hash,role,created_at) VALUES (?,?,?,?,?)',
                   (args.name.strip(),email,hash_password(password),args.role,utc_now()))
    print('Account created.')


if __name__=='__main__':
    main()
