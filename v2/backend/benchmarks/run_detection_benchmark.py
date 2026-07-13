"""Benchmark reproductible du retrieval VersePro, sans appel cloud."""

import asyncio
import json
import statistics
import time
import unicodedata
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.semantic_search import LocalSemanticService
from app.services.verse_parser import VerseParserService


CASES_PATH = Path(__file__).with_name("sermon_cases.json")


def normalize(reference):
    plain = "".join(
        c for c in unicodedata.normalize("NFD", str(reference or "").lower())
        if unicodedata.category(c) != "Mn"
    )
    return "".join(c for c in plain if c.isalnum())


async def main():
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    parser = VerseParserService()
    semantic = LocalSemanticService(parser.bible_loader)
    semantic.initialize(allow_download=False)
    latencies = []
    correct = 0

    for case in cases:
        started = time.perf_counter()
        result = await parser.parse(case["text"])
        if not result and semantic.initialized:
            candidates = semantic.search(case["text"], top_k=1)
            result = candidates[0] if candidates else None
        latencies.append((time.perf_counter() - started) * 1000)
        predicted = result.get("reference") if result else None
        ok = normalize(predicted) == normalize(case["expected"])
        correct += int(ok)
        print(f"{'OK' if ok else 'MISS':4} {case['kind']:10} {predicted or '-':12} {case['text']}")

    ordered = sorted(latencies)
    p95 = ordered[min(len(ordered) - 1, round(len(ordered) * 0.95) - 1)]
    print("\nResultats locaux")
    print(f"Exactitude : {correct}/{len(cases)} ({correct / len(cases):.1%})")
    print(f"Latence p50 : {statistics.median(latencies):.2f} ms")
    print(f"Latence p95 : {p95:.2f} ms")
    print(f"ONNX actif : {'oui' if semantic.initialized else 'non (fallback lexical uniquement)'}")


if __name__ == "__main__":
    asyncio.run(main())
