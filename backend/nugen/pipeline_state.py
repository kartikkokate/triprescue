"""Persisted record of our Nugen alignment run (ids, statuses, evaluation), so the pipeline
can resume after interruption and the app can show the model's provenance."""
import json
from pathlib import Path

STATE_PATH = Path(__file__).parent / "state.json"
DATA_DIR = Path(__file__).parent / "data"


def load() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def dataset_stats() -> dict:
    """Sample counts per advisor task in the generated alignment dataset."""
    train, bench = DATA_DIR / "triprescue_train.jsonl", DATA_DIR / "triprescue_benchmark.json"
    if not train.exists():
        return {}
    by_task: dict[str, int] = {}
    total = 0
    for line in train.open(encoding="utf-8"):
        q = json.loads(line)["question"]
        task = q.split("\n", 1)[0].removeprefix("TASK: ") if q.startswith("TASK: ") else "POLICY_QA"
        by_task[task] = by_task.get(task, 0) + 1
        total += 1
    benchmark = len(json.loads(bench.read_text(encoding="utf-8"))) if bench.exists() else 0
    return {"train_samples": total, "benchmark_questions": benchmark, "by_task": by_task}
