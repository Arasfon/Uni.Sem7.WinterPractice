from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.services.report import generate_pdf_report, generate_xlsx_report

router = APIRouter(prefix="/api/report", tags=["report"])


def _parse_dt(value: str) -> float:
    s = value.strip()
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        dt = datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        return dt.timestamp()

    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).timestamp()


@router.get("/pdf")
def make_pdf_report(
    start: Optional[str] = Query(default=None, description="Start datetime/date (UTC). Examples: 2026-01-01 or 2026-01-01T12:00:00Z"),
    end: Optional[str] = Query(default=None, description="End datetime/date (UTC). Examples: 2026-01-28 or 2026-01-28T23:59:59Z"),
) -> Response:
    try:
        start_ts = _parse_dt(start) if start else None
        end_ts = _parse_dt(end) if end else None
        if start_ts is not None and end_ts is not None and end_ts < start_ts:
            raise HTTPException(status_code=400, detail="end must be >= start")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}") from e

    pdf_bytes = generate_pdf_report(start_ts, end_ts)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="bicycle_counter_report.pdf"'},
    )


@router.get("/xlsx")
def make_xlsx_report(
    start: Optional[str] = Query(default=None, description="Start datetime/date (UTC). Examples: 2026-01-01 or 2026-01-01T12:00:00Z"),
    end: Optional[str] = Query(default=None, description="End datetime/date (UTC). Examples: 2026-01-28 or 2026-01-28T23:59:59Z"),
) -> Response:
    try:
        start_ts = _parse_dt(start) if start else None
        end_ts = _parse_dt(end) if end else None
        if start_ts is not None and end_ts is not None and end_ts < start_ts:
            raise HTTPException(status_code=400, detail="end must be >= start")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}") from e

    try:
        xlsx_bytes, fname = generate_xlsx_report(start_ts, end_ts, start, end)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
