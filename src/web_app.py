import csv
import json
import os
import re
import time
from io import BytesIO

from flask import Flask, redirect, render_template, request, send_file, url_for

from cli import run_pipeline


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(__name__, template_folder=TEMPLATES_DIR, static_folder=STATIC_DIR)


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/run", methods=["POST"])
def run_scoring():
    job_text = request.form.get("job_text", "").strip()
    use_existing_job = request.form.get("use_existing_job") == "on"
    config_path = request.form.get("config_path", "config.yml").strip() or "config.yml"
    batch_size_raw = request.form.get("batch_size", "").strip()

    files = request.files.getlist("cv_files")
    handles, source_map, missing, link_rows = extract_handles_from_files(files)

    if not handles:
        return render_template(
            "index.html",
            error="No GitHub profile links found in uploaded PDFs.",
            missing=missing,
        )

    candidates_path = write_candidates_csv(handles, source_map)

    if use_existing_job and os.path.exists("job.md"):
        job_path = "job.md"
    else:
        job_path = write_job_md(job_text)

    config_overrides = None
    if batch_size_raw:
        try:
            batch_size = int(batch_size_raw)
            if batch_size > 0:
                config_overrides = {"processing": {"batch_size": batch_size}}
        except ValueError:
            config_overrides = None

    result = run_pipeline(
        candidates_path,
        job_path,
        config_path,
        store_full_resume=False,
        config_overrides=config_overrides,
    )
    write_extracted_links_csv(result["run_dir"], link_rows)
    return redirect(url_for("results", run_dir=result["run_dir"]))


@app.route("/results", methods=["GET"])
def results():
    run_dir = request.args.get("run_dir")
    if not run_dir:
        return redirect(url_for("index"))
    run_dir_abs = run_dir
    if not os.path.isabs(run_dir_abs):
        run_dir_abs = os.path.join(BASE_DIR, run_dir_abs)
    run_id = os.path.basename(run_dir_abs.rstrip("/"))
    scores_path = os.path.join(run_dir_abs, "scores.csv")
    report_path = os.path.join(run_dir_abs, "top_report.md")
    profiles_path = os.path.join(run_dir_abs, "profiles.jsonl")
    batch_path = os.path.join(run_dir_abs, "batch_summary.jsonl")
    links_path = os.path.join(run_dir_abs, "extracted_links.csv")

    scores = read_scores(scores_path, profiles_path)
    batch_summary = read_batch_summary(batch_path)
    extracted_links = read_extracted_links(links_path)
    return render_template(
        "results.html",
        run_dir=run_dir_abs,
        run_id=run_id,
        scores=scores,
        batch_summary=batch_summary,
        extracted_links=extracted_links,
        scores_path=scores_path,
        report_path=report_path,
    )


@app.route("/download/<run_id>/<filename>", methods=["GET"])
def download_file(run_id, filename):
    allowed = {
        "scores.csv",
        "top_report.md",
        "profiles.jsonl",
        "batch_summary.jsonl",
        "extracted_links.csv",
    }
    if filename not in allowed:
        return redirect(url_for("index"))
    run_path = os.path.join(BASE_DIR, "runs", run_id, filename)
    if not os.path.exists(run_path):
        return redirect(url_for("index"))
    try:
        return send_file(run_path, as_attachment=True)
    except Exception as exc:
        return f"Download error: {exc}", 500


