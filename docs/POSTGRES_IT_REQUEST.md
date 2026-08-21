# Request to IT / Admin — install PostgreSQL for the PGR Platform

I'm setting up a development app that needs a local **PostgreSQL 16** server. Installing it
requires administrator rights, which I don't have. Could you please do the install and give me
the connection details below?

## 1. Install PostgreSQL 16 (needs admin)

Easiest — from an **elevated (Administrator) PowerShell**:

```powershell
winget install --id PostgreSQL.PostgreSQL.16 --silent --accept-package-agreements --accept-source-agreements
```

Or use the official installer: https://www.postgresql.org/download/windows/ (EDB installer,
PostgreSQL 16). During a GUI install you'll be asked to set a password for the **postgres**
superuser and a port (please keep the default **5432**). Let the installer register the
Windows service so it starts automatically.

## 2. Create a database and login for the app

After install, please run this in **psql** (or pgAdmin) as the `postgres` superuser. Pick any
password and tell it to me:

```sql
CREATE ROLE pgr WITH LOGIN PASSWORD 'PUT-A-PASSWORD-HERE';
CREATE DATABASE pgr OWNER pgr;
GRANT ALL PRIVILEGES ON DATABASE pgr TO pgr;
```

(These are local-only dev credentials — nothing internet-facing.)

## 3. What I need back from you

| Item | Example | Your value |
|---|---|---|
| Host | `localhost` | |
| Port | `5432` | |
| Database name | `pgr` | |
| Username | `pgr` | |
| Password | (the one you set above) | |

That's it. With those five values I can point the app at Postgres and run its migrations —
no further admin rights needed.

---

### Alternative (if you'd rather not create the DB yourself)
Just install PostgreSQL (step 1) and give me the **postgres superuser password** + the **port**.
I'll create the `pgr` database and role myself using the SQL above.
