"""
ETL(build_mart.py)을 Cloud Run Job 으로 배포 + 매일 03:30 KST Cloud Scheduler 트리거.
수집(03:00) 직후 마트 재적재. 런타임 SA = perf-data-analyst (raw READ + report_mart WRITE).

사용법: python deploy_job.py <SA_KEY.json>
"""
import sys, os, io, json, time, tarfile, urllib.request, urllib.error, urllib.parse
from google.oauth2 import service_account
import google.auth.transport.requests as gtr

KEY = sys.argv[1]
PROJ = "innocean-perf-apac-kr"; REG = "asia-northeast3"
JOB = "report-mart-builder"
RUNTIME_SA = os.environ.get("REPORT_JOB_RUNTIME_SA", "perf-data-analyst@innocean-perf-apac-kr.iam.gserviceaccount.com")
BUCKET = "innocean-perf-apac-kr_cloudbuild"
IMAGE = f"{REG}-docker.pkg.dev/{PROJ}/cloud-run-source-deploy/{JOB}:latest"
ETL_DIR = os.path.join(os.path.dirname(__file__), "..", "etl")

creds = service_account.Credentials.from_service_account_file(KEY, scopes=["https://www.googleapis.com/auth/cloud-platform"])
def tok(): creds.refresh(gtr.Request()); return creds.token
def http(method, url, body=None, ctype="application/json", raw=False):
    data = body if raw else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(url, data=data, method=method,
        headers={"Authorization": "Bearer " + tok(), **({"Content-Type": ctype} if data else {})})
    try:
        r = urllib.request.urlopen(req, timeout=120); t = r.read().decode()
        return r.status, (json.loads(t) if t else {})
    except urllib.error.HTTPError as e:
        return e.code, {"_err": e.read().decode()[:500]}

# 1-3) package + upload + build
print("1) package + upload...")
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz") as tf:
    for f in ["build_mart.py", "fx_load.py", "run_all.py", "requirements.txt", "Dockerfile"]:
        tf.add(os.path.join(ETL_DIR, f), arcname=f)
OBJ = f"source/{JOB}-deploy.tgz"
up = f"https://storage.googleapis.com/upload/storage/v1/b/{BUCKET}/o?uploadType=media&name={urllib.parse.quote(OBJ, safe='')}"
st, r = http("POST", up, body=buf.getvalue(), ctype="application/gzip", raw=True); assert st < 300, r

print("2) Cloud Build...")
build = {"source": {"storageSource": {"bucket": BUCKET, "object": OBJ}},
         "steps": [{"name": "gcr.io/cloud-builders/docker", "args": ["build", "-t", IMAGE, "."]}],
         "images": [IMAGE], "timeout": "1200s"}
st, r = http("POST", f"https://cloudbuild.googleapis.com/v1/projects/{PROJ}/builds", body=build); assert st < 300, r
bid = r["metadata"]["build"]["id"]
DEPLOY_IMAGE = IMAGE
while True:
    time.sleep(12)
    _, b = http("GET", f"https://cloudbuild.googleapis.com/v1/projects/{PROJ}/builds/{bid}")
    s = b.get("status"); print("   ...", s)
    if s in ("SUCCESS", "FAILURE", "INTERNAL_ERROR", "TIMEOUT", "CANCELLED"):
        assert s == "SUCCESS", b.get("logUrl")
        digest = (b.get("results", {}).get("images", [{}])[0] or {}).get("digest")
        if digest:
            DEPLOY_IMAGE = IMAGE.split(":")[0] + "@" + digest
            print("   image digest:", digest)
        break

# 4) Cloud Run Job create-or-update
print("3) Cloud Run Job...")
jobbody = {"template": {"template": {
    "containers": [{"image": DEPLOY_IMAGE, "resources": {"limits": {"memory": "1Gi", "cpu": "1"}}}],
    "serviceAccount": RUNTIME_SA, "maxRetries": 1, "timeout": "900s"}}}
base = f"https://run.googleapis.com/v2/projects/{PROJ}/locations/{REG}/jobs"
st, r = http("POST", f"{base}?jobId={JOB}", body=jobbody)
if st == 409:
    st, r = http("PATCH", f"{base}/{JOB}", body=jobbody)
assert st < 300, r
opname = r["name"]
for _ in range(40):
    time.sleep(5)
    _, o = http("GET", f"https://run.googleapis.com/v2/{opname}")
    if o.get("done"): assert "error" not in o, o; break
print("   job ready")

# 5) 첫 실행 (즉시 1회 트리거)
print("4) first run...")
st, r = http("POST", f"{base}/{JOB}:run", body={})
print("   run:", st, r.get("name", r.get("_err")))

# 6) Cloud Scheduler 매일 03:30 KST
print("5) Cloud Scheduler 03:30 KST...")
sb = "https://cloudscheduler.googleapis.com/v1/projects/{}/locations/{}/jobs".format(PROJ, REG)
sched = {
    "name": f"projects/{PROJ}/locations/{REG}/jobs/{JOB}-trigger",
    "schedule": "30 3 * * *", "timeZone": "Asia/Seoul",
    "httpTarget": {
        "uri": f"https://{REG}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/{PROJ}/jobs/{JOB}:run",
        "httpMethod": "POST",
        "oauthToken": {"serviceAccountEmail": RUNTIME_SA, "scope": "https://www.googleapis.com/auth/cloud-platform"},
    },
}
st, r = http("POST", sb, body=sched)
if st == 409:
    st, r = http("PATCH", f"{sb}/{JOB}-trigger?updateMask=schedule,timeZone,httpTarget", body=sched)
print("   scheduler:", st, r.get("name", r.get("_err")))
print("\n=== ETL JOB + SCHEDULER DEPLOYED ===")
print(f"job: {JOB}  schedule: 30 3 * * * Asia/Seoul")