def extract_handles_from_files(files):
    text_pattern = re.compile(
        r"(https?://github\.com/[^\s\)\]>,\"']+|github\.com/[^\s\)\]>,\"']+)",
        re.I,
    )
    uri_pattern = re.compile(rb"/URI\s*\(([^)]+)\)")
    bytes_pattern = re.compile(
        rb"https?://(?:www\.)?github\.com/[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)?"
    )
    handles = []
    source_map = {}
    missing = []
    link_rows = []

    for file_storage in files:
        name = file_storage.filename or "uploaded.pdf"
        try:
            data = file_storage.read()
        except Exception:
            missing.append(name)
            continue

        urls = set()
        text = data.decode("latin1", errors="ignore")
        for match in text_pattern.findall(text):
            url = match
            if not url.startswith("http"):
                url = "https://" + url
            clean = _sanitize_github_url(url)
            if clean:
                urls.add(clean)

        for match in uri_pattern.findall(data):
            try:
                decoded = match.decode("utf-8", errors="ignore")
            except Exception:
                continue
            clean = _sanitize_github_url(decoded)
            if clean:
                urls.add(clean)

        for match in bytes_pattern.findall(data):
            try:
                decoded = match.decode("utf-8", errors="ignore")
            except Exception:
                continue
            clean = _sanitize_github_url(decoded)
            if clean:
                urls.add(clean)

        found_handle = False
        for url in urls:
            url = _sanitize_github_url(url)
            if not url:
                continue
            link_type = "other"
            handle = None
            m_profile = re.match(
                r"https?://github\.com/([A-Za-z0-9-]+)(?:/)?$", url, re.I
            )
            if m_profile:
                link_type = "profile"
                handle = m_profile.group(1)
            else:
                m_repo = re.match(
                    r"https?://github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9._-]+)",
                    url,
                    re.I,
                )
                if m_repo:
                    link_type = "repo"
                    handle = m_repo.group(1)

            link_rows.append(
                {
                    "source_file": name,
                    "url": url,
                    "link_type": link_type,
                    "handle": handle,
                }
            )

            if link_type == "profile" and handle:
                if handle.lower() not in [h.lower() for h in handles]:
                    handles.append(handle)
                    source_map[handle] = name
                found_handle = True
        if not found_handle:
            missing.append(name)

    return handles, source_map, missing, link_rows


def write_candidates_csv(handles, source_map):
    os.makedirs("runs", exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    path = os.path.join("runs", f"candidates_{timestamp}.csv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["candidate_id", "candidate_name", "handle", "source_file"],
        )
        writer.writeheader()
        for idx, handle in enumerate(handles, start=1):
            source_file = source_map.get(handle)
            candidate_name = None
            if source_file:
                candidate_name = _normalize_name_from_filename(source_file)
            writer.writerow(
                {
                    "candidate_id": f"c{idx:03d}",
                    "candidate_name": candidate_name,
                    "handle": handle,
                    "source_file": source_file,
                }
            )
    return path


def write_extracted_links_csv(run_dir, link_rows):
    if not link_rows:
        return None
    path = os.path.join(run_dir, "extracted_links.csv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["source_file", "link_type", "handle", "url"]
        )
        writer.writeheader()
        for row in link_rows:
            writer.writerow(row)
    return path


def write_job_md(text):
    os.makedirs("runs", exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    path = os.path.join("runs", f"job_{timestamp}.md")
    content = text or ""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def read_scores(path, profiles_path=None):
    if not os.path.exists(path):
        return []
    profiles = _read_profiles(profiles_path)
    profile_by_handle = {p.get("handle"): p for p in profiles if p.get("handle")}
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            profile = profile_by_handle.get(row.get("handle")) or {}
            rationale = profile.get("score_rationale") or []
            row["score_rationale"] = " | ".join(rationale)
            if not row.get("candidate_name"):
                row["candidate_name"] = profile.get("candidate_name")
            rows.append(row)
        rows.sort(key=lambda r: float(r.get("TotalScore") or 0), reverse=True)
        return rows


def read_batch_summary(path):
    if not path or not os.path.exists(path):
        return []
    summaries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                summaries.append(json.loads(line))
            except Exception:
                continue
    return summaries


def read_extracted_links(path):
    if not path or not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _read_profiles(path):
    if not path or not os.path.exists(path):
        return []
    profiles = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                profiles.append(json.loads(line))
            except Exception:
                continue
    return profiles


def _normalize_name_from_filename(filename):
    name = os.path.splitext(filename)[0]
    name = name.replace("_", " ")
    name = name.replace("+", " ")
    name = re.sub(r"\s+", " ", name)
    return name.strip()


def _sanitize_github_url(raw):
    if not raw:
        return None
    raw = raw.strip()
    raw = raw.replace("www.github.com", "github.com")
    match = re.search(
        r"https?://github\.com/[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)?",
        raw,
        re.I,
    )
    if not match:
        return None
    url = match.group(0)
    return url.rstrip("/\"')>,.;")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
