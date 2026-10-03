"""Populate only an isolated end-to-end fixture database, never the live app."""
import sqlite3, sys
from pathlib import Path
path=Path(sys.argv[1]).resolve()
if not path.parent.name.startswith('campus-route-e2e-') or path.name!='browser.sqlite3':
    raise SystemExit('This fixture accepts only the browser-check temporary database.')
with sqlite3.connect(path) as db:
    db.row_factory=sqlite3.Row
    source=db.execute("SELECT * FROM requests WHERE status!='Resolved' LIMIT 1").fetchone()
    count=db.execute("SELECT count(*) FROM requests WHERE status!='Resolved'").fetchone()[0]
    if source is None or count>500:raise SystemExit('Unexpected browser fixture state.')
    columns=[key for key in source.keys() if key!='id']
    sql='INSERT INTO requests ('+','.join(columns)+') VALUES ('+','.join('?'*len(columns))+')'
    db.executemany(sql,[tuple(source[k] for k in columns)]*(500-count))
