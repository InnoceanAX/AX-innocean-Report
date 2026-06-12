"""
innocean-report-api  —  리포트 솔루션 전용 읽기 API

격리 원칙: report_mart 데이터셋만 읽는다. apac_kr_raw 에 접근하지 않는다.
런타임 SA(report-api-reader)는 report_mart 에 대한 READ 권한만 가진다.

엔드포인트:
  GET  /api/coverage  -> 플랫폼별 신선도/공백 (mart_coverage)
  GET  /api/catalog   -> 데이터가 실제 존재하는 디멘션/지표/플랫폼/기간 (적응형)
  POST /api/query     -> {dims[], metrics[], filters, dateRange} 집계
  GET  /api/targets   -> 목표값 (media_plan_targets)  [Phase 3]
"""
import os
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google.cloud import bigquery

PROJECT = os.environ.get("BQ_PROJECT", "innocean-perf-apac-kr")
MART = f"{PROJECT}.report_mart"
PERF = f"{MART}.report_campaign_performance"

# GOOGLE_APPLICATION_CREDENTIALS 또는 Cloud Run 런타임 SA 사용
client = bigquery.Client(project=PROJECT)

app = FastAPI(title="INNOCEAN Report API", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── 화이트리스트 (SQL 인젝션 차단 + 적응형 카탈로그의 진실원천) ──────────────
DIMS = {
    "platform": "platform", "brand_name": "brand_name", "country": "country",
    "advertiser_name": "advertiser_name", "campaign_name": "campaign_name",
    "adgroup_name": "adgroup_name", "ad_name": "ad_name",
    "date": "date", "year": "EXTRACT(YEAR FROM date)", "month": "FORMAT_DATE('%Y-%m', date)",
}
# 가산 지표(SUM) / 비율 지표(합산 후 계산) 구분 — 비율을 평균내지 않음
ADDITIVE = {
    "spend": "SUM(spend)", "impressions": "SUM(impressions)", "clicks": "SUM(clicks)",
    "reach": "SUM(reach)", "conversions": "SUM(conversions)",
    "costs_krw": "SUM(costs_krw)", "costs_usd": "SUM(costs_usd)",
}
RATIO = {
    "ctr": "SAFE_DIVIDE(SUM(clicks), SUM(impressions))",
    "cpc": "SAFE_DIVIDE(SUM(spend), SUM(clicks))",
    "cpm": "SAFE_DIVIDE(SUM(spend), SUM(impressions)) * 1000",
    "conversion_rate": "SAFE_DIVIDE(SUM(conversions), SUM(clicks))",
    "frequency": "SAFE_DIVIDE(SUM(impressions), SUM(reach))",
}
METRICS = {**ADDITIVE, **RATIO}


class QueryReq(BaseModel):
    dims: list[str] = ["platform"]
    metrics: list[str] = ["spend", "impressions", "clicks"]
    filters: dict = {}          # {col: value | [values]}
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    limit: int = 1000


@app.get("/api/coverage")
def coverage():
    rows = client.query(f"SELECT * FROM `{MART}.mart_coverage` ORDER BY rows_n DESC").result()
    return {"platforms": [dict(r) for r in rows]}


@app.get("/api/catalog")
def catalog():
    """실제 데이터가 존재하는 것만 반환 (적응형 구동)."""
    cov = list(client.query(f"SELECT platform, first_date, last_date FROM `{MART}.mart_coverage`").result())
    platforms = [r.platform for r in cov]
    dmin = min((r.first_date for r in cov), default=None)
    dmax = max((r.last_date for r in cov), default=None)
    # 어떤 지표가 실데이터(비전부 NULL)를 가지는지 점검 → 가용 지표만 노출
    checks = ", ".join(f"COUNTIF({c} IS NOT NULL) AS {c}" for c in ADDITIVE)
    av = list(client.query(f"SELECT {checks} FROM `{PERF}`").result())[0]
    avail_metrics = [m for m in ADDITIVE if av[m] and av[m] > 0]
    # 비율은 기반 지표가 있으면 가용
    if "clicks" in avail_metrics and "impressions" in avail_metrics:
        avail_metrics += ["ctr", "cpc", "cpm"]
    if "conversions" in avail_metrics:
        avail_metrics.append("conversion_rate")
    return {
        "platforms": platforms,
        "date_range": {"from": str(dmin) if dmin else None, "to": str(dmax) if dmax else None},
        "dimensions": list(DIMS.keys()),
        "metrics": sorted(set(avail_metrics)),
    }


@app.post("/api/query")
def query(req: QueryReq):
    dims = [d for d in req.dims if d in DIMS]
    mets = [m for m in req.metrics if m in METRICS]
    if not mets:
        raise HTTPException(400, "no valid metrics")
    select_dims = [f"{DIMS[d]} AS {d}" for d in dims]
    select_mets = [f"{METRICS[m]} AS {m}" for m in mets]
    where, params = ["date IS NOT NULL"], []
    for col, val in (req.filters or {}).items():
        if col not in DIMS:
            continue
        if isinstance(val, list):
            where.append(f"{DIMS[col]} IN UNNEST(@{col})")
            params.append(bigquery.ArrayQueryParameter(col, "STRING", [str(v) for v in val]))
        else:
            where.append(f"{DIMS[col]} = @{col}")
            params.append(bigquery.ScalarQueryParameter(col, "STRING", str(val)))
    if req.date_from:
        where.append("date >= @dfrom"); params.append(bigquery.ScalarQueryParameter("dfrom", "DATE", req.date_from))
    if req.date_to:
        where.append("date <= @dto"); params.append(bigquery.ScalarQueryParameter("dto", "DATE", req.date_to))
    group = ", ".join(str(i + 1) for i in range(len(dims))) if dims else ""
    sql = f"SELECT {', '.join(select_dims + select_mets)} FROM `{PERF}` WHERE {' AND '.join(where)}"
    if group:
        sql += f" GROUP BY {group} ORDER BY {group}"
    sql += f" LIMIT {min(int(req.limit), 50000)}"
    job = client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
    return {"rows": [dict(r) for r in job.result()], "dims": dims, "metrics": mets}


TARGETS = f"{MART}.media_plan_targets"
PHASES = f"{MART}.phase_definitions"
FEES = f"{MART}.media_plan_fees"
INDEX_BASE = {"impressions_index": "impressions", "clicks_index": "clicks", "conversions_index": "conversions", "costs_index": "costs_krw"}
BASE_SET = {"impressions", "clicks", "conversions", "costs_krw", "ctr", "cpm", "cpc"}


def _q(sql, params=None):
    job = client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params or []))
    return [dict(r) for r in job.result()]


