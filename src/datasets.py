import csv
import json
import os


def ensure_dataset_dir(base_dir="datasets/resume_samples"):
    os.makedirs(base_dir, exist_ok=True)
    return base_dir


def append_labels(base_dir, rows):
    path = os.path.join(base_dir, "labels.csv")
    exists = os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["candidate_id", "label", "reviewer_note"])
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def append_derived_features(base_dir, rows):
    path = os.path.join(base_dir, "derived_features.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")
    return path
