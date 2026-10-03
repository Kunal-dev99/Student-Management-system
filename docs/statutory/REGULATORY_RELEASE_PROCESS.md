# Regulatory updates under subscription

How a new or changed HESA specification reaches every institution (Demo 2 item 1.21). The
platform team releases it once, centrally, and each institution then closes its own gaps and
signs off its return. Institutions never have to wait for a software release to get a regulatory
change.

## How it works

- **Shared specification versions.** A specification is held per return (pack, e.g.
  `HESA_STUDENT`) and collection year (e.g. `2027/28`) as numbered versions in
  `statutory_spec_version`. Every institution shares them. Version 1 is the baseline shipped in
  code; each accepted advisory or imported specification adds a new version and supersedes the
  previous one.
- **Every institution picks it up at once.** Return profiles read the active version for their
  own pack and year. A release for 2027/28 never touches a 2026/27 return.
- **Only the platform team can change it.** Ingesting, importing, accepting or rejecting a
  specification, and suppressing a rule for the whole pack, need `platform.configure`.
  Institutions read the specification, and suppress rules for their own profiles only.
- **Returns already signed off are untouched.** A signed-off return is a frozen version and can
  still be re-downloaded exactly as it was.

## Who does what

| Step | Who | Where |
|---|---|---|
| Get the new specification from HESA | Platform team | HESA coding manual, specification or advisory |
| Release it | Platform team (`platform.configure`) | **Statutory → Import spec**, or **Advisories → Ingest → Accept** |
| Check the impact and notify | Platform team | `python -m scripts.spec_release impact <pack> <year> --notify` |
| Close the gaps, validate, sign off | Each institution (`admin.configure`, `reports.signoff`) | **Statutory → their return → Sign-off** |
| Roll back if needed | Platform team | `python -m scripts.spec_release restore <version-id>` |

## The release procedure

1. **Get the specification.** Download it from HESA, either the collection's field specification
   or an advisory. HESA blocks automated fetching, so upload the file or paste the text rather
   than pointing the platform at a URL.
2. **Stage it.** On staging (a copy of production), release it:
   - **Statutory → Import spec** for a whole specification;
   - **Advisories → Ingest** for a change list. Review the proposed changes (fields added or
     removed, coding frames, rules), then **Accept**.
3. **Check the impact on staging:**

   ```bash
   python -m scripts.spec_release versions HESA_STUDENT 2027/28
   python -m scripts.spec_release impact HESA_STUDENT 2027/28
   ```

   `impact` lists, for every institution, each return on that pack and year and what it still needs
   before sign-off: specification fields it doesn't have, and required fields with no source or
   default. It uses the same check as the sign-off screen.
4. **Regression.** On staging, open **Validate** for a sample of returns and compare the errors
   with the previous version. A new rule that fails for most records usually means a bad rule;
   fix it in the specification before release rather than suppressing it everywhere.
5. **Release to production.** Repeat step 2 on production, then record the release in the log
   below.
6. **Tell the institutions:**

   ```bash
   python -m scripts.spec_release impact HESA_STUDENT 2027/28 --notify
   ```

   Each institution's administrators get an in-app notification ("A new statutory specification
   version is live"), including how many of their returns need action.
7. **Institutions close their gaps.** In **Statutory → Sign-off** they map or default each missing
   field (one-click mapping is offered where the specification suggests a source), run
   **Validate**, and sign off.
8. **If the release is wrong, roll back:**

   ```bash
   python -m scripts.spec_release versions HESA_STUDENT 2027/28     # find the previous version's id
   python -m scripts.spec_release restore <previous-version-id>
   ```

   The API equivalent is `POST /api/v1/report-advisories/spec-versions/{id}/restore` (platform
   only). Nothing is deleted, so restoring the newer version again undoes the rollback. Notify the
   institutions again.

## Release log

Keep one row per release (in the release notes or the platform team's runbook).

| Date | Pack | Year | Version | HESA source and reference | Released by | Impact (returns needing action) | Notes |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

## Rules that keep it safe

- **Year-specific.** A version applies only to its own collection year; profiles fall back to the
  latest year only when none exists for theirs.
- **Signed-off returns are frozen** and are never rebuilt against a new version.
- **A bad rule is fixed centrally**, by a pack-wide suppression or a corrected version from the
  platform team, so institutions don't each work around it.
- **Every release and rollback is a recorded API call.** The audit log names who made it.

## Code

| Piece | File |
|---|---|
| Versions, resolving the active one | `backend/app/modules/exports/spec_resolver.py` |
| Import and advisories | `backend/app/modules/exports/spec_import.py`, `advisory_service.py` |
| Version list, rollback, impact | `backend/app/modules/exports/spec_release.py` |
| Release tool | `backend/scripts/spec_release.py` |
| Platform-only rule | `SHARED_SPEC_PERMISSION` in `backend/app/modules/exports/router.py` |
| Tests | `backend/tests/integration/test_spec_release.py`, `test_shared_spec_platform_only.py` |
