# PGR Pattern Lab — Implementation Plan

**Source:** `PGR_Pattern_Lab_Implementation_Plan.docx` (product & implementation plan)
**Status:** ✅ **COMPLETE — all six phases built, tested and browser-verified (2026-08-22)**
**Prepared:** 2026-08-22, against migration head `800191647194`, 224 passing tests

> **Build record (PL-1 + PL-2):** module `app/modules/pattern_lab/` (targets, features,
> dataset builder, discovery, router), migration `ddba4187dd3c` (`ml_dataset`, `ml_finding`),
> permissions `ml.read`/`ml.analyse`, 7 tests (231 total). Verified against the live cohort:
> funding-continuity discovery found a significant pattern in 126 ms with Bonferroni holding
> the borderline ones; progression-delay correctly found **nothing** significant (the
> generator plants overdue milestones at random — there is no true association, and the tool
> does not invent one). Live-run finding folded back into the code: the `overdue` status is
> never stored — overdue is a fact about dates — so the outcome labels past-due undecided
> milestones as delayed (0 → 36 positives).
>
> **Build record (PL-3):** `training.py` — bounded candidate search (dummy baseline,
> logistic regression, random forest, gradient boosting; small grids via GridSearchCV),
> stratified 5-fold CV with out-of-fold metrics (AUC±std, average precision, Brier,
> precision/recall@0.5), permutation importance on held-out data, pickled artifact per
> version. Tables `ml_model` / `ml_model_version` / `ml_training_run` (migration
> `d1affdf74011`); permission `ml.train`; scikit-learn added as the optional `[ml]` extra —
> **no pandas needed** (plain arrays suffice). Verdict rule: beats baseline by ≥0.05 AND
> (mean−std)>0.5, else the run is reported **failed** ("a result, not an error") — pinned by
> a test that scrambles outcomes and asserts failure. Live cohort: Funding Continuity →
> gradient boosting **AUC 0.702±0.057**, top factor `stipend_amount` (consistent with the
> PL-2 finding); Progression Delay → AUC 0.609±0.079, top factor `milestones_defined` — an
> exposure effect (more scheduled milestones, more chances one slips) that univariate
> median-splits could not see; the model may find what discovery cannot, and both report
> honestly. 234 tests.
>
> **Build record (PL-4):** `registry.py` — the lifecycle state machine
> (trained → candidate → review → approved → production, with declined/retired terminal),
> **approver separation** (whoever started the training run cannot approve/decline/promote
> its versions), mandatory written rationale on every decision, an append-only
> `governance_log` on each version, single-production-per-model (promotion auto-retires the
> incumbent and says so in both logs), and a **baseline block**: a version that lost to the
> baseline cannot even enter review — "a coin-flip with a version number must never acquire
> governance momentum". Auto-generated **model card** with *computed* limitations (small-n,
> imbalance, modest AUC, fold variance — the card says what a careful statistician would
> say), plus the dataset→features→run→version→predictions lineage chain. New permission
> `ml.approve` — held only by "*"-roles (Institution Administrator), deliberately NOT in the
> PGR Administrator bundle. Migration `d81f2647288f`. 240 tests (6 governance tests, incl.
> the two-humans walk to production and the trainer-cannot-approve refusal).
>
> **Build record (PL-5):** `prediction.py` — batch scoring of the live cohort (active/
> registered students, features as of today) from **production versions only** (a candidate,
> however good, produces nothing a user can see); append-only `ml_prediction` rows with full
> version traceability (migration `44faaad53ffb`); **per-student contributing factors by
> perturbation** — replace one feature with the population median, measure the probability
> move ("Stipend amount +50.8 pp") — model-agnostic, exact per student, no SHAP dependency.
> Task raising is governed by two Phase 8 settings (`pattern_lab.raise_tasks` default OFF,
> `pattern_lab.task_threshold`), assigns advisory review tasks to PGR Administrators, and
> never duplicates an open task on rescore. Enterprise 360's response shape was deliberately
> left untouched (it feeds exports + the assistant); the cohort lens is the Predictions tab
> and the per-student panel. Live run: 266 students scored in 700 ms, mean 13.4%, 13
> students in the 60–80 % band, every one explained. 244 tests (+1 conditional skip).
>
> **Build record (PL-6):** `monitoring.py` — performance vs actuals (matured predictions
> compared against real outcomes: calibration-in-the-wild per band + AUC on the matured
> subset via a rank statistic — monitoring needs no ML dependency), population drift per
> feature (PSI against the frozen training matrix; the stored dataset artifact pays off),
> prediction trend per batch, and a health verdict (`ok`/`watch`/`review`) that **names its
> reasons** and computes a recommended review date (`pattern_lab.review_interval_days`
> setting, default 90). **Manual-first retraining**: `POST /models/{id}/retrain` builds a
> fresh dataset + re-runs the candidate search; the result enters at CANDIDATE and walks
> the same governance — nothing auto-promotes; scheduled/triggered retraining deliberately
> deferred until a manual cycle has been observed. **First live run caught a real issue**:
> the production funding model flagged `review` — matured AUC 0.48 vs trained 0.70 plus
> major PSI drift in four features — the training-serving skew between point-in-time
> training features and scored-today features, surfaced by the monitor exactly as designed.
> The browser-verified retrain round-trip produced v2 candidates with production v1
> untouched. 248 tests (+1 conditional skip).

