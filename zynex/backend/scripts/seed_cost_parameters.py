"""
Seed default cost parameters (hourly rates + overhead percentages).
Usage (from backend/): python -m scripts.seed_cost_parameters
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import settings
from app.models.knowledge_base import CostParameter

engine = create_async_engine(settings.DATABASE_URL)
Session = async_sessionmaker(engine)

DEFAULTS = [
    # role,        level,    rate,  qa%,  devops%, cont%, profit%
    ("developer",  "junior",  25.0, 15.0, 10.0,   10.0,  20.0),
    ("developer",  "mid",     40.0, 15.0, 10.0,   10.0,  20.0),
    ("developer",  "senior",  60.0, 15.0, 10.0,   10.0,  20.0),
    ("qa",         "junior",  20.0, 0.0,  10.0,   10.0,  20.0),
    ("qa",         "mid",     30.0, 0.0,  10.0,   10.0,  20.0),
    ("qa",         "senior",  45.0, 0.0,  10.0,   10.0,  20.0),
    ("devops",     "mid",     45.0, 15.0, 0.0,    10.0,  20.0),
    ("devops",     "senior",  65.0, 15.0, 0.0,    10.0,  20.0),
    ("designer",   "mid",     35.0, 15.0, 10.0,   10.0,  20.0),
    ("manager",    "senior",  70.0, 15.0, 10.0,   10.0,  20.0),
]


async def seed():
    async with Session() as db:
        have = {(r.role, r.level) for r in (await db.execute(select(CostParameter))).scalars()}
        added = 0
        for role, level, rate, qa, devops, cont, profit in DEFAULTS:
            if (role, level) in have:      # safe to run again: never duplicates or overwrites edited rates
                continue
            added += 1
            obj = CostParameter(
                role=role,
                level=level,
                hourly_rate=rate,
                qa_percentage=qa,
                devops_percentage=devops,
                contingency_percentage=cont,
                profit_margin_percentage=profit,
            )
            db.add(obj)
        await db.commit()
        print(f"Added {added} cost parameter records ({len(DEFAULTS) - added} already existed).")


if __name__ == "__main__":
    asyncio.run(seed())
