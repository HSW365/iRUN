"""iRun Video job runner: takes queued rows from irun_video_jobs (made by the irun-video edge function from
HSW365studio), renders each with engine/musicvideo.py and saves the finished mp4 + poster to the public
irun-media bucket. Progress is written back to the row so the member watches it fill in the studio.

  python engine/video_jobs.py --peek        # prints how many jobs are waiting (exit 0) - used to skip idle runs
  python engine/video_jobs.py [--max 2] [--id <job id>]
"""
import argparse
import datetime as dt
import json
import os
import shutil
import sys
import time
import traceback

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402

UPLOADS = "irun-video"
STALE_HOURS = 3


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def log(*a):
    print("[jobs]", *a, flush=True)


def queued(limit=5, jid=None):
    q = "status=eq.queued&order=created_at.asc&limit=%d" % limit
    if jid:
        q = f"id=eq.{jid}&status=in.(queued,failed)"
    return db.select("irun_video_jobs", q + "&select=*")


def claim(job):
    """Atomically flip queued -> rendering. Returns False when another run took it first."""
    r = requests.patch(f"{db.URL}/rest/v1/irun_video_jobs?id=eq.{job['id']}&status=in.(queued,failed)",
                       headers=db._h({"Prefer": "return=representation"}),
                       json={"status": "rendering", "started_at": now(), "progress": 1, "stage": "Starting",
                             "error": None}, timeout=30)
    r.raise_for_status()
    return bool(r.json())


def reap_stale():
    """A run that died mid-render leaves a row in 'rendering'; fail it so the member can start again."""
    cut = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=STALE_HOURS)).isoformat()
    for j in db.select("irun_video_jobs", f"status=eq.rendering&started_at=lt.{cut}&select=id"):
        db.update("irun_video_jobs", {"id": j["id"]},
                  {"status": "failed", "stage": None, "finished_at": now(),
                   "error": "The render stopped before it finished. It didn't count against your plan. Try again."})
        log("reaped", j["id"])


def fetch(path, dest):
    r = requests.get(f"{db.URL}/storage/v1/object/{UPLOADS}/{path}",
                     headers={"apikey": db.KEY, "Authorization": f"Bearer {db.KEY}"}, timeout=300)
    r.raise_for_status()
    open(dest, "wb").write(r.content)
    return dest


def run(job, work_root):
    import musicvideo
    jid = job["id"]
    work = os.path.join(work_root, jid)
    os.makedirs(work, exist_ok=True)
    last = [0.0]

    def progress(p, stage):
        log(f"{jid[:8]} {p:3d}% {stage}")
        if time.time() - last[0] > 8 or p >= 80:
            last[0] = time.time()
            try:
                db.update("irun_video_jobs", {"id": jid}, {"progress": int(p), "stage": stage})
            except Exception as e:  # noqa: BLE001
                log("progress write failed", e)

    photo = fetch(job["photo_path"], os.path.join(work, "photo." + job["photo_path"].rsplit(".", 1)[-1]))
    song = fetch(job["song_path"], os.path.join(work, "song." + job["song_path"].rsplit(".", 1)[-1])) \
        if job.get("song_path") else None
    out = os.path.join(work, "video.mp4")
    rep = musicvideo.build(photo, song, out, job["kind"], job["description"], job.get("style") or "cinematic",
                           job.get("length_s") or 60, job.get("title") or "", job.get("artist") or "",
                           os.path.join(work, "w"), progress)
    progress(96, "Saving your video")
    if os.path.getsize(out) > 45 * 1048576:  # keep it under the bucket limit and quick to stream on a phone
        small = out.rsplit(".", 1)[0] + "_s.mp4"
        musicvideo.M.sh(["ffmpeg", "-y", "-v", "error", "-i", out, "-c:v", "libx264", "-preset", "veryfast", "-crf",
                         "21", "-maxrate", "5M", "-bufsize", "10M", "-pix_fmt", "yuv420p", "-c:a", "copy",
                         "-movflags", "+faststart", small])
        os.replace(small, out)
    base = f"video/{job['user_id']}/{jid}"
    vurl = db.upload_public(out, base + ".mp4", "video/mp4")
    purl = db.upload_public(out.rsplit(".", 1)[0] + ".jpg", base + ".jpg", "image/jpeg")
    slim = {k: rep.get(k) for k in ("duration", "bpm", "song_start", "stills", "failed", "balance_start",
                                    "balance_end")}
    db.update("irun_video_jobs", {"id": jid}, {"status": "done", "progress": 100, "stage": "Ready",
                                               "video_url": vurl, "poster_url": purl, "finished_at": now(),
                                               "report": slim})
    log("done", jid, vurl)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--peek", action="store_true")
    ap.add_argument("--max", type=int, default=2)
    ap.add_argument("--id")
    ap.add_argument("--work", default="/tmp/irun-video")
    a = ap.parse_args()
    if not db.enabled():
        raise SystemExit("SUPABASE_URL / SUPABASE_SERVICE_KEY not set")
    if a.peek:
        print(len(queued(1, a.id)))
        return
    reap_stale()
    n = 0
    while n < a.max:
        jobs = queued(1, a.id)
        if not jobs:
            break
        job = jobs[0]
        if not claim(job):
            continue
        n += 1
        try:
            run(job, a.work)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            msg = str(e)
            friendly = msg if ("Upload" in msg or "too short" in msg or "Nothing was charged" in msg) else \
                "The render hit a problem. It didn't count against your plan. Try again, or try a different photo."
            db.update("irun_video_jobs", {"id": job["id"]},
                      {"status": "failed", "stage": None, "error": friendly, "finished_at": now(),
                       "report": {"error": msg[-1500:]}})
        finally:
            shutil.rmtree(os.path.join(a.work, job["id"]), ignore_errors=True)
        if a.id:
            break
    log("rendered", n)


if __name__ == "__main__":
    main()
