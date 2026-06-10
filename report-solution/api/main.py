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
# *_index(달성률) -> 실적 base 지표 매핑
INDEX_BASE = {
    "impressions_index": "impressions", "clicks_index": "clicks",
    "conversions_index": "conversions", "costs_index": "costs_krw",
}


@app.get("/api/targets")
def targets_list():
    try:
        rows = client.query(f"SELECT * FROM `{TARGETS}` ORDER BY _updated_at DESC").result()
        return {"targets": [dict(r) for r in rows]}
    except Exception as e:
        return {"targets": [], "error": str(e)[:200]}


class TargetRow(BaseModel):
    metric: str
    target_value: float
    period_start: str
    period_end: str
    platform: Optional[str] = None
    brand_name: Optional[str] = None
    country: Optional[str] = None
    campaign_id: Optional[str] = None
    note: Optional[str] = None


@app.post("/api/targets")
def targets_save(rows: list[TargetRow]):
    """목표 입력(append). media_plan_targets 에만 쓰기권한 보유."""
    if not rows:
        raise HTTPException(400, "no rows")
    payload = []
    for r in rows:
        d = r.model_dump()
        d["_updated_at"] = None  # 서버시각으로 채움
        payload.append(d)
    sql = f"""INSERT INTO `{TARGETS}`
        (metric, target_value, period_start, period_end, platform, brand_name, country, campaign_id, note, _updated_at)
        VALUES (@metric,@target_value,@period_start,@period_end,@platform,@brand_name,@country,@campaign_id,@note,CURRENT_TIMESTAMP())"""
    n = 0
    for r in rows:
        params = [
            bigquery.ScalarQueryParameter("metric", "STRING", r.metric),
            bigquery.ScalarQueryParameter("target_value", "FLOAT64", r.target_value),
            bigquery.ScalarQueryParameter("period_start", "DATE", r.period_start),
            bigquery.ScalarQueryParameter("period_end", "DATE", r.period_end),
            bigquery.ScalarQueryParameter("platform", "STRING", r.platform),
            bigquery.ScalarQueryParameter("brand_name", "STRING", r.brand_name),
            bigquery.ScalarQueryParameter("country", "STRING", r.country),
            bigquery.ScalarQueryParameter("campaign_id", "STRING", r.campaign_id),
            bigquery.ScalarQueryParameter("note", "STRING", r.note),
        ]
        client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
        n += 1
    return {"inserted": n}


class AchieveReq(BaseModel):
    metric: str                      # *_index (예: impressions_index)
    groupby: Optional[str] = None    # 선택 디멘션 (platform/brand_name/...)
    filters: dict = {}
    date_from: Optional[str] = None
    date_to: Optional[str] = None


@app.post("/api/achievement")
def achievement(req: AchieveReq):
    """달성률 = 실적(actual) / 목표(target) * 100. 목표 없으면 target=None."""
    base = INDEX_BASE.get(req.metric)
    if not base or base not in ADDITIVE:
        raise HTTPException(400, f"unsupported index metric: {req.metric}")
    gb = DIMS.get(req.groupby) if req.groupby else None
    # 실적
    aw, ap = ["date IS NOT NULL"], []
    for col, val in (req.filters or {}).items():
        if col in DIMS:
            aw.append(f"{DIMS[col]} = @f_{col}"); ap.append(bigquery.ScalarQueryParameter(f"f_{col}", "STRING", str(val)))
    if req.date_from:
        aw.append("date >= @df"); ap.append(bigquery.ScalarQueryParameter("df", "DATE", req.date_from))
    if req.date_to:
        aw.append("date <= @dt"); ap.append(bigquery.ScalarQueryParameter("dt", "DATE", req.date_to))
    asel = (f"{gb} AS k, " if gb else "") + f"SUM({base}) AS actual"
    asql = f"SELECT {asel} FROM `{PERF}` WHERE {' AND '.join(aw)}" + (f" GROUP BY 1" if gb else "")
    actual = {(r.get("k") if gb else "_"): r["actual"] for r in [dict(x) for x in client.query(asql, job_config=bigquery.QueryJobConfig(query_parameters=ap)).result()]}
    # 목표 (기간 겹침 + 동일 scope). 목표테이블에 실제 존재하는 컬럼으로만 그룹화.
    TARGET_DIMS = {"platform", "brand_name", "country"}   # campaign 은 name/id 불일치로 그룹 제외
    tgb = req.groupby if req.groupby in TARGET_DIMS else None
    tw, tp = ["metric=@m"], [bigquery.ScalarQueryParameter("m", "STRING", base)]
    for col, val in (req.filters or {}).items():
        if col in ("platform", "brand_name", "country", "campaign_id"):
            tw.append(f"{col}=@t_{col}"); tp.append(bigquery.ScalarQueryParameter(f"t_{col}", "STRING", str(val)))
    if req.date_to:
        tw.append("period_start <= @dt2"); tp.append(bigquery.ScalarQueryParameter("dt2", "DATE", req.date_to))
    if req.date_from:
        tw.append("period_end >= @df2"); tp.append(bigquery.ScalarQueryParameter("df2", "DATE", req.date_from))
    tsel = (f"{tgb} AS k, " if tgb else "") + "SUM(target_value) AS target"
    tsql = f"SELECT {tsel} FROM `{TARGETS}` WHERE {' AND '.join(tw)}" + (" GROUP BY 1" if tgb else "")
    trows = [dict(x) for x in client.query(tsql, job_config=bigquery.QueryJobConfig(query_parameters=tp)).result()]
    if tgb:
        target = {r.get("k"): r["target"] for r in trows}
    else:
        # 그룹 불가(또는 무그룹): 전체 목표 합을 단일 키로
        total_t = trows[0]["target"] if trows else None
        target = {"_": total_t} if not gb else {}  # gb 있는데 목표 그룹불가 → 그룹별 목표 None
    keys = set(actual) | set(target)
    out = []
    for k in keys:
        a, t = actual.get(k), target.get(k)
        out.append({"key": k, "actual": a, "target": t,
                    "index": (round(a / t * 100, 1) if (a is not None and t) else None)})
    return {"metric": req.metric, "base": base, "groupby": req.groupby, "rows": out}


@app.get("/")
def health():
    return {"service": "innocean-report-api", "reads": MART, "status": "ok"}
