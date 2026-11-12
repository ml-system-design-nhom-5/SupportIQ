# SupportIQ System Evaluation Benchmark Suite v2 (Acceptance)

- **Suite ID:** `supportiq-system-acceptance-v2`
- **Split:** `acceptance`
- **Status:** `draft` (held as draft until formal human sign-off as required by spec)
- **Total Cases:** 156
- **Purpose:** Full blinded acceptance benchmark across all 46 intent labels and 12 product scopes with strict quota enforcement.
- **Slice Quotas:**
  - `supported`: 60
  - `unsupported`: 34
  - `answerable`: 24
  - `unanswerable`: 18
  - `uncertainty_and_faults`: 20
- **Contract Rules:** Enforces strict separation between `must_escalate` and `safe_manual_handling`. Zero logical contradictions between `must_escalate` and `draft_expected`.
