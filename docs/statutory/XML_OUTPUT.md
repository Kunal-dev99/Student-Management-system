# XML output of a statutory return

A return downloads as CSV (the file to submit today), an Excel review workbook, and XML in two
shapes. Both XML files are built from the same rows as the CSV, so their values agree.

| | Flat XML | Nested XML |
|---|---|---|
| Shape | One `<Record>` per row, one element per field code | `Student` → `Engagement` (+ `Leaver`) → `StudentCourseSession` → `SessionStatus` / `ModuleInstance` / `SupervisorAllocation`, the shape of HESA Data Futures |
| Live return | `GET /api/v1/report-profiles/{id}/xml` | `GET /api/v1/report-profiles/{id}/xml?nested=true` |
| Frozen version | `.../versions/{vid}/download?format=xml` | `.../versions/{vid}/download?format=xml-nested` |
| Screen | **XML** | **XML (nested)** |

## How the nested file is built

- **Grouping.** One `Student` per person (HUSID), one `Engagement` per student record, one
  `StudentCourseSession` per programme period in the year (a mid-year transfer gives two).
- **Where a mapped field goes** follows its source in the profile's field mapping: `person.*` →
  Student, `engagement.*` → Engagement, `leaver.*` → Leaver, everything else → StudentCourseSession.
  A field with no telling source (filled from a default) is placed by its HESA code: ETHNIC,
  SEXID and the like on Student. Mapped fields keep exactly the CSV's value.
- **Engagement and Leaver** are filled from the dated history when the profile doesn't map them.
- **Children** (status periods, module instances, supervisors) come from the dated history for that
  period. A frozen version keeps its frozen values; its children are rebuilt as the data was known
  at sign-off, which the snapshot guarantees is the same data.

## Not yet validated against HESA's XSD

The root carries `schemaValidated="false"`. Child element names and the field-to-entity fallbacks
are in one place, `backend/app/modules/exports/xml_nested.py` (`CHILDREN`, `ENTITY_OF_CODE`,
`ENGAGEMENT_FIELDS`, `LEAVER_FIELDS`). When the collection's XSD is available:

1. align those names and the entity order with the XSD;
2. validate generated files against it (and add that check to the download);
3. map coded values to HESA codes where they still hold internal ones (e.g. status, fee status).

Dates in mapped fields follow the profile's transforms (e.g. `YYYYMMDD`); dates in child entities
are ISO (`YYYY-MM-DD`), as Data Futures uses.

## Code

| Piece | File |
|---|---|
| Flat XML | `backend/app/modules/exports/xml_return.py` |
| Nested XML | `backend/app/modules/exports/xml_nested.py` |
| Routes | `backend/app/modules/exports/router.py` |
| Tests | `backend/tests/integration/test_xml_nested.py`, `test_return_workbook.py` |
