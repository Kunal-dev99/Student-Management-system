"""Pattern discovery (PL-2): dependency-free statistics with business-language evidence.

Method, chosen for explainability at institutional scale (hundreds of rows):

- Every feature is reduced to a **two-group comparison**: booleans as-is, numerics split at
  the median. A university committee can argue with "students with fewer than 3 meetings
  delayed at 41% vs 12%"; it cannot argue with a regression coefficient.
- Significance: two-proportion z-test, with **Bonferroni correction** across every test run
  — with ~13 features, uncorrected p<0.05 would hand back one false pattern per analysis.
- Effect size: risk ratio, because "2.4× the rate" is the honest headline number.
- Groups smaller than MIN_GROUP are not tested — reported as skipped, never as absence of
  a pattern.
- **Confounders are named**: for each significant finding, other features whose split
  co-varies with it (|phi| ≥ 0.3) are listed, with the doc's own warning that association
  is not causation (§6.7).

No scipy/pandas: the z-test needs only `math.erfc`. The `[ml]` extra arrives in PL-3 for
model training; discovery stays runnable on every install.
"""
from __future__ import annotations

import math
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationAppError
from app.modules.pattern_lab.models import MlDataset, MlFinding
from app.modules.pattern_lab.targets import TARGETS

MIN_GROUP = 15
ALPHA = 0.05
PHI_CONFOUND = 0.3


def _two_proportion_p(p1: float, n1: int, p2: float, n2: int) -> float | None:
    pooled = (p1 * n1 + p2 * n2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2)) if 0 < pooled < 1 else 0.0
    if se == 0:
        return None
    z = (p1 - p2) / se
    return math.erfc(abs(z) / math.sqrt(2))          # two-sided


def _phi(a: list[int], b: list[int]) -> float:
    n = len(a)
    if n == 0:
        return 0.0
    n11 = sum(1 for x, y in zip(a, b) if x and y)
    n10 = sum(1 for x, y in zip(a, b) if x and not y)
    n01 = sum(1 for x, y in zip(a, b) if not x and y)
    n00 = n - n11 - n10 - n01
    denom = math.sqrt((n11 + n10) * (n01 + n00) * (n11 + n01) * (n10 + n00))
    return ((n11 * n00) - (n10 * n01)) / denom if denom else 0.0


class DiscoveryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def discover(self, dataset_id: uuid.UUID) -> list[MlFinding]:
        ds = await self.session.get(MlDataset, dataset_id)
        if ds is None:
            raise NotFoundError("Dataset not found")
        if not ds.sufficient:
            raise ValidationAppError(
                "This dataset did not pass the sufficiency gate — discovery on it would "
                "produce patterns that are noise dressed as insight."
            )
        target = TARGETS[ds.target_key]
        rows = ds.matrix
        outcomes = [r["outcome"] for r in rows]

        # Build the binary split per feature (bool → as-is, numeric → median split).
        feature_meta = {f["key"]: f for f in ds.quality["activeFeatures"]}
        splits: dict[str, dict] = {}
        for key in feature_meta:
            pairs = [(r["features"].get(key), r["outcome"]) for r in rows
                     if r["features"].get(key) is not None]
            if len(pairs) < 2 * MIN_GROUP:
                splits[key] = {"skipped": f"only {len(pairs)} usable values"}
                continue
            values = sorted(v for v, _ in pairs)
            is_bool = set(values) <= {0.0, 1.0}
            if is_bool:
                threshold, desc_hi, desc_lo = 0.5, "yes", "no"
            else:
                threshold = values[len(values) // 2]
                desc_hi, desc_lo = f"above {threshold:g}", f"at or below {threshold:g}"
                if all(v <= threshold for v in values) or all(v > threshold for v in values):
                    splits[key] = {"skipped": "no variation to split on"}
                    continue
            hi = [(v, o) for v, o in pairs if v > threshold]
            lo = [(v, o) for v, o in pairs if v <= threshold]
            if len(hi) < MIN_GROUP or len(lo) < MIN_GROUP:
                splits[key] = {"skipped": f"a split group would have under {MIN_GROUP} students"}
                continue
            splits[key] = {
                "threshold": threshold, "descHi": desc_hi, "descLo": desc_lo,
                "hiN": len(hi), "loN": len(lo),
                "hiRate": sum(o for _, o in hi) / len(hi),
                "loRate": sum(o for _, o in lo) / len(lo),
                "flags": [1 if (r["features"].get(key) or 0) > threshold else 0 for r in rows],
            }

        tested = {k: s for k, s in splits.items() if "skipped" not in s}
        corrected_alpha = ALPHA / max(1, len(tested))

        # Replace any earlier findings for this dataset — discovery is idempotent per version.
        for old in (await self.session.execute(
            select(MlFinding).where(MlFinding.dataset_id == ds.id)
        )).scalars().all():
            await self.session.delete(old)

        candidates = []
        for key, s in tested.items():
            p = _two_proportion_p(s["hiRate"], s["hiN"], s["loRate"], s["loN"])
            if p is None:
                continue
            worse_hi = s["hiRate"] >= s["loRate"]
            rate_w, n_w, desc_w = ((s["hiRate"], s["hiN"], s["descHi"]) if worse_hi
                                   else (s["loRate"], s["loN"], s["descLo"]))
            rate_b, n_b, desc_b = ((s["loRate"], s["loN"], s["descLo"]) if worse_hi
                                   else (s["hiRate"], s["hiN"], s["descHi"]))
            rr = (rate_w / rate_b) if rate_b > 0 else None
            candidates.append({
                "key": key, "p": p, "rr": rr, "split": s,
                "worse": {"desc": desc_w, "rate": rate_w, "n": n_w},
                "better": {"desc": desc_b, "rate": rate_b, "n": n_b},
            })
        candidates.sort(key=lambda c: c["p"])

        findings = []
        for rank, c in enumerate(candidates, start=1):
            meta = feature_meta[c["key"]]
            significant = c["p"] < corrected_alpha
            confounders = [
                {"key": k2, "label": feature_meta[k2]["label"],
                 "phi": round(_phi(c["split"]["flags"], tested[k2]["flags"]), 2)}
                for k2 in tested
                if k2 != c["key"] and abs(_phi(c["split"]["flags"], tested[k2]["flags"])) >= PHI_CONFOUND
            ] if significant else []
            rr_txt = f" — {c['rr']:.1f}× the rate" if c["rr"] else ""
            statement = (
                f"Students with {meta['label'].lower()} {c['worse']['desc']} "
                f"{target.outcome_label} at {c['worse']['rate']:.0%}, vs "
                f"{c['better']['rate']:.0%} for {c['better']['desc']}{rr_txt}."
            )
            findings.append(MlFinding(
                dataset_id=ds.id, feature_key=c["key"], rank=rank,
                statement=statement, significant=significant,
                p_value=round(c["p"], 6), effect=round(c["rr"], 3) if c["rr"] else None,
                evidence={
                    "featureLabel": meta["label"], "group": meta["group"],
                    "description": meta["description"],
                    "worse": c["worse"], "better": c["better"],
                    "pValue": c["p"], "correctedAlpha": corrected_alpha,
                    "testsRun": len(tested), "riskRatio": c["rr"],
                    "confounders": confounders,
                    "caution": "Association does not imply causation. Review the possible "
                               "confounders before acting on this pattern.",
                },
            ))
        skipped = [{"key": k, "label": feature_meta[k]["label"], "reason": s["skipped"]}
                   for k, s in splits.items() if "skipped" in s]
        for f in findings:
            self.session.add(f)
        # Skipped tests are part of the record — silence must not read as "no pattern".
        ds.quality = {**ds.quality, "discoverySkipped": skipped,
                      "testsRun": len(tested), "correctedAlpha": corrected_alpha}
        await self.session.commit()
        return findings
