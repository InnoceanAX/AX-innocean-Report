"""
프론트엔드(index.html, nginx) 재배포 — 기존 innocean-report Cloud Run 서비스 업데이트.
REPORT_API_BASE 가 박힌 index.html 을 라이브에 반영 + 데이터 커버리지 배너 활성화.

사용법: python deploy_frontend.py <SA_KEY.json> <frontend_repo_dir>
"""
import sys, os, io, json, time, tarfile, urllib.request, urllib.error, urllib.parse
from google.oauth2 import service_account
import google.auth.transport.requests as gtr

KEY = sys.argv[1]
REPO = sys.argv[2] if len(sys.argv) > 2 else "."
PROJ = "innocean-perf-apac-kr"; REG = "asia-northeast3"
SVC = "innocean-report"
RUNTIME_SA = "291757702623-compute@developer.gserviceaccount.com"
BUCKET = "innocean-perf-apac-kr_cloudbuild"
IMAGE = f"{REG}-docker.pkg.dev/{PROJ}/cloud-run-source-deploy/{SVC}:latest"

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

print("1) packaging frontend...")
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz") as tf:
    for f in ["index.html", "nginx.conf", "Dockerfile"]:
        tf.add(os.path.join(REPO, f), arcname=f)
blob = buf.getvalue(); OBJ = f"source/{SVC}-deploy.tgz"
print(f"   {len(blob)} bytes")

print("2) upload GCS...")
up = f"https://storage.googleapis.com/upload/storage/v1/b/{BUCKET}/o?uploadType=media&name={urllib.parse.quote(OBJ, safe='')}"
st, r = http("POST", up, body=blob, ctype="application/gzip", raw=True); assert st < 300, r

print("3) Cloud Build...")
build = {"source": {"storageSource": {"bucket": BUCKET, "object": OBJ}},
         "steps": [{"name": "gcr.io/cloud-builders/docker", "args": ["build", "-t", IMAGE, "."]}],
         "images": [IMAGE], "timeout": "1200s"}
st, r = http("POST", f"https://cloudbuild.googleapis.com/v1/projects/{PROJ}/builds", body=build); assert st < 300, r
bid = r["metadata"]["build"]["id"]; print("   build", bid)
DEPLOY_IMAGE = IMAGE
while True:
    time.sleep(12)
    _, b = http("GET", f"https://cloudbuild.googleapis.com/v1/projects/{PROJ}/builds/{bid}")
    s = b.get("status"); print("   ...", s)
    if s in ("SUCCESS", "FAILURE", "INTERNAL_ERROR", "TIMEOUT", "CANCELLED"):
        assert s == "SUCCESS", b.get("logUrl")
        # :latest 태그 문자열이 같으면 Cloud Run이 새 리비전을 안 만듦 → digest 로 배포
        digest = (b.get("results", {}).get("images", [{}])[0] or {}).get("digest")
        if digest:
            DEPLOY_IMAGE = IMAGE.split(":")[0] + "@" + digest
            print("   image digest:", digest)
        break

print("4) Cloud Run update...")
body = {"template": {"containers": [{"image": DEPLOY_IMAGE, "ports": [{"containerPort": 8080}]}],
        "serviceAccount": RUNTIME_SA}, "ingress": "INGRESS_TRAFFIC_ALL"}
base = f"https://run.googleapis.com/v2/projects/{PROJ}/locations/{REG}/services"
st, r = http("PATCH", f"{base}/{SVC}", body=body)
if st == 404:
    st, r = http("POST", f"{base}?serviceId={SVC}", body=body)
assert st < 300, r
opname = r["name"]
for _ in range(60):
    time.sleep(6)
    _, o = http("GET", f"https://run.googleapis.com/v2/{opname}")
    if o.get("done"): assert "error" not in o, o; break
_, s = http("GET", f"{base}/{SVC}")
print("\n=== FRONTEND REDEPLOYED ===\nURL:", s.get("uri"))
