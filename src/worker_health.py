"""Small read-only health command for local operations."""

import argparse
import json
import os
import sqlite3

from crawl_jobs import list_jobs
from storage.sqlite_store import init_db


def health(db_path: str) -> dict:
    init_db(db_path)
    jobs = list_jobs(db_path)
    active = [j for j in jobs if j["status"] in {"queued", "running", "waiting", "retrying"}]
    running = [j for j in active if j["status"] == "running"]
    return {
        "database": os.path.abspath(db_path),
        "database_exists": os.path.exists(db_path),
        "active_jobs": len(active),
        "running_jobs": len(running),
        "jobs": [{"id": j["job_id"], "package_id": j["package_id"], "status": j["status"],
                  "heartbeat_at": j["heartbeat_at"], "last_event": j["last_event"]} for j in jobs[:20]],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Show Mericrawler queue health")
    parser.add_argument("--db", default="data/reviews.db")
    args = parser.parse_args()
    print(json.dumps(health(args.db), indent=2))
