"""Benchmark local de la cascade de production VersePro, sans appel cloud."""

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main as runtime
from app.core.config import settings
from app.services.semantic_search import LocalSemanticService
from app.services.verse_parser import VerseParserService


DEFAULT_CASES = Path(__file__).with_name("sermon_cases.json")


class DisabledAI:
    enabled = False


async def canonical(parser: VerseParserService, reference: str | None):
    if not reference:
        return None
    parsed = await parser.parse(reference, skip_text_search=True)
    if not parsed:
        return None
    return (
        parsed.get("book_abbr"),
        parsed.get("chapter"),
        parsed.get("verse_start"),
        parsed.get("verse_end"),
    )


def percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * ratio)))
    return ordered[index]


async def run(cases_path: Path, require_onnx: bool = False) -> dict:
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    parser = VerseParserService()
    semantic = LocalSemanticService(parser.bible_loader)
    semantic.initialize(allow_download=False)
    if require_onnx and not semantic.initialized:
        raise RuntimeError("Le modèle ONNX demandé n'est pas préparé")

    runtime.verse_parser = parser
    runtime.semantic_service = semantic
    runtime.ai_service = DisabledAI()
    settings.AI_AGENT_ENABLED = False

    latencies: list[float] = []
    rows = []
    tp = tn = fp = fn = exact = negative_fp = 0
    for case in cases:
        expected_key = await canonical(parser, case.get("expected"))
        started = time.perf_counter()
        result = await runtime.run_detection_cascade(case["text"], final_state=True)
        latency = (time.perf_counter() - started) * 1000
        latencies.append(latency)
        predicted = result.get("reference") if result else None
        predicted_key = await canonical(parser, predicted)
        ok = predicted_key == expected_key
        exact += int(ok)
        if expected_key and predicted_key:
            if ok:
                tp += 1
            else:
                fp += 1
                fn += 1
        elif expected_key:
            fn += 1
        elif predicted_key:
            fp += 1
            negative_fp += 1
        else:
            tn += 1
        rows.append({
            "ok": ok,
            "kind": case.get("kind", "unknown"),
            "expected": case.get("expected"),
            "predicted": predicted,
            "latency_ms": round(latency, 3),
            "text": case["text"],
        })

    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    negatives = negative_fp + tn
    metrics = {
        "cases": len(cases),
        "exact_accuracy": exact / len(cases),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_positive_rate": negative_fp / negatives if negatives else 0.0,
        "negative_false_positives": negative_fp,
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "latency_ms": {
            "p50": statistics.median(latencies),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
            "max": max(latencies),
        },
        "onnx_active": semantic.initialized,
    }
    return {"metrics": metrics, "rows": rows}


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--require-onnx", action="store_true")
    parser.add_argument("--fail-below-f1", type=float, default=0.0)
    args = parser.parse_args()
    report = await run(args.cases, args.require_onnx)
    if args.as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for row in report["rows"]:
            print(
                f"{'OK' if row['ok'] else 'MISS':4} {row['kind']:<11} "
                f"{str(row['predicted'] or '-'):18} {row['latency_ms']:8.2f} ms  {row['text']}"
            )
        m = report["metrics"]
        print("\nRésultats cascade de production")
        print(f"Exactitude : {m['exact_accuracy']:.1%} ({m['cases']} cas)")
        print(f"Précision / rappel / F1 : {m['precision']:.1%} / {m['recall']:.1%} / {m['f1']:.1%}")
        print(f"Taux de faux positifs : {m['false_positive_rate']:.1%}")
        print(
            "Latence p50 / p95 / p99 : "
            f"{m['latency_ms']['p50']:.2f} / {m['latency_ms']['p95']:.2f} / {m['latency_ms']['p99']:.2f} ms"
        )
        print(f"ONNX actif : {'oui' if m['onnx_active'] else 'non'}")
    return 1 if report["metrics"]["f1"] < args.fail_below_f1 else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
