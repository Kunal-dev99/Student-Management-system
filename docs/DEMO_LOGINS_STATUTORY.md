# Demo logins — statutory returns, custom attributes, multi-tenancy

**Demo databases only.** Created by `backend/scripts/seed_statutory_demo.py` (refuses to run with
`APP_ENV=production`). Re-run it any time to reset these accounts to the passwords below:

```
cd backend
python -m scripts.seed_statutory_demo
```

## Institute of Cancer Research (tenant `default`) — password `ICRdemo2026!`

| Login | Role | Use in the demo |
|---|---|---|
| admin@icr.demo | Institution Administrator + PGR Administrator | The institution's admin (every permission) |
| requester@icr.demo | PGR Administrator | Raises custom-attribute requests, runs/generates the return |
| approver@icr.demo | Institution Administrator | Approves/rejects requests, maps fields, retires/restores, signs off |
| approver2@icr.demo | Institution Administrator | The second person for maker-checker steps (e.g. retire after approver started a review) |
| supervisor@icr.demo | Supervisor | Shows Statutory is not available to academic staff |

ICR holds the full demo cohort (696 students), five return profiles and the existing custom
attributes (care leaver flag, disability, ethnic origin, refugee status, SEXORT).

## Oxbridge University (tenant `oxbridge`) — password `OXBdemo2026!`

| Login | Role | Use in the demo |
|---|---|---|
| admin@oxbridge.demo | Institution Administrator + PGR Administrator | The institution's admin (every permission) |
| requester@oxbridge.demo | PGR Administrator | Same as above, for Oxbridge |
| approver@oxbridge.demo | Institution Administrator | Same as above, for Oxbridge |
| approver2@oxbridge.demo | Institution Administrator | Second approver |
| supervisor@oxbridge.demo | Supervisor | No statutory access |

Oxbridge has 3 students and its own HESA Student 2026/27 return (created from the spec), and no
custom attributes.

## Showing multi-tenancy (5 minutes)

1. Sign in as **approver@icr.demo** → Statutory: five returns, 696 students; Custom attributes
   lists ICR's five attributes.
2. Sign out, sign in as **approver@oxbridge.demo** → Statutory: one return, 3 students;
   Custom attributes is empty. None of ICR's data is visible.
3. As **requester@oxbridge.demo**, request an attribute called `Care leaver flag` — it is
   accepted (no duplicate warning against ICR's attribute of the same name): each institution
   has its own catalogue.
4. As **approver@oxbridge.demo**, approve it. Sign back in as ICR: its catalogue is unchanged.
5. Show the guard: on the sign-in page pick **Institute of Cancer Research** and sign in as
   approver@oxbridge.demo → refused: "This account isn't registered with Institute of Cancer
   Research. Choose your own institution and sign in again." Pick Oxbridge University → signed in.
   (A wrong password always says just "Invalid email or password", whatever is picked.) In
   production each institution has its own web address, which enforces the same rule.

## Older demo logins (still valid, ICR)

admin@example.com / pgr.admin@example.com / kunal@fusionpractice.com (dev console) — see
`backend/scripts/seed_demo_logins.py`.
