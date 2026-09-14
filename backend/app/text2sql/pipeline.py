"""极简流水线编排器。

设计取舍：本项目只有十几个节点、一处条件分支（校验失败 → 修正），
为此引入完整的图框架会带来不必要的运行时复杂度与测试成本。
这里用不到 100 行实现同样语义：

- ``Node``：一个纯 async 函数，返回要合并进 state 的字典差分；
- ``Edge``：无条件跳转；
- ``ConditionalEdge``：根据 state 决定下一个节点；
- 执行时每个节点前/后自动发 ``progress`` 事件，节点内部可发任意领域事件。

未来若节点数与分支显著增长（例如加入多轮澄清、并行子图），
把 ``Pipeline.run`` 换成 LangGraph 即可，节点函数与状态定义无需改动。
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

Emit = Callable[[dict[str, Any]], None]
NodeFn = Callable[[dict[str, Any], Any, Emit], Awaitable[dict[str, Any] | None]]


@dataclass(frozen=True)
class Node:
    name: str
    label: str
    fn: NodeFn


@dataclass(frozen=True)
class Edge:
    source: str
    target: str


@dataclass(frozen=True)
class ConditionalEdge:
    source: str
    # 返回 mapping 的 key
    router: Callable[[dict[str, Any]], str]
    mapping: dict[str, str]


@dataclass
class Pipeline:
    name: str
    entry: str
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: dict[str, str] = field(default_factory=dict)
    conditionals: dict[str, tuple[Callable[[dict[str, Any]], str], dict[str, str]]] = field(
        default_factory=dict
    )

    def add(self, node: Node, next_node: str | None = None) -> "Pipeline":
        self.nodes[node.name] = node
        if next_node:
            self.edges[node.name] = next_node
        return self

    def branch(
        self,
        source: str,
        router: Callable[[dict[str, Any]], str],
        mapping: dict[str, str],
    ) -> "Pipeline":
        self.conditionals[source] = (router, mapping)
        return self

    def route(self, name: str, state: dict[str, Any]) -> str:
        if name in self.conditionals:
            router, mapping = self.conditionals[name]
            key = router(state)
            if key not in mapping:
                raise KeyError(f"条件分支 {name} 返回了未定义的 key: {key}")
            return mapping[key]
        return self.edges.get(name, "END")

    async def run(
        self, state: dict[str, Any], context: Any
    ) -> AsyncIterator[dict[str, Any]]:
        """执行流水线并按顺序 yield 出所有事件。"""
        events: list[dict[str, Any]] = []

        def emit(event: dict[str, Any]) -> None:
            events.append(event)

        node_name = self.entry
        visited: list[str] = []
        # 防御性上限：即使图配置写错也不会死循环
        for _ in range(64):
            if node_name == "END":
                break
            node = self.nodes.get(node_name)
            if node is None:
                raise KeyError(f"未找到节点 {node_name}")

            emit({"type": "progress", "step": node.label, "node": node.name, "status": "running"})
            while events:
                yield events.pop(0)

            try:
                updates = await node.fn(state, context, emit)
            except Exception as exc:
                emit(
                    {
                        "type": "progress",
                        "step": node.label,
                        "node": node.name,
                        "status": "error",
                    }
                )
                while events:
                    yield events.pop(0)
                raise exc

            if updates:
                state.update(updates)

            emit({"type": "progress", "step": node.label, "node": node.name, "status": "success"})
            while events:
                yield events.pop(0)

            visited.append(node_name)
            node_name = self.route(node_name, state)

        while events:
            yield events.pop(0)
        yield {"type": "trace", "nodes": visited}

    def mermaid(self) -> str:
        """把流水线画成 mermaid，方便写在文档里对照。"""
        lines = ["graph TD", f"  START([START]) --> {self.entry}"]
        for source, target in self.edges.items():
            lines.append(f"  {source} --> {target}")
        for source, (_, mapping) in self.conditionals.items():
            for label, target in mapping.items():
                lines.append(f"  {source} -->|{label}| {target}")
        lines.append("  END([END])")
        return "\n".join(lines)