def _actual_expr(base, pfx=""):
    c, i, k = pfx + "clicks", pfx + "impressions", pfx + "costs_krw"
    if base == "ctr":
        return f"SAFE_DIVIDE(SUM({c}), SUM({i}))"
    if base == "cpm":
        return f"SAFE_DIVIDE(SUM({k}), SUM({i})) * 1000"
    if base == "cpc":
        return f"SAFE_DIVIDE(SUM({k}), SUM({c}))"
    return f"SUM({pfx}{base})"


# ---- 실제 캠페인 목록 (MM Setup 드롭다운) ----
@app.get("/api/campaigns")
def campaigns(limit: int = 60):
    rows = _q(
        f"SELECT campaign_name, ANY_VALUE(brand_name) brand, ANY_VALUE(country) country, "
        f"MIN(date) first_date, MAX(date) last_date, SUM(costs_krw) costs_krw, "
        f"ARRAY_AGG(DISTINCT platform IGNORE NULLS) platforms "
        f"FROM `{PERF}` WHERE campaign_name IS NOT NULL "
        f"GROUP BY campaign_name ORDER BY costs_krw DESC LIMIT {min(int(limit), 500)}"
    )
    return {"campaigns": rows}


# ---- Phase 정의 ----
class PhaseRow(BaseModel):
    phase_name: str
    period_start: str
    period_end: str
    sort_order: Optional[int] = 0


