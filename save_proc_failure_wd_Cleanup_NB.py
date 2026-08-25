#!/usr/bin/env python3
import os
import requests
import logging
import configparser
from datetime import datetime, timezone, timedelta

import boto3
from botocore.config import Config

BASE_URL = "https://portal.cbrain.mcgill.ca"

# REAL uploads enabled
DRY_RUN_UPLOADS = False 
# Keep zapping disabled for now 
DRY_RUN_ZAP = True

# -----------------------
# Central S3 log archive (goal destination)
# -----------------------
CENTRAL_LOG_BUCKET = "midb-hbcd-main-deid"
CENTRAL_LOG_PREFIX = "cbrain_std_logs"

# -----------------------
# ONLY TEST THESE TASKS
# -----------------------
# TARGET_TASK_IDS = {3249717, 3249711}


# -----------------------
# Token loader
# -----------------------
def load_cbrain_token():
    print("[DEBUG] Loading CBRAIN token")
    token_path = os.getenv(
        "CBRAIN_TOKEN_PATH",
        os.path.expanduser("~/.config/cbrain/token.cred")
    )
    print(f"[DEBUG] Token path: {token_path}")
    with open(token_path) as f:
        token = f.read().strip()
    print("[DEBUG] Token loaded successfully")
    return token


# -----------------------
# Generic fetcher
# -----------------------
def fetch_cbrain_objects(token, model, params=None, target_ids=None):
    print(f"[DEBUG] Fetching model: {model}")
    if params is None:
        params = {}
    url = f"{BASE_URL}/{model}.json"
    all_results = []
    page = 1
    per_page = 999

    while True:
        print(f"[DEBUG] Requesting {model} page={page}")
        request_params = {
            "cbrain_api_token": token,
            "page": page,
            "per_page": per_page,
            "_simple_filters": 1,
            **params
        }
        print(f"[DEBUG] Request params: page={page}, filters={params}")
        resp = requests.get(
            url,
            params=request_params,
            headers={"Accept": "application/json"},
            timeout=30
        )
        print(f"[DEBUG] HTTP {resp.status_code} for {model} page {page}")
        if resp.status_code != 200:
            print(f"[ERROR] Response: {resp.text[:300]}")
            raise RuntimeError("Fetch failed")

        page_data = resp.json()
        print(f"[DEBUG] Received {len(page_data)} records")

        if not page_data:
            print("[DEBUG] No more data  breaking pagination")
            break

        all_results.extend(page_data)

        # Early exit: stop paginating once all target tasks are found
        if target_ids and model == "tasks":
            found = {t["id"] for t in all_results}
            if target_ids.issubset(found):
                print(f"[DEBUG] All target tasks found on page {page}, stopping early")
                break

        # Clean exit: last page has fewer records than per_page
        if len(page_data) < per_page:
            print(f"[DEBUG] Partial page ({len(page_data)} < {per_page})  last page, breaking")
            break

        page += 1

    print(f"[DEBUG] DONE fetching {model}: total {len(all_results)}")
    return all_results


# -----------------------
# Task logs fetch
# -----------------------
def fetch_task_logs(token, task_id):
    print(f"[DEBUG] Fetching logs for task {task_id}")
    resp = requests.get(
        f"{BASE_URL}/tasks/{task_id}.json",
        params={"cbrain_api_token": token, "get_task_outputs": 1},
        headers={"Accept": "application/json"},
        timeout=30
    )
    print(f"[DEBUG] Logs HTTP {resp.status_code} for task {task_id}")
    if resp.status_code != 200:
        print(f"[ERROR] Logs fetch failed for {task_id}: {resp.text[:200]}")
        return None
    print(f"[DEBUG] Logs received for task {task_id}")
    return resp.json()


