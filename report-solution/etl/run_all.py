"""일일 ETL 엔트리포인트: 마트 재적재.
   통화정규화(spend_krw/usd)는 소스 v_perf_unified 가 제공하므로 fx_load 불필요.
   (fx_load.py 는 통합뷰 미사용 시 폴백용으로 보관)"""
import subprocess, sys
print("[run_all] build_mart (source=v_perf_unified) ...")
subprocess.run([sys.executable, "build_mart.py"], check=True)
print("[run_all] done")
