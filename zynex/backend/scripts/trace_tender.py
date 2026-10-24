"""TEMPORARY: write the step-by-step trace of a tender (text per page, chunks, what is read) WITHOUT the AI steps.

    python -m scripts.trace_tender /path/to/tender.pdf

For the AI steps too, turn on Settings > Tender analysis > "Save a step-by-step trace" and upload the tender normally.
Output: <uploads>/trace/run_manual_<file>/  (open 00_SUMMARY.txt first).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.ai.tender.criteria_extractor import CriteriaExtractor  # noqa: E402
from app.ai.tender.run_options import RunOptions  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.services.eligibility import trace  # noqa: E402
from app.services.eligibility.pipeline import EligibilityPipeline  # noqa: E402


async def main(path: str) -> None:
    settings.TRACE_RUNS = True
    t = trace.start("manual", os.path.basename(path))
    data = open(path, "rb").read()
    pipe = EligibilityPipeline(extractor=None)
    chunks = await pipe.parse("manual", os.path.basename(path), data, None)
    CriteriaExtractor(RunOptions.build(None, None, None, None)).plan_only(chunks)
    print("trace written to:", trace.finish(os.path.basename(path)) or t.path)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