# -----------------------
# Local staging
# -----------------------
def save_local(task_id, stdout, stderr, tmp_dir):
    print(f"[DEBUG] Saving logs locally for task {task_id}")
    os.makedirs(tmp_dir, exist_ok=True)
    out_path = os.path.join(tmp_dir, f"{task_id}.out")
    err_path = os.path.join(tmp_dir, f"{task_id}.err")
    with open(out_path, "w") as f:
        f.write(stdout or "")
    with open(err_path, "w") as f:
        f.write(stderr or "")
    print(f"[DEBUG] Saved local files for task {task_id}")
    return out_path, err_path


# -----------------------
# S3 client
# -----------------------
def create_s3_client(cfg_path):
    print("[DEBUG] Creating S3 client")
    cfg = configparser.ConfigParser()
    cfg.read(cfg_path)
    print(f"[DEBUG] S3 host: {cfg['default']['host_base']}")
    client = boto3.client(
        "s3",
        aws_access_key_id=cfg['default']['access_key'],
        aws_secret_access_key=cfg['default']['secret_key'],
        endpoint_url="https://" + cfg['default']['host_base'],
        config=Config(
            s3={"payload_signing_enabled": True},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required"
        )
    )
    print("[DEBUG] S3 client ready")
    return client


# -----------------------
# DP INFO
# -----------------------
def get_dp_info(token, session_dp_names):
    print("[DEBUG] Fetching DP info")
    dps = fetch_cbrain_objects(token, "data_providers")
    dp_map = {}
    for dp in dps:
        if dp["name"] in session_dp_names:
            print(f"[DEBUG] Matched DP: {dp['name']} ({dp['id']})")
            dp_map[dp["id"]] = {
                "name": dp["name"],
                "bucket": dp["cloud_storage_client_bucket_name"],
                "prefix": dp["cloud_storage_client_path_start"]
            }
    print(f"[DEBUG] Total matched DPs: {len(dp_map)}")
    return dp_map


# -----------------------
# S3 upload helper (with skip-if-exists)
# -----------------------
def upload_to_s3(s3_client, local_path, bucket, s3_key, dry_run=False):
    """Upload a single file to S3. Skips if the key already exists."""
    # Check if already exists to avoid redundant daily re-uploads
    try:
        s3_client.head_object(Bucket=bucket, Key=s3_key)
        print(f"[DEBUG] Already exists, skipping: s3://{bucket}/{s3_key}")
        return True
    except Exception:
        pass  # Key does not exist  proceed with upload

    with open(local_path, "rb") as f:
        file_bytes = f.read()

    print(f"[DEBUG] Uploading {local_path} ({len(file_bytes)} bytes)  s3://{bucket}/{s3_key}")

    if DRY_RUN_UPLOADS:
        print(f"[DRY RUN] Would upload to s3://{bucket}/{s3_key}")
        return True

    s3_client.put_object(
        Bucket=bucket,
        Key=s3_key,
        Body=file_bytes,
        ContentLength=len(file_bytes)
    )
    return True


# -----------------------
# SAFE batch zap
# -----------------------
def batch_zap_wd(token, task_ids, dry_run=True):
    if not task_ids:
        print("[DEBUG] No tasks to zap")
        return
    print(f"[DEBUG] ZAP batch size: {len(task_ids)}")
    if dry_run:
        print(f"[DRY RUN] Would zap: {task_ids}")
        return
    resp = requests.post(
        f"{BASE_URL}/tasks/operation",
        json={
            "cbrain_api_token": token,
            "tasklist": task_ids,
            "operation": "zap_wd"
        }
    )
    print(f"[DEBUG] Zap HTTP {resp.status_code}")
    if resp.status_code != 200:
        print(f"[ERROR] Zap failed: {resp.text}")
        raise RuntimeError("Zap failed")
    print(f"[DEBUG] Zap success")


