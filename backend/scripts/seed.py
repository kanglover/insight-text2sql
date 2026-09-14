"""初始化数据库并灌入自制数据集。

用法：
    python -m scripts.seed              # 建表 + 灌数据（会先清空已有业务数据）
    python -m scripts.seed --keep       # 只补建表，不重复灌数据
    python -m scripts.seed --stats      # 灌完后打印各表行数与几个校验查询
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.core.log import setup_logging  # noqa: E402
from app.db.session import db  # noqa: E402


async def main(reset: bool, show_stats: bool) -> None:
    from app.data.seed import seed_database

    counts = await seed_database(db, reset=reset)
    print("=" * 72)
    print("数据初始化完成")
    print("=" * 72)
    for name, count in counts.items():
        print(f"  {name:<24} {count:>8} 行")

    if not show_stats:
        return

    checks = {
        "2026 年各经营单元收入 TOP5": """
            SELECT o.org_name, ROUND(SUM(r.revenue), 1) AS revenue
            FROM dw_fact_revenue r JOIN dw_dim_org o ON r.org_id = o.org_id
            WHERE r.year = 2026 GROUP BY o.org_name ORDER BY revenue DESC LIMIT 5
        """,
        "2026 年 北京代表处 完成率": """
            SELECT ROUND(rev.revenue, 1) AS revenue, ROUND(tgt.target, 1) AS target,
                   ROUND(rev.revenue / tgt.target * 100, 1) AS rate
            FROM (SELECT SUM(revenue) AS revenue FROM dw_fact_revenue r JOIN dw_dim_org o
                  ON r.org_id = o.org_id WHERE r.year = 2026 AND o.org_name = '北京代表处') rev,
                 (SELECT SUM(biz_target) AS target FROM dw_fact_target t JOIN dw_dim_org o
                  ON t.org_id = o.org_id WHERE t.year = 2026 AND o.org_name = '北京代表处') tgt
        """,
        "高风险项目数": "SELECT COUNT(*) FROM dw_fact_project_risk WHERE risk_level = '高'",
    }
    async with db.session() as session:
        for title, sql in checks.items():
            print("-" * 72)
            print(title)
            rows = (await session.execute(text(sql))).all()
            for row in rows:
                print("   ", tuple(row))
    await db.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="初始化问数数据集")
    parser.add_argument("--keep", action="store_true", help="只建表，不重复灌数据")
    parser.add_argument("--stats", action="store_true", help="打印校验查询结果")
    args = parser.parse_args()
    setup_logging()
    asyncio.run(main(reset=not args.keep, show_stats=args.stats))