@app.get("/api/phases")
def phases_get(campaign: str):
    return {"phases": _q(
        f"SELECT phase_name, period_start, period_end, sort_order FROM `{PHASES}` WHERE campaign_name=@c ORDER BY sort_order",
        [bigquery.ScalarQueryParameter("c", "STRING", campaign)])}


@app.post("/api/phases")
def phases_save(campaign: str, rows: list[PhaseRow]):
    cp = [bigquery.ScalarQueryParameter("c", "STRING", campaign)]
    client.query(f"DELETE FROM `{PHASES}` WHERE campaign_name=@c", job_config=bigquery.QueryJobConfig(query_parameters=cp)).result()
    for i, r in enumerate(rows):
        client.query(
            f"INSERT INTO `{PHASES}` (campaign_name,phase_name,period_start,period_end,sort_order,_updated_at) "
            f"VALUES (@c,@n,@s,@e,@o,CURRENT_TIMESTAMP())",
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("c", "STRING", campaign),
                bigquery.ScalarQueryParameter("n", "STRING", r.phase_name),
                bigquery.ScalarQueryParameter("s", "DATE", r.period_start),
                bigquery.ScalarQueryParameter("e", "DATE", r.period_end),
                bigquery.ScalarQueryParameter("o", "INT64", r.sort_order if r.sort_order is not None else i)])).result()
    return {"saved": len(rows)}


# ---- Gross 수수료 ----
class FeeRow(BaseModel):
    platform: str
    fee_rate: float


@app.get("/api/fees")
def fees_get(campaign: str):
    return {"fees": _q(f"SELECT platform, fee_rate FROM `{FEES}` WHERE campaign_name=@c",
                       [bigquery.ScalarQueryParameter("c", "STRING", campaign)])}


@app.post("/api/fees")
def fees_save(campaign: str, rows: list[FeeRow]):
    cp = [bigquery.ScalarQueryParameter("c", "STRING", campaign)]
    client.query(f"DELETE FROM `{FEES}` WHERE campaign_name=@c", job_config=bigquery.QueryJobConfig(query_parameters=cp)).result()
    for r in rows:
        client.query(
            f"INSERT INTO `{FEES}` (campaign_name,platform,fee_rate,_updated_at) VALUES (@c,@p,@f,CURRENT_TIMESTAMP())",
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("c", "STRING", campaign),
                bigquery.ScalarQueryParameter("p", "STRING", r.platform),
                bigquery.ScalarQueryParameter("f", "FLOAT64", r.fee_rate)])).result()
    return {"saved": len(rows)}


# ---- 목표(Targets): campaign x platform x phase x metric ----
class TargetRow(BaseModel):
    platform: str
    phase_name: Optional[str] = None
    metric: str
    target_value: float


@app.get("/api/targets")
def targets_get(campaign: Optional[str] = None):
    w = "WHERE campaign_name=@c" if campaign else ""
    pr = [bigquery.ScalarQueryParameter("c", "STRING", campaign)] if campaign else []
    return {"targets": _q(f"SELECT campaign_name,platform,phase_name,metric,target_value FROM `{TARGETS}` {w} ORDER BY _updated_at DESC", pr)}