# -----------------------
# PROCESS TASKS
# -----------------------
def process_tasks(token, tasks, s3_client, dp_map, tmp_dir):
    print(f"[DEBUG] Starting task processing. Total tasks: {len(tasks)}")
    zap_candidates = []

    for task in tasks:
        task_id = task["id"]
        print(f"\n[DEBUG] --- TASK START {task_id} ---")

        # if task_id not in TARGET_TASK_IDS:
        #     print(f"[DEBUG] Skip {task_id} (not target)")
        #     continue

        if task["status"] not in ["Completed", "Failed On Cluster"]:
            print(f"[DEBUG] Skip {task_id} (status={task['status']})")
            continue

        dp_id = task.get("results_data_provider_id")
        if dp_id not in dp_map:
            print(f"[DEBUG] Skip {task_id} (DP not in map)")
            continue

        dp_bucket = dp_map[dp_id]["bucket"]
        dp_prefix = dp_map[dp_id]["prefix"]
        print(f"[DEBUG] Task {task_id} dp_bucket={dp_bucket}, dp_prefix={dp_prefix}")

        try:
            # -------------------
            # Fetch full task info and check workdir
            # -------------------
            info = fetch_task_logs(token, task_id)
            if not info:
                print(f"[DEBUG] Skip {task_id} (no task info returned)")
                continue

            print(f"[DEBUG] Task {task_id} info keys: {list(info.keys())}")

            wd_size = info.get("cluster_workdir_size")
            has_wd = wd_size is not None and wd_size > 0
            print(f"[DEBUG] Task {task_id} has_workdir={has_wd}, workdir_size={wd_size}")

            if not has_wd:
                print(f"[DEBUG] Skip {task_id} (workdir absent or size=0)")
                continue

            is_archived = info.get("workdir_archived", False)
            if is_archived:
                print(f"[DEBUG] Skip {task_id} (workdir already archived)")
                continue

            # -------------------
            # Extract logs and save locally (staging)
            # -------------------
            stdout = info.get("cluster_stdout", "")
            stderr = info.get("cluster_stderr", "")
            out_path, err_path = save_local(task_id, stdout, stderr, tmp_dir)

            # -------------------
            # Upload 1: Respective DP location (original behavior)
            # Destination: s3://<dp_bucket>/<dp_prefix>/<task_id>.out
            # -------------------
            print(f"[DEBUG] Upload to DP location START {task_id}")
            dp_upload_ok = True
            for local_path, s3_key in [
                (out_path, f"{dp_prefix}/{task_id}.out"),
                (err_path, f"{dp_prefix}/{task_id}.err")
            ]:
                ok = upload_to_s3(s3_client, local_path, dp_bucket, s3_key, dry_run=DRY_RUN_UPLOADS)
                if not ok:
                    dp_upload_ok = False
            print(f"[DEBUG] Upload to DP location DONE {task_id} (success={dp_upload_ok})")

            # -------------------
            # Upload 2: Central log archive (goal destination)
            # Destination: s3://midb-hbcd-main-deid/cbrain_std_logs/<task_id>.out
            # -------------------
            print(f"[DEBUG] Upload to central log archive START {task_id}")
            central_upload_ok = True
            for local_path, s3_key in [
                (out_path, f"{CENTRAL_LOG_PREFIX}/{task_id}.out"),
                (err_path, f"{CENTRAL_LOG_PREFIX}/{task_id}.err")
            ]:
                ok = upload_to_s3(s3_client, local_path, CENTRAL_LOG_BUCKET, s3_key, dry_run=DRY_RUN_UPLOADS)
                if not ok:
                    central_upload_ok = False
            print(f"[DEBUG] Upload to central log archive DONE {task_id} (success={central_upload_ok})")

            # -------------------
            # Clean up local temp files after both uploads
            # -------------------
            try:
                os.remove(out_path)
                os.remove(err_path)
                print(f"[DEBUG] Cleaned up local temp files for task {task_id}")
            except Exception as e:
                print(f"[WARN] Could not clean up temp files for {task_id}: {e}")

            # -------------------
            # Add to zap list only if both uploads succeeded
            # -------------------
            if dp_upload_ok and central_upload_ok:
                zap_candidates.append(task_id)
            else:
                print(f"[WARN] Skipping zap for {task_id} due to upload failure")

        except Exception as e:
            print(f"[ERROR] Error processing {task_id}: {e}")

    print(f"[DEBUG] Zap candidates: {zap_candidates}")

    # Uncomment later if desired
    #for i in range(0, len(zap_candidates), 50):
        #batch = zap_candidates[i:i + 50]
        #print(f"[DEBUG] Zapping batch: {batch}")
        #batch_zap_wd(token, batch, dry_run=DRY_RUN)