---

## 1. What the document asks for

An institutional learning layer over the PGR lifecycle: **Discover → Validate → Train →
Evaluate → Approve → Deploy → Monitor → Retrain**. Administrators define an institutional
question ("what factors are associated with progression delays?"), the platform builds and
validates a historical dataset, discovers statistically meaningful patterns with evidence,
optionally trains governed predictive models, and feeds **approved** predictions back into
existing views and workflows — with humans making every consequential decision.

## 2. What already exists (build on, don't duplicate)

| Doc asks for | Already in the platform |
|---|---|
| Prediction surfaced in student/enterprise views | Enterprise 360 + deterministic **risk indicators** (Phase 3) — Pattern Lab *adds* learned signals beside them, never replaces them |
| Workflow integration ("suggest an intervention") | Workflow/task engine — a prediction can raise a task exactly like the funding-integrity engine does. **No second workflow engine** (standing guardrail) |
| Background training jobs | Existing worker loop — training runs as a worker job, same as exports |
| Approval workflow, audit trail | Approver-separation pattern from Phase 6.5 + existing audit middleware |
| Governed settings (thresholds, retrain cadence) | Phase 8 settings registry — Pattern Lab knobs become registry entries |
| Rules vs ML separation (§10) | Exactly the platform's standing stance: the funding-integrity engine, route-integrity rules and lifecycle rules are the deterministic layer; Pattern Lab is the *learned* layer beside them |
| Explainability | The matching engine set the house style: every score attributes its points to named reasons. Pattern Lab holds the same bar |

## 3. Data reality check (measured 2026-08-22, live DB)

| Outcome data | Count | Verdict for supervised training |
|---|---|---|
| Milestones, decided | **810** | ✅ **Progression Delay Risk is trainable now** |
| Funding arrangements | 381 (gaps derivable) | ✅ Funding Continuity Risk viable |
| Supervision meetings | 702 | ✅ Usable as signals |
| Completions | **1** | ❌ Completion Forecast — **no outcomes to learn from yet** |
| Applications → registration | 344 at 99.7% conversion | ❌ Applicant Outcome — **almost no negative class** |