@app.post("/api/targets")
def targets_save(campaign: str, rows: list[TargetRow]):
    cp = [bigquery.ScalarQueryParameter("c", "STRING", campaign)]
    client.query(f"DELETE FROM `{TARGETS}` WHERE campaign_name=@c", job_config=bigquery.QueryJobConfig(query_parameters=cp)).result()
    n = 0
    for r in rows:
        if r.target_value is None:
            continue
        client.query(
            f"INSERT INTO `{TARGETS}` (campaign_name,platform,phase_name,metric,target_value,_updated_at) "
            f"VALUES (@c,@p,@ph,@m,@v,CURRENT_TIMESTAMP())",
            job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("c", "STRING", campaign),
                bigquery.ScalarQueryParameter("p", "STRING", r.platform),
                bigquery.ScalarQueryParameter("ph", "STRING", r.phase_name),
                bigquery.ScalarQueryParameter("m", "STRING", r.metric),
                bigquery.ScalarQueryParameter("v", "FLOAT64", r.target_value)])).result()
        n += 1
    return {"inserted": n}


# ---- 달성률: by=platform(일별) | phase(Phase 분석) ----
class AchieveReq(BaseModel):
    metric: str
    by: str = "platform"
    campaign: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None


@app.post("/api/achievement")
def achievement(req: AchieveReq):
    base = INDEX_BASE.get(req.metric) or (req.metric if req.metric in BASE_SET else None)
    if not base:
        raise HTTPException(400, f"unsupported metric: {req.metric}")
    if req.by == "phase":
        if not req.campaign:
            raise HTTPException(400, "campaign required for by=phase")
        cp = [bigquery.ScalarQueryParameter("c", "STRING", req.campaign)]
        actual = {r["k"]: r["actual"] for r in _q(
            f"SELECT ph.phase_name k, {_actual_expr(base, 'p.')} actual "
            f"FROM `{PHASES}` ph JOIN `{PERF}` p "
            f"ON p.campaign_name=ph.campaign_name AND p.date BETWEEN ph.period_start AND ph.period_end "
            f"WHERE ph.campaign_name=@c GROUP BY 1", cp)}
        target = {r["k"]: r["target"] for r in _q(
            f"SELECT phase_name k, SUM(target_value) target FROM `{TARGETS}` "
            f"WHERE campaign_name=@c AND metric=@m AND phase_name IS NOT NULL GROUP BY 1",
            cp + [bigquery.ScalarQueryParameter("m", "STRING", base)])}
        keys = [r["phase_name"] for r in _q(f"SELECT phase_name FROM `{PHASES}` WHERE campaign_name=@c ORDER BY sort_order", cp)] or sorted(set(actual) | set(target))
    else:
        aw, ap = ["date IS NOT NULL"], []
        if req.campaign:
            aw.append("campaign_name=@c"); ap.append(bigquery.ScalarQueryParameter("c", "STRING", req.campaign))
        if req.date_from:
            aw.append("date>=@df"); ap.append(bigquery.ScalarQueryParameter("df", "DATE", req.date_from))
        if req.date_to:
            aw.append("date<=@dt"); ap.append(bigquery.ScalarQueryParameter("dt", "DATE", req.date_to))
        actual = {r["k"]: r["actual"] for r in _q(f"SELECT platform k, {_actual_expr(base)} actual FROM `{PERF}` WHERE {' AND '.join(aw)} GROUP BY 1", ap)}
        tw, tp = ["metric=@m"], [bigquery.ScalarQueryParameter("m", "STRING", base)]
        if req.campaign:
            tw.append("campaign_name=@c"); tp.append(bigquery.ScalarQueryParameter("c", "STRING", req.campaign))
        target = {r["k"]: r["target"] for r in _q(f"SELECT platform k, SUM(target_value) target FROM `{TARGETS}` WHERE {' AND '.join(tw)} GROUP BY 1", tp)}
        keys = sorted(set(actual) | set(target))
    out = [{"key": k, "actual": actual.get(k), "target": target.get(k),
            "index": (round(actual[k] / target[k] * 100, 1) if actual.get(k) is not None and target.get(k) else None)} for k in keys]
    return {"metric": req.metric, "base": base, "by": req.by, "rows": out}


@app.get("/")
def health():
    return {"service": "innocean-report-api", "reads": MART, "status": "ok"}