# -----------------------
# MAIN
# -----------------------
if __name__ == "__main__":
    print("[DEBUG] Pipeline start")
    log_file = "/projects/standard/midb_hbcd/shared/bilas003_scripts/cbrain_pipeline.log"
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )
    print(f"[DEBUG] DRY_RUN_UPLOADS = {DRY_RUN_UPLOADS}")
    print(f"[DEBUG] DRY_RUN_ZAP = {DRY_RUN_ZAP}")

    token = load_cbrain_token()

    print(" Fetching tasks from CBRAIN")

    DAYS_CUTOFF = 30
    cutoff_date = (
    datetime.now(timezone.utc) -
    timedelta(days=DAYS_CUTOFF)
    ).strftime("%Y-%m-%d")

    tasks = fetch_cbrain_objects(
        token,
        "tasks",
        params={
            "status[]": ["Completed", "Failed On Cluster"],
            "created_at": f">{cutoff_date}"
        },
        # target_ids=TARGET_TASK_IDS
    )

    #DAYS_CUTOFF = 60
    #cutoff_date = datetime.now(timezone.utc) - timedelta(days=DAYS_CUTOFF)
    #tasks = [
        #t for t in tasks
        #if datetime.fromisoformat(t["updated_at"].replace("Z", "+00:00")) >= cutoff_date
    #]
    #print(f"[DEBUG] Tasks after date filter (last {DAYS_CUTOFF} days): {len(tasks)}")

    print(f"Fetched: {len(tasks)} tasks")

    session_data_provider_names = [
        'HBCD-Main-V02-Derivatives',
        'HBCD-Main-V03-Derivatives',
        'HBCD-Main-V04-Derivatives',
        'HBCD-Main-P04-Derivatives',
        'HBCD-Main-P06-Derivatives',
        'HBCD-Main-V06-Derivatives',
        'HBCD-Main-V08-Derivatives',
        'HBCD-Main-Anon-Derivatives-V02-V2',
        'HBCD-Main-Anon-Derivatives-V04-V2',
        'HBCD-Main-Anon-Derivatives-V06-V2',
        'HBCD-Main-Anon-Derivatives-P04-V2',
        'HBCD-Main-Anon-Derivatives-P06-V2',
        'HBCD-Main-Anon-Derivatives-V03-V2',
        'HBCD-Main-Anon-Derivatives-V08-V2'

    ]

    dp_map = get_dp_info(token, session_data_provider_names)

    s3cfg = "/projects/standard/midb_hbcd/shared/pandh015_scripts/s3cfg/msi-midb-hbcd.s3cfg"
    print(" Creating S3 client")
    s3_client = create_s3_client(s3cfg)

    # tasks = [t for t in tasks if t["id"] in TARGET_TASK_IDS]
    # print(f"[DEBUG] Filtered to {len(tasks)} target tasks: {[t['id'] for t in tasks]}")

    tmp_dir = "/projects/standard/midb_hbcd/shared/bilas003_scripts/cbrain_logs"
    print(f"[DEBUG] Total tasks to process: {len(tasks)}")
    # input("Press Enter to continue or Ctrl+C to abort...")

    process_tasks(
        token,
        tasks,
        s3_client,
        dp_map,
        tmp_dir
    )
    print(" Pipeline completed")
