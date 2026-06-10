"""
전용 SA 격리 마무리 — 관리자가 SA를 생성한 뒤 실행.
perf-data-analyst 키로 가능한 부분만 수행:
  1) report_mart 데이터셋에 전용 SA를 READER(읽기전용)로 ACL 부여  (bigquery.datasets.update 보유)
  2) innocean-report-api / report-mart-builder Job 의 런타임 SA를 전용 SA로 재배포

전제(관리자 1회 작업):
  - 전용 SA 생성: report-api-reader@innocean-perf-apac-kr.iam.gserviceaccount.com
  - 프로젝트 역할 roles/bigquery.jobUser 부여(쿼리 잡 실행용, 데이터접근 없음)
  - (마트빌더용 전용 SA를 별도로 두려면 report-mart-builder@ 도 동일 + apac_kr_unified READ)

사용법:
  python finalize_sa.py <SA_KEY.json> <api_reader_sa_email> [builder_sa_email]
"""
import sys, subprocess, os
from google.cloud import bigquery
from google.oauth2 import service_account

KEY = sys.argv[1]
API_SA = sys.argv[2]
BUILDER_SA = sys.argv[3] if len(sys.argv) > 3 else None
PROJECT = "innocean-perf-apac-kr"
MART = f"{PROJECT}.report_mart"

creds = service_account.Credentials.from_service_account_file(KEY)
client = bigquery.Client(credentials=creds, project=PROJECT)

# 1) report_mart 에 API SA 를 READER 로 ACL 부여 (읽기전용)
ds = client.get_dataset(MART)
entries = list(ds.access_entries)
def has(sa, role):
    return any(e.entity_id == sa and e.role == role for e in entries if e.entity_type == "userByEmail")
for sa in [s for s in [API_SA, BUILDER_SA] if s]:
    if not has(sa, "READER"):
        entries.append(bigquery.AccessEntry("READER", "userByEmail", sa))
ds.access_entries = entries
client.update_dataset(ds, ["access_entries"])
print(f"[OK] report_mart READER 부여: {API_SA}" + (f", {BUILDER_SA}" if BUILDER_SA else ""))

# 2) 재배포 (런타임 SA 교체). deploy 스크립트의 RUNTIME_SA 를 env 로 오버라이드할 수 있게 처리.
here = os.path.dirname(__file__)
env = dict(os.environ, REPORT_API_RUNTIME_SA=API_SA)
print("[..] API 재배포 (런타임 SA =", API_SA, ")")
subprocess.run([sys.executable, os.path.join(here, "deploy_api.py"), KEY], env=env, check=True)
if BUILDER_SA:
    env2 = dict(os.environ, REPORT_JOB_RUNTIME_SA=BUILDER_SA)
    print("[..] ETL Job 재배포 (런타임 SA =", BUILDER_SA, ")")
    subprocess.run([sys.executable, os.path.join(here, "deploy_job.py"), KEY], env=env2, check=True)
print("[DONE] 전용 SA 격리 완료 — perf-data-analyst 의존 제거")