**Consequence, built into the design:** every analysis passes a **data sufficiency gate**
(minimum eligible outcomes, minimum minority-class count, class balance) before training is
even offered. The doc's own Validate stage demands this; here it is enforced, not advisory.
Completion Forecast and Applicant Outcome ship as *defined targets* that unlock automatically
when the data exists — the UI says exactly what is missing ("1 completion recorded; ≥50
needed").

## 4. Technology decisions (where this plan deviates from the doc, and why)

The document proposes pandas, scikit-learn, XGBoost/LightGBM, FLAML/AutoGluon, Optuna, SHAP
and MLflow. That is a reasonable industry stack — for a data platform with millions of rows.
This platform has **hundreds of students**, and a standing no-heavy-dependency principle that
has paid off three times (assistant, funding integrity, matching). Adjustments:

| Doc proposes | This plan | Why |
|---|---|---|
| pandas / scikit-learn | ✅ Adopt (optional extra: `pip install .[ml]`) | The genuinely irreplaceable core. Installed as an extra so the base platform still deploys without it; Pattern Lab endpoints degrade to a clear "ML extra not installed" state |
| XGBoost / LightGBM | ⏸ Defer | At n≈300–800, gradient boosting over logistic regression + random forest buys noise, not accuracy. Add later if evaluation shows a real gap |
| FLAML / AutoGluon (AutoML) | ❌ Replace with a **bounded candidate search** | "AutoML" at this scale = trying 3–4 sklearn model families × small hyperparameter grids with proper cross-validation. That *is* the automated model comparison the doc's UI shows — without a framework that dwarfs the platform |
| Optuna | ❌ sklearn `GridSearchCV` on small grids | Same reason |
| MLflow | ❌ Build the registry on **our own tables** (§9 of the doc *already specifies them*: `ml_models`, `ml_model_versions`, `ml_training_runs`, …) | MLflow is a server + UI + artifact store; the doc's data model is a better fit, gets our audit/permissions for free, and keeps lineage queryable next to the domain data |
| SHAP | ⏸ Start with **permutation importance + per-prediction contribution** (built into sklearn / computable directly for linear + tree models) | Same explanation quality for these model families; SHAP added later only if model complexity grows to need it |
| Celery | ❌ Existing worker | Standing decision |

Everything else in the doc — the lifecycle, the governance, the data model, the guardrails,
the discovery-first UX — is adopted as written.

## 5. Architecture

New backend module `app/modules/pattern_lab/` (the doc's §7 package layout, flattened to fit
the modular monolith):

```
pattern_lab/
  models.py        # ml_dataset, ml_feature, ml_model, ml_model_version,
                   # ml_training_run, ml_prediction, ml_finding  (§9 + findings)
  targets.py       # governed target definitions (the ONLY trainable outcomes)
  dataset.py       # dataset builder: SQL → point-in-time feature matrix, versioned
  features.py      # feature registry + generators + leakage rules
  discovery.py     # statistics: group comparisons, association tests, evidence
  training.py      # candidate search (sklearn), cross-validation, calibration
  explain.py       # permutation importance, per-prediction contributions
  registry.py      # model lifecycle: TRAINED → CANDIDATE → REVIEW → APPROVED → PRODUCTION
  prediction.py    # batch scoring via worker; per-student prediction read API
  monitoring.py    # drift (population stability), performance vs actuals, retrain signals
  router.py        # /pattern-lab/* endpoints
```

**Cross-cutting rules that hold:**
- **Governed targets only** (§13): training is only possible against targets defined in
  `targets.py` — no arbitrary "predict anything" (each target = business definition,
  population, outcome SQL, prediction horizon, leakage rules). Custom targets are a
  *configuration* added by engineering, mirroring the statutory-returns pattern.
- **Leakage prevention is structural**: every feature declares its `as_of` semantics; the
  dataset builder only reads data timestamped *before* the prediction point. Features that
  can't prove temporal validity are excluded and listed as such in the UI.
- **Point-in-time correctness**: the platform's history-preserving tables
  (`valid_from`/`valid_to`, lifecycle events, stage history) make this genuinely possible —
  most systems can't reconstruct "what did we know on day X"; ours can.
- **Sensitive features excluded by default** (§13): demographic/protected attributes are not
  in the feature registry at all in v1. Adding any such feature is an explicit governance
  decision, not a checkbox.
- **Predictions are advisory**: a production model writes `ml_prediction` rows and (optionally)
  raises workflow *tasks*. It never changes student state. Rules and humans remain the
  decision layer (§10, §13).
- **Row scoping**: prediction reads respect `student_scope` like every other student read.
- **New permissions**: `ml.read` (see predictions/findings), `ml.analyse` (run discovery),
  `ml.train` (train candidates), `ml.approve` (promote to production — must be a different
  user than the trainer, same approver-separation as lifecycle events).

## 6. Phase plan

### PL-1 — Foundation (backend)
Tables (§9) + migration; governed target definitions with **the four doc targets** (two
active: Progression Delay, Funding Continuity; two gated: Completion Forecast, Applicant
Outcome); feature registry (~25 features from Research/Supervision/Progression/Funding/Student
groups, each with temporal validity declared); dataset builder producing versioned,
reproducible snapshots with the quality report (records found, eligible outcomes, exclusions,
completeness); sufficiency gate; `ml.*` permissions. **Tests:** dataset reproducibility
(same version → identical matrix), leakage rule enforcement, sufficiency gating.

### PL-2 — Pattern Discovery (backend + UI)
Statistical discovery over a built dataset: outcome-rate comparisons across feature groups,
association tests with multiple-comparison correction, effect sizes, confounder flags.
Findings stored as `ml_finding` rows with full evidence. **UI:** Pattern Lab home (active
models / recent discoveries / data health), New Analysis wizard (question → outcome → dataset
→ signal review → discovery), Discovery Results + Evidence View with the "association is not
causation" framing (§6.6–6.7). *This phase alone delivers §2's core value and works at
today's data sizes.*

### PL-3 — Training & evaluation (backend)
`[ml]` optional extra (pandas + scikit-learn). Bounded candidate search (logistic regression,
random forest, gradient boosting (sklearn's), dummy baseline) with stratified k-fold CV,
calibration, and honest metrics (AUC, precision/recall at operating points, calibration
error). Every run recorded as `ml_training_run`; every candidate as `ml_model_version` with
params, metrics, feature-set version and serialized artifact. Runs execute on the worker.
**A model that cannot beat the baseline is said to have failed** — the UI shows it.

### PL-4 — Governance (backend + UI)
Model lifecycle TRAINED → CANDIDATE → REVIEW → APPROVED → PRODUCTION with approver
separation; auto-generated **model card** (purpose, data window, population, features,
metrics, limitations, excluded features); Models section UI: candidate comparison,
recommended model, promote/decline with recorded rationale; full lineage view
(Dataset → Features → Run → Version → Prediction).

### PL-5 — Production predictions (backend + UI)
Batch scoring job (worker) writing `ml_prediction` with model-version traceability; student
detail + Enterprise 360 show the prediction **beside** the deterministic risk indicators,
with contributing factors ("78% predicted probability of delay — top factors: funding gap
41 days, no meeting in 97 days, first milestone took 1.4× median"); optional task-raising
rule per model (off by default, a Phase 8 setting); Predictions section UI.

### PL-6 — Monitoring & retraining
Performance-vs-actuals as outcomes mature; population drift (PSI) per feature; prediction
distribution tracking; Monitoring UI with recommended review date; **retraining is
manual-first** — scheduled/triggered retraining lands only after at least one manual retrain
cycle has been observed end-to-end (the doc's own governance instinct, applied strictly).
Retrained versions re-enter the lifecycle at CANDIDATE; nothing auto-promotes.

**Sequencing note:** PL-1→PL-2 first and demoable on their own; PL-3→PL-4 together; PL-5 only
after a model has passed governance; PL-6 last. Each phase ends green (tests + build) like
every prior phase.

## 7. Success criteria (from §14, testable)

1. An administrator completes question → dataset → discovery → evidence with zero Python/SQL.
2. Discovery on the generated cohort finds the problems `generate_cohort.py` *planted*
   (funding gaps ↔ delay associations) — the same reconciliation trick Phase 7 used.
3. Leakage: a feature computed after the prediction point is structurally excluded, with a test proving it.
4. Every candidate evaluated with stratified CV against a dummy baseline; failures reported as failures.
5. Every production prediction traceable: prediction → model version → training run → dataset version → feature versions.
6. Every prediction shows its contributing factors in business language.
7. Retraining runs without engineering (PL-6), gated by governance.
8. Rules, workflows and humans remain the decision layer — ML writes advisory rows and optional tasks only.

## 8. Open questions before building

1. **Scope of v1 approval** — build PL-1→PL-2 first and pause for review (recommended), or
   commit the full six phases now?
2. **The `[ml]` extra** — confirm acceptance of pandas + scikit-learn as an *optional* install
   (~150 MB). Base platform stays dependency-light; Pattern Lab training/scoring requires the extra.
3. **Who holds `ml.approve`?** Proposed: Institution Administrator only, and never the same
   user who trained the version (approver separation).
4. **Task-raising from predictions** (PL-5) — proposed off by default per model, enabled via a
   setting. Confirm.
5. **Completion Forecast / Applicant Outcome** — agreed to ship gated (visible, explained,
   locked until data suffices)?
