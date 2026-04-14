"""
Animation export — manages export jobs for map animations to GIF/MP4/WebM.

Actual rendering happens client-side via html2canvas + MediaRecorder.
This module tracks job status and metadata.
"""
import json
import uuid
from datetime import datetime, timezone


def create_export_job(conn, export_type: str = "gif",
                      parameters: dict | None = None,
                      duration_secs: float | None = None,
                      frame_count: int | None = None) -> str:
    eid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO animation_exports
           (id, export_type, status, parameters_json,
            duration_secs, frame_count)
           VALUES (?, ?, 'pending', ?, ?, ?)""",
        (eid, export_type,
         json.dumps(parameters) if parameters else None,
         duration_secs, frame_count),
    )
    conn.commit()
    return eid


def get_export_job(conn, job_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM animation_exports WHERE id = ?",
                       (job_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["parameters"] = json.loads(d["parameters_json"]) if d["parameters_json"] else None
    return d


def list_export_jobs(conn, status: str | None = None,
                     limit: int = 50) -> list[dict]:
    if status:
        rows = conn.execute(
            "SELECT * FROM animation_exports WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            (status, limit)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM animation_exports ORDER BY created_at DESC LIMIT ?",
            (limit,)).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["parameters"] = json.loads(d["parameters_json"]) if d["parameters_json"] else None
        results.append(d)
    return results


def update_export_status(conn, job_id: str, status: str,
                         output_path: str | None = None,
                         file_size: int | None = None,
                         error_message: str | None = None) -> bool:
    valid = {"pending", "rendering", "completed", "failed"}
    if status not in valid:
        return False

    updates = ["status = ?"]
    params = [status]

    if status == "completed":
        updates.append("completed_at = ?")
        params.append(datetime.now(timezone.utc).isoformat())
    if output_path is not None:
        updates.append("output_path = ?"); params.append(output_path)
    if file_size is not None:
        updates.append("file_size = ?"); params.append(file_size)
    if error_message is not None:
        updates.append("error_message = ?"); params.append(error_message)

    params.append(job_id)
    result = conn.execute(
        f"UPDATE animation_exports SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    conn.commit()
    return result.rowcount > 0
