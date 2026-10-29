from pydantic import BaseModel

class ReportCostResponse(BaseModel):
    unknown_runs: int
    known_total_micro: int
    known_average_per_run_micro: int

class ReportSummaryResponse(BaseModel):
    ai_review_counts: dict[str, int]
    reviewed_drafts: int
    cost: ReportCostResponse
