#!/usr/bin/env python3
"""Compare hourly GH Archive-compatible sources from the machine it runs on (stdlib only).

For each hour and each source: download throughput, whether the per-hour manifest exists, event
counts by type, WatchEvent count. WatchEvent rows (repo_id, actor_id, created_at) are written to
an NDJSON.gz per source/hour so star capture can be compared later against other ground truth.
Run from the `source-test` workflow; output goes to --out.
"""

from __future__ import annotations

import argparse
import collections
import gzip
import json
import re
import time
import urllib.error
import urllib.request
import zlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

SOURCES = {
    "opendigger": "https://gharchive.open-digger.cn",
    "gharchive": "https://data.gharchive.org",
}
UA = {"User-Agent": "gh-breakout-source-test/0.1 (+https://github.com/Yash-814800/GH-Breakout)"}
TYPE_RE = re.compile(rb'"type":"([A-Za-z]+)"')


def hour_name(ts: datetime) -> str:
    return f"{ts:%Y-%m-%d}-{ts.hour}"


def recent_hours(n: int, lag_hours: int = 3) -> list[datetime]:
    base = datetime.now(UTC).replace(minute=0, second=0, microsecond=0, tzinfo=None)
    return [base - timedelta(hours=lag_hours + i) for i in range(n)][::-1]


def http_status(url: str, method: str = "HEAD", timeout: int = 30) -> tuple[int, dict]:
    req = urllib.request.Request(url, method=method, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers)
    except Exception as e:  # noqa: BLE001
        return -1, {"error": str(e)}


def fetch_manifest(base: str, name: str, out: Path) -> dict:
    url = f"{base}/{name}.manifest.json"
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
        (out / f"manifest_{name}.json").write_bytes(body)
        return {
            "url": url,
            "status": 200,
            "bytes": len(body),
            "seconds": round(time.time() - t0, 2),
        }
    except urllib.error.HTTPError as e:
        return {"url": url, "status": e.code}
    except Exception as e:  # noqa: BLE001
        return {"url": url, "status": -1, "error": str(e)}


def stream_hour(src: str, base: str, name: str, out: Path, max_seconds: int) -> dict:
    url = f"{base}/{name}.json.gz"
    status, headers = http_status(url)
    res: dict = {
        "source": src,
        "url": url,
        "head_status": status,
        "content_length": int(headers.get("Content-Length", 0) or 0),
    }
    if status != 200:
        return res
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    types: collections.Counter = collections.Counter()
    watch_path = out / f"watch_{src}_{name}.ndjson.gz"
    nbytes = lines = 0
    tail = b""
    t0 = time.time()
    first_byte = None
    complete = False
    marks: list[tuple[float, int]] = []
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=60) as r, gzip.open(watch_path, "wb") as wf:
            while True:
                if time.time() - t0 > max_seconds:
                    break
                chunk = r.read(1 << 20)
                if first_byte is None:
                    first_byte = time.time() - t0
                if not chunk:
                    complete = True
                    break
                nbytes += len(chunk)
                marks.append((time.time() - t0, nbytes))
                data = tail + d.decompress(chunk)
                parts = data.split(b"\n")
                tail = parts.pop()
                for line in parts:
                    lines += 1
                    m = TYPE_RE.search(line)
                    if not m:
                        continue
                    t = m.group(1).decode()
                    types[t] += 1
                    if t == "WatchEvent":
                        try:
                            e = json.loads(line)
                            wf.write(
                                (
                                    json.dumps([e["repo"]["id"], e["actor"]["id"], e["created_at"]])
                                    + "\n"
                                ).encode()
                            )
                        except Exception:  # noqa: BLE001
                            types["_bad_watch"] += 1
    except Exception as e:  # noqa: BLE001
        res["error"] = f"{type(e).__name__}: {e}"
    secs = time.time() - t0
    # sustained rate over the second half of the transfer (ignores connection setup)
    half = [m for m in marks if m[0] >= secs / 2]
    sustained = None
    if len(half) >= 2 and half[-1][0] > half[0][0]:
        sustained = (half[-1][1] - half[0][1]) / (half[-1][0] - half[0][0])
    res.update(
        complete=complete,
        bytes_downloaded=nbytes,
        seconds=round(secs, 1),
        first_byte_seconds=round(first_byte, 2) if first_byte is not None else None,
        avg_MBps=round(nbytes / secs / 1e6, 3) if secs else None,
        sustained_MBps=round(sustained / 1e6, 3) if sustained else None,
        lines=lines,
        types=dict(types),
        watch_events=types.get("WatchEvent", 0),
    )
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", default="", help="comma list YYYY-MM-DD-H; default: 3 recent hours")
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--max-seconds", type=int, default=900)
    ap.add_argument("--out", default="source_test_out")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.hours:
        names = [h.strip() for h in a.hours.split(",") if h.strip()]
    else:
        names = [hour_name(t) for t in recent_hours(a.n)]
    summary: dict = {
        "started": datetime.now(UTC).isoformat(),
        "hours": names,
        "runs": [],
        "manifests": [],
        "manifest_probe_last_48h": {},
    }
    for name in names:
        for src, base in SOURCES.items():
            summary["manifests"].append(
                {"source": src, "hour": name, **fetch_manifest(base, name, out)}
            )
    # manifest existence over the last 48 complete hours (HEAD only)
    probe = {"opendigger": [0, 0], "gharchive": [0, 0]}
    for t in recent_hours(48, lag_hours=2):
        for src, base in SOURCES.items():
            code, _ = http_status(f"{base}/{hour_name(t)}.manifest.json")
            probe[src][0 if code == 200 else 1] += 1
    summary["manifest_probe_last_48h"] = {
        k: {"found": v[0], "not_found": v[1]} for k, v in probe.items()
    }
    for name in names:
        for src, base in SOURCES.items():
            r = stream_hour(src, base, name, out, a.max_seconds)
            r["hour"] = name
            summary["runs"].append(r)
            print(
                json.dumps(
                    {
                        k: r.get(k)
                        for k in (
                            "source",
                            "hour",
                            "complete",
                            "bytes_downloaded",
                            "seconds",
                            "avg_MBps",
                            "sustained_MBps",
                            "watch_events",
                            "error",
                        )
                    }
                ),
                flush=True,
            )
    summary["finished"] = datetime.now(UTC).isoformat()
    (out / "summary.json").write_text(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
