# Kanbus API verification evidence

The API remains unpublished. Its Virtuus store dependency is pinned to tested published Git commit `639f873a73ebf1f68add2ae4b93f5fd117a539dc`; final API verification against that exact commit is recorded below when completed.

## Real AWS API CRUD

The guarded `scripts/run-aws-proof.py` run verified account `682849160744`, existing profile `cyclotron-production`, region `us-east-1`, and the existing private stack `virtuus-store-proof-20261014-aws01` at `CREATE_COMPLETE`. No resources or IAM grants were created.

- Namespace: `proof-api/proof-api-20261014-01`
- Bucket: `virtuus-store-proof-20261014-aws01-canonicalbucket-wdxzesz9pihb`
- Table: `virtuus-store-proof-20261014-aws01-CatalogTable-14GEGYK7A6UPN`
- API test: `real_s3_api_quoted_revision_crud_and_audit`
- Result: 1 live test passed in 12.60 seconds after compilation.
- Issue: `kanbus-32bd9918-d730-40bd-91d2-29786430696b`

Observed through the API: configuration with actor identity, create, canonical read, PATCH using the returned quoted ETag, stale PATCH conflict, authenticated comment, history read, converged catalog board query, revision-checked DELETE, durable create/deletion retries, canonical issue absence after deletion, and retained `issue_deleted` history. Conditional publication received the original backend revision. Custom unknown nested data survived PATCH. All five event files retained normal timestamp-double-underscore-UUID names.

An offline fixture issue `project/issues/imported-oversized.json` exceeded 2 MiB and was rejected by the API's bounded S3 accessor with `query_budget_exceeded`. History after deletion reported 5 listed paths, 5 canonical objects and 2,175 canonical bytes. The private configuration, five audit events, oversized fixture import and isolated recovery records remain for inspection. The test issue was conditionally deleted; bucket version history remains. No fixture resources were removed.

## Local cost and revision regressions

22 local integration tests and doctests passed after the first bounded-read integration. A native-quoted filesystem wrapper rejects stripped CAS tokens, exercising PATCH, comments and DELETE with quoted revisions.

For a board containing 1,002 summaries, a request with `limit=1` rejected before card hydration: 1,002 collected summaries, 1,012 backend candidates examined, 11 catalog requests, zero canonical objects and zero accepted canonical bytes. A DELETE reference scan over the oversized fixture returned the budget error without changing the issue.

For 40 unrelated 450 KB events plus normal history, the API stopped at 39 canonical read attempts and 16,652,948 accepted bytes, below the 16 MiB request allowance. The next bounded read was rejected before full collection. The oversized imported issue regression observed zero calls to the raw unbounded accessor.

Cost counters exclude configuration reads and journal control reads. The default storage API remains suitable for raw portable import/export. The API-specific canonical limit also applies to journal recovery; its successful local follow-up is recorded below.

## Recovery-policy follow-up

The API now binds `JournaledStore::with_canonical_read_limit(2 MiB)` at construction and local startup. All 23 local integration tests and doctests passed (5.31 seconds of behavior execution). `durable_replay_after_oversized_restore_never_uses_unbounded_canonical_reads` creates and deletes an issue, restores oversized valid JSON at the absent path while preserving recovery records, and retries the original create. It returns the original durable receipt with `catalog_pending=true`, observes zero unbounded canonical accessor calls, and preserves the restored file. The storage lead also verifies native File/S3 bounded reads and the same recovery policy.

Cloud run `proof-api/proof-api-20261014-02` exercised the original CRUD flow successfully but failed the later recovery setup because its compiled test created an unrelated oversized import before attempting the recovery-test deletion. The API correctly returned HTTP 422 before deletion. The fixture order was corrected; this run does not count as final recovery proof. Read-only inventory confirmed the configuration (3,050 bytes), six normal audit events, the oversized import (2,097,571 bytes), and the undeleted recovery setup issue `kanbus-64a9dd85-badd-4b2c-bfcd-caeed398062b` (427 bytes). These isolated fixture objects remain; no resources or versions were removed.

## Final published-source verification

The store dependency is locked to published Virtuus commit `639f873a73ebf1f68add2ae4b93f5fd117a539dc`. Cargo replaced only the local store/core packages with the exact Git packages; existing registry versions were preserved. All 28 API integration tests and doctests passed against that commit in 4.54 seconds. The independent reviewer separately ran all 28 cases successfully in 5.61 seconds and reported no remaining focused findings.

The final regressions verify mismatched imported identities cannot redirect GET/PATCH/comment/DELETE or board reads, oversized generated before/after history fails before publication, and all response bodies fit a 2.5 MiB compact JSON budget. The actual gateway serializer was tested with quote/backslash-heavy accepted content: its escaped envelope stays below 6 MiB. A priority containing one million backslashes fits the incoming request budget but returns a bounded validation error without issue or history publication. Six matching 450 KB events return explicit `response_bytes` rather than an oversized gateway response. All prior canonical bytes, relationship, authentication, query and native revision cases remain green.

### Final live S3 proof

- Namespace: `proof-api/proof-api-20261014-03`, on the same account/profile/region/private fixture stack as above.
- Locked test: `real_s3_api_quoted_revision_crud_and_audit`.
- Result: 1 real AWS test passed in 20.76 seconds after compilation.
- Main issue: `kanbus-63adba75-0ca6-42fa-94ca-4b5000f0a8f8`; its canonical current object was deleted conditionally, with versions retained.
- Restored recovery fixture: `kanbus-82335634-371d-4583-8fbd-9ba405467cba`; it was created and deleted, then restored create-only as oversized valid JSON. Retrying the original create returned its original receipt with repair pending, without unbounded canonical collection or overwrite.
- Retained events: 13 total (5 main CRUD audit events, 2 recovery-fixture audit events, 6 imported 450 KB matching-history records).

Observed success: create/read/PATCH/comment/DELETE using original quoted S3 ETags, stale conflict, durable create/deletion replay, catalog convergence, retained normal event filenames, oversized direct import rejection, oversized-restoration receipt recovery, bounded response rejection for large matching history, and bounded invalid-priority diagnostics with unchanged canonical issue paths. Base CRUD history cost remained 5 listed/read objects and 2,175 accepted bytes. The public gateway helper emitted small errors beneath the envelope quota.

All fixture configurations, audit files, oversized imports, recovery records and object versions remain isolated and inventoried. No resources or IAM grants were created or removed by these API proof runs. The previously recorded run02 setup failure remains disclosed rather than being counted as a successful proof.
