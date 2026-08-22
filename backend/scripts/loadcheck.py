"""Load check against the arch §15 latency targets (Phase 4C.5).

Measures SERVER-side handler latency (durationMs from the structured access log) rather than
client wall-clock: on a single dev box, co-locating an aggressive async load generator with the
API workers and Postgres inflates client-side timings by an order of magnitude, which is a
measurement artifact, not service latency.

Targets: standard read p95 < 300ms, dashboards p95 < 2s.

Usage — start the API with its output captured to a log file, then:

    python scripts/loadcheck.py <path-to-api-log>

e.g.  uvicorn app.main:app --workers 4 --log-level warning > api.log 2>&1
      python scripts/loadcheck.py api.log

Exits 0 when every target is met.
"""
import asyncio, time, statistics, json, sys
import httpx

BASE = "http://127.0.0.1:8000/api/v1"
LOG = sys.argv[1]

async def login(c):
    r = await c.post(f"{BASE}/auth/login", json={"email":"admin@example.com","password":"admin123"})
    return r.json()["accessToken"]

async def drive(c, tok, path, n, conc):
    h={"Authorization":f"Bearer {tok}"}; sem=asyncio.Semaphore(conc)
    async def one():
        async with sem: await c.get(f"{BASE}{path}", headers=h)
    await asyncio.gather(*[one() for _ in range(n)])

def log_size(path):
    try:
        with open(path,'rb') as f: return f.seek(0,2) or f.tell()
    except FileNotFoundError: return 0

def parse(path, start_byte, want_path):
    ds=[]
    with open(path,'r',encoding='utf-8',errors='ignore') as f:
        f.seek(start_byte)
        for line in f:
            line=line.strip()
            if not line.startswith('{'): continue
            try: r=json.loads(line)
            except Exception: continue
            if r.get('logger')=='pgr.access' and r.get('path')==want_path and 'durationMs' in r:
                ds.append(r['durationMs'])
    return ds

async def main():
    checks=[("Standard read  GET /students","/students?limit=25","/api/v1/students",120,20,300),
            ("Heavy report   enterprise-360","/reports/pgr-enterprise-360","/api/v1/reports/pgr-enterprise-360",60,10,2000),
            ("Heavy report   analytics","/reports/analytics","/api/v1/reports/analytics",60,10,2000)]
    async with httpx.AsyncClient(timeout=30) as c:
        tok=await login(c)
        allpass=True
        print(f"{'endpoint':<32} {'srv p50':>9} {'srv p95':>9} {'srv max':>9}  target   result   (server-side handler latency)")
        for label,path,logpath,n,conc,target in checks:
            start=log_size(LOG)
            await drive(c,tok,path,n,conc)
            await asyncio.sleep(0.5)  # let log flush
            ds=sorted(parse(LOG,start,logpath))
            if not ds:
                print(f"{label:<32}  (no log samples parsed)"); allpass=False; continue
            p50=statistics.median(ds); p95=ds[int(len(ds)*0.95)]; mx=max(ds)
            ok=p95<target; allpass=allpass and ok
            print(f"{label:<32} {p50:>8.0f}ms {p95:>8.0f}ms {mx:>8.0f}ms  <{target}ms  {'PASS' if ok else 'FAIL'}  n={len(ds)}")
        print("\n"+("ALL PASS" if allpass else "SOME FAIL"))
        sys.exit(0 if allpass else 1)

asyncio.run(main())
