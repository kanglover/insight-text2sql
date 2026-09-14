"""命令行问数：不依赖前端，直接观察整条流水线。

用法：
    python -m scripts.ask "2026年各经营单元的收入和完成率分别是多少"
    python -m scripts.ask "有哪些高风险项目" --provider rule
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.query_service import QueryService  # noqa: E402


async def main(question: str, provider: str | None) -> None:
    from app.core.log import setup_logging
    from app.db.session import db

    setup_logging()
    await db.create_all()

    service = QueryService(db)
    print("=" * 72)
    print(f"问题：{question}")
    print("=" * 72)

    async for event in service.run(question, provider=provider):
        kind = event.get("type")
        if kind == "progress":
            print(f"[进度] {event['step']:<24} {event['status']}")
        elif kind == "state":
            state = event["state"]
            print("=" * 72)
            print("SQL：")
            print(state.get("sql", ""))
            print("-" * 72)
            print(f"命中表：{state.get('selected_tables')}")
            print(f"生成方式：{state.get('provider')}  Token：{state.get('token_usage')}")
            print(f"返回行数：{state.get('row_count')}")
            if state.get("chart"):
                print(f"图表：{state['chart'].get('type')}")
            print("-" * 72)
            print("结论：")
            print(state.get("answer"))
            if state.get("followups"):
                print("-" * 72)
                print("延伸问题：" + " / ".join(state["followups"]))
        elif kind == "error":
            print(f"[错误] {event.get('message')}")

    await db.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="命令行问数")
    parser.add_argument("question", help="自然语言问题")
    parser.add_argument("--provider", default=None, choices=["auto", "openai", "rule"])
    args = parser.parse_args()
    asyncio.run(main(args.question, args.provider))
