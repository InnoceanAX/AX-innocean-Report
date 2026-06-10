"""
gcloud 없이 REST API 로 innocean-report-api 를 Cloud Run 에 배포.
경로: 소스 tar.gz -> GCS 업로드 -> Cloud Build(도커 빌드+푸시) -> Cloud Run v2 -> 공개 IAM.

사용법:
  python deploy_api.py <SA_KEY.json>
"""
import sys, os, io, json, time, tarfile, urllib.request, urllib.error, urllib.parse
from google.oauth2 import service_account
import google.auth.transport.requests as gtr

KEY = sys.argv[1] if len(sys.argv) > 1 else "innocean-perf-apac-kr-40e02bc0d0d8.json"
PROJ = "innocean-perf-apac-kr"
PROJNUM = "291757702623"
REG = "asia-northeast3"
SVC = "innocean-report-api"
RUNTIME_SA = os.environ.get("REPORT_API_RUNTIME_SA", "perf-data-analyst@innocean-perf-apac-kr.iam.gserviceaccount.com")
BUCKET = "innocean-perf-apac-kr_cloudbuild"
IMAGE = f"{REG}-docker.pkg.dev/{PROJ}/cloud-run-source-deploy/{SVC}:latest"
API_DIR = os.path.join(os.path.dirname(__file__), "..", "api")

creds = service_account.Credentials.from_service_account_file(KEY, scopes=["https://www.googleapis.com/auth/cloud-platform"])

def tok():
    creds.refresh(gtr.Request()); return creds.token

def http(method, url, body=None, ctype="application/json", raw=False):
    data = body if raw else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(url, data=data, method=method,
        headers={"Authorization": "Bearer " + tok(), **({"Content-Type": ctype} if data else {})})
    try:
        r = urllib.request.urlopen(req, timeout=120)
        t = r.read().decode()
        return r.status, (json.loads(t) if t else {})
    except urllib.error.HTTPError as e:
        return e.code, {"_err": e.read().decode()[:500]}

# 1) 소스 tar.gz (Dockerfile context: main.py, requirements.txt, Dockerfile)
print("1) packaging source...")
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz") as tf:
    for f in ["main.py", "requirements.txt", "Dockerfile"]:
        tf.add(os.path.join(API_DIR, f), arcname=f)
blob = buf.getvalue()
OBJ = f"source/{SVC}-deploy.tgz"
print(f"   {len(blob)} bytes -> gs://{BUCKET}/{OBJ}")

# 2) GCS 업로드 (media upload)
print("2) uploading to GCS...")
up = f"https://storage.googleapis.com/upload/storage/v1/b/{BUCKET}/o?uploadType=media&name={urllib.parse.quote(OBJ, safe='')}"
st, r = http("POST", up, body=blob, ctype="application/gzip", raw=True)
print("   upload:", st, r.get("name", r))
assert st < 300, r

# 3) Cloud Build (build + push)
print("3) Cloud Build...")
build = {"source": {"storageSource": {"bucket": BUCKET, "object": OBJ}},
         "steps": [{"name": "gcr.io/cloud-builders/docker", "args": ["build", "-t", IMAGE, "."]}],
         "images": [IMAGE], "timeout": "1200s"}
st, r = http("POST", f"https://cloudbuild.googleapis.com/v1/projects/{PROJ}/builds", body=build)
print("   submit:", st, r.get("name", r.get("_err")))
assert st < 300, r
bid = r["metadata"]["build"]["id"]
print("   build id:", bid)
DEPLOY_IMAGE = IMAGE
while True:
    time.sleep(12)
    _, b = http("GET", f"https://cloudbuild.googleapis.com/v1/projects/{PROJ}/builds/{bid}")
    s = b.get("status")
    print("   ...", s)
    if s in ("SUCCESS", "FAILURE", "INTERNAL_ERROR", "TIMEOUT", "CANCELLED"):
        assert s == "SUCCESS", f"build {s}: {b.get('logUrl')}"
        digest = (b.get("results", {}).get("images", [{}])[0] or {}).get("digest")
        if digest:
            DEPLOY_IMAGE = IMAGE.split(":")[0] + "@" + digest
            print("   image digest:", digest)
        break

# 4) Cloud Run v2 create-or-update
print("4) Cloud Run deploy...")
svc_body = {
    "template": {
        "containers": [{"image": DEPLOY_IMAGE, "ports": [{"containerPort": 8080}],
                         "resources": {"limits": {"memory": "512Mi", "cpu": "1"}},
                         "env": [{"name": "BQ_PROJECT", "value": PROJ}]}],
        "serviceAccount": RUNTIME_SA,
        "timeout": "60s",
    },
    "ingress": "INGRESS_TRAFFIC_ALL",
}
base = f"https://run.googleapis.com/v2/projects/{PROJ}/locations/{REG}/services"
st, r = http("POST", f"{base}?serviceId={SVC}", body=svc_body)
if st == 409:
    print("   exists -> PATCH")
    st, r = http("PATCH", f"{base}/{SVC}", body=svc_body)
print("   op:", st, r.get("name", r.get("_err")))
assert st < 300, r
opname = r["name"]
for _ in range(60):
    time.sleep(6)
    _, o = http("GET", f"https://run.googleapis.com/v2/{opname}")
    if o.get("done"):
        assert "error" not in o, o
        break
print("   service ready")

# 5) 공개 IAM (allUsers invoker)
print("5) setIamPolicy allUsers->run.invoker...")
pol = {"policy": {"bindings": [{"role": "roles/run.invoker", "members": ["allUsers"]}]}}
st, r = http("POST", f"{base}/{SVC}:setIamPolicy", body=pol)
print("   iam:", st, r.get("_err", "ok"))

# 6) URL
_, s = http("GET", f"{base}/{SVC}")
print("\n=== DEPLOYED ===")
print("URL:", s.get("uri"))
