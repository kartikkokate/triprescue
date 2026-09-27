"""Nugen alignment pipeline for the TripRescue Advisor model.

  Base model -> Nugen alignment on the TripRescue dataset -> domain-aligned model
  -> deployed -> used by the app (app.nugen_client) for inference.

Each step records its ids in nugen/state.json, so re-running `run` resumes where it
stopped instead of re-uploading or re-training.

Usage (from backend/, with NUGEN_API_KEY in backend/.env):
  python -m nugen.build_dataset                  # 1. generate the dataset + benchmark
  python -m nugen.align base-models              # 2. pick an alignment-ready base model
  python -m nugen.align run --base-model <id>    # 3. upload, align, deploy (resumable)
  python -m nugen.align status                   #    show pipeline progress
  python -m nugen.align ask "TASK: ..."          # 4. query the deployed aligned model
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

from nugen import pipeline_state
from nugen.build_dataset import BENCHMARK_PATH, TRAIN_PATH

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)

BASE_URL = os.environ.get("NUGEN_BASE_URL", "https://api.nugen.in")
ALIGNMENT_NAME = "TripRescue Advisor"
POLL_SECONDS = 15


def _headers() -> dict:
    key = os.environ.get("NUGEN_API_KEY")
    if not key:
        sys.exit("NUGEN_API_KEY is not set - add it to backend/.env")
    return {"Authorization": f"Bearer {key}"}


def _request(method: str, path: str, **kwargs) -> dict:
    resp = httpx.request(method, f"{BASE_URL}{path}", headers=_headers(), timeout=120, **kwargs)
    if resp.status_code >= 400:
        sys.exit(f"{method} {path} failed: HTTP {resp.status_code}: {resp.text[:500]}")
    return resp.json() if resp.content else {}


def _wait(label: str, path: str, done: set[str], failed: set[str] = frozenset({"FAILED", "ERROR"})) -> dict:
    while True:
        data = _request("GET", path)
        status = data.get("status")
        extra = f" progress={data['progress']}" if data.get("progress") is not None else ""
        extra += f" eta={data['eta_seconds']}s" if data.get("eta_seconds") else ""
        print(f"  {label}: {status}{extra}")
        if status in done:
            return data
        if status in failed:
            sys.exit(f"{label} {status}: {json.dumps(data)[:500]}\nRe-run with --retry to resubmit.")
        time.sleep(POLL_SECONDS)


def _write_env(key: str, value: str) -> None:
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --- commands ---------------------------------------------------------------------


def cmd_base_models(_args) -> None:
    data = _request("GET", "/api/v3/models/base")
    print(json.dumps(data, indent=2)[:6000])


def _task_of(sample: dict) -> str:
    q = sample["question"]
    return q.split("\n", 1)[0] if q.startswith("TASK: ") else "POLICY_QA"


def _stratified(samples: list[dict], n: int) -> list[dict]:
    """Keeps every task represented in proportion (at least a few of each)."""
    by_task: dict[str, list[dict]] = {}
    for s in samples:
        by_task.setdefault(_task_of(s), []).append(s)
    out = []
    for items in by_task.values():
        out += items[: max(4, round(n * len(items) / len(samples)))]
    return out[:n] if len(out) > n else out


def _compact_files(n_train: int) -> tuple[Path, Path]:
    train = [json.loads(line) for line in TRAIN_PATH.open(encoding="utf-8")]
    bench = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    small_train = TRAIN_PATH.with_name(f"triprescue_train_{n_train}.jsonl")
    small_bench = BENCHMARK_PATH.with_name(f"triprescue_benchmark_{n_train}.json")
    with small_train.open("w", encoding="utf-8") as f:
        for s in _stratified(train, n_train):
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    small_bench.write_text(json.dumps(_stratified(bench, max(20, n_train // 6)), indent=2, ensure_ascii=False), encoding="utf-8")
    return small_train, small_bench


def cmd_run(args) -> None:
    global TRAIN_PATH, BENCHMARK_PATH
    if not TRAIN_PATH.exists() or not BENCHMARK_PATH.exists():
        sys.exit("Dataset missing - run `python -m nugen.build_dataset` first")
    st = pipeline_state.load()

    # --compact N: a smaller stratified subset, for when the training service chokes on the full file
    if args.compact:
        TRAIN_PATH, BENCHMARK_PATH = _compact_files(args.compact)
        if st.get("dataset_file") != TRAIN_PATH.name:
            for key in ("document_id", "benchmark_id", "alignment_id", "model_id"):
                if key in st:
                    st.setdefault("previous", []).append({key: st.pop(key)})
            st["dataset_file"] = TRAIN_PATH.name
            pipeline_state.save(st)

    # 1. upload the domain dataset
    if not st.get("document_id"):
        print("Uploading TripRescue dataset...")
        with TRAIN_PATH.open("rb") as f:
            data = _request(
                "POST", "/api/v3/documents/create",
                files={"files": (TRAIN_PATH.name, f, "application/json")},
                data={"categories": "text/json"},
            )
        st["document_id"] = data["document_ids"][0]
        st["dataset_samples"] = sum(1 for _ in TRAIN_PATH.open(encoding="utf-8"))
        pipeline_state.save(st)
    print(f"Dataset document: {st['document_id']}")
    _wait("document", f"/api/v3/documents/{st['document_id']}/status", {"READY"})

    # 2. upload our curated, held-out benchmark (never part of the training file)
    if not st.get("benchmark_id"):
        print("Uploading held-out benchmark...")
        with BENCHMARK_PATH.open("rb") as f:
            data = _request(
                "POST", "/api/v3/benchmarks/upload",
                files={"file": (BENCHMARK_PATH.name, f, "application/json")},
                data={
                    "name": "TripRescue held-out benchmark",
                    "document_id": [st["document_id"]],
                    "description": "Held-out disruption impact, recovery-plan and traveler-rights questions",
                },
            )
        st["benchmark_id"] = data["benchmark_id"]
        st["benchmark_questions"] = len(json.loads(BENCHMARK_PATH.read_text(encoding="utf-8")))
        pipeline_state.save(st)
    print(f"Benchmark: {st['benchmark_id']}")
    _wait("benchmark", f"/api/v3/benchmarks/{st['benchmark_id']}/status", {"READY"})

    # 3. align the base model (--retry discards a failed alignment but keeps the uploads)
    if args.retry and st.get("alignment_id"):
        st.setdefault("failed_alignments", []).append(st.pop("alignment_id"))
        st.pop("model_id", None)
        pipeline_state.save(st)
    if not st.get("alignment_id"):
        if not args.base_model:
            sys.exit("Pass --base-model (see `python -m nugen.align base-models`)")
        print(f"Creating alignment on base model {args.base_model}...")
        data = _request(
            "POST", "/api/v3/alignment-projects/create",
            json={
                "alignment_name": ALIGNMENT_NAME,
                "base_model_id": args.base_model,
                "document_ids": [st["document_id"]],
                "benchmark_id": st["benchmark_id"],
                "description": (
                    "Aligns a base model into a travel disruption recovery advisor for India: explains "
                    "itinerary impact from a dependency graph, recommends recovery plans against traveler "
                    "preferences, and states DGCA / railway / booking-policy refund and compensation rights."
                ),
            },
        )
        st["alignment_id"] = data["alignment_id"]
        st["base_model_id"] = args.base_model
        pipeline_state.save(st)
    print(f"Alignment: {st['alignment_id']} (base {st.get('base_model_id')})")
    _wait("alignment", f"/api/v3/alignment-projects/{st['alignment_id']}/status", {"READY"})

    # 4. find the aligned model it produced
    if not st.get("model_id"):
        models = _request("GET", "/api/v3/models/aligned").get("domain_aligned_models", [])
        match = next((m for m in models if m.get("alignment_id") == st["alignment_id"]), None)
        if not match:
            sys.exit("Alignment is READY but no aligned model is listed for it yet - re-run in a minute")
        st["model_id"] = match["model_id"]
        pipeline_state.save(st)
    print(f"Aligned model: {st['model_id']}")

    # 5. deploy it
    status = _request("GET", f"/api/v3/models/{st['model_id']}/deployment/status").get("status")
    if status != "DEPLOYED":
        print("Deploying aligned model...")
        _request("POST", f"/api/v3/models/{st['model_id']}/deployment")
        _wait("deployment", f"/api/v3/models/{st['model_id']}/deployment/status", {"DEPLOYED"})

    # 6. record its evaluation against the base model on our benchmark
    model = _request("GET", f"/api/v3/models/{st['model_id']}")
    st["deployment_status"] = "DEPLOYED"
    st["model_name"] = model.get("model_name")
    st["base_model_name"] = model.get("base_model_name")
    st["evaluation"] = (model.get("evaluation_data") or {}).get("comparison")
    pipeline_state.save(st)

    _write_env("NUGEN_MODEL_ID", st["model_id"])
    print(f"\nDone. NUGEN_MODEL_ID={st['model_id']} written to backend/.env - restart the backend to use it.")


def cmd_status(_args) -> None:
    st = pipeline_state.load()
    print(json.dumps(st, indent=2) if st else "No pipeline run yet.")
    if st.get("alignment_id"):
        print(json.dumps(_request("GET", f"/api/v3/alignment-projects/{st['alignment_id']}/status"), indent=2))


def cmd_ask(args) -> None:
    from app.advisor_prompts import SYSTEM_PROMPT

    model_id = os.environ.get("NUGEN_MODEL_ID") or pipeline_state.load().get("model_id")
    if not model_id:
        sys.exit("No aligned model yet - run the pipeline first")
    data = _request(
        "POST", "/api/v3/inference/chat/completions",
        json={
            "model": model_id,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": args.prompt}],
            "max_tokens": 400,
            "temperature": 0.2,
            "stream": False,
        },
    )
    print(json.dumps(data, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("base-models").set_defaults(fn=cmd_base_models)
    run = sub.add_parser("run")
    run.add_argument("--base-model")
    run.add_argument("--retry", action="store_true", help="start a new alignment, reusing the uploaded dataset/benchmark")
    run.add_argument("--compact", type=int, metavar="N", help="upload a stratified N-sample subset instead of the full dataset")
    run.set_defaults(fn=cmd_run)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    ask = sub.add_parser("ask")
    ask.add_argument("prompt")
    ask.set_defaults(fn=cmd_ask)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
