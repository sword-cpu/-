"""课程知识点标准化（第1阶段）

运行方式：在项目根目录执行 python preprocessing/clean_data.py
输出文件：data/processed/{nodes.csv, edges.csv, issues.csv, summary.json}
注意：源Excel的数值/文本“15”被视为占位值；修改源数据时需复核此约定。
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import networkx as nx
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "raw" / "信息科学基础-课程知识点.xlsx"
OUTPUT = ROOT / "data" / "processed"
LEVEL_COLS = [f"{s}级知识点" for s in "一二三四五六七"]
ATTR_COLS = ["标签", "认知维度", "分类", "教学目标", "知识点说明"]
REL_COLS = ["前置知识点", "后置知识点", "关联知识点"]
REQUIRED = LEVEL_COLS + REL_COLS + ATTR_COLS
PLACEHOLDERS = {"", "15", "nan", "none", "null", "n/a", "无"}


def clean(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).replace("\u3000", " ").strip()
    return "" if text.lower() in PLACEHOLDERS else text


def split_names(text: object) -> list[str]:
    """仅按明确的多值分隔符拆分，避免拆分合法知识点名称。"""
    value = clean(text)
    if not value:
        return []
    return [part for item in re.split(r"[;；,，、\n\r]+", value) if (part := item.strip())]


def main() -> None:
    if not INPUT.exists():
        raise FileNotFoundError(f"没有找到Excel文件：{INPUT}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    # Excel的第一行为大标题、第二行为实际表头。
    df = pd.read_excel(INPUT, sheet_name="课程知识点", header=1, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]
    missing_columns = [c for c in REQUIRED if c not in df.columns]
    if missing_columns:
        raise ValueError(f"Excel缺少必要字段：{missing_columns}")

    nodes: list[dict] = []
    issues: list[dict] = []
    last_seen: dict[int, str] = {}
    name_to_ids: defaultdict[str, list[str]] = defaultdict(list)

    def issue(kind: str, node_id: str, name: str, field: str, raw: str, detail: str) -> None:
        issues.append({
            "问题类型": kind,
            "节点ID": node_id,
            "知识点": name,
            "字段": field,
            "原始值": raw,
            "说明": detail,
        })

    for index, row in df.iterrows():
        nonempty = [(j + 1, clean(row[col])) for j, col in enumerate(LEVEL_COLS) if clean(row[col])]
        if not nonempty:
            issue("缺少知识点", "", "", "层级列", "", f"Excel第{index + 3}行没有知识点名称")
            continue
        if len(nonempty) != 1:
            issue("层级冲突", "", "", "层级列", str(nonempty), f"Excel第{index + 3}行存在多个知识点名称，先跳过")
            continue
        level, name = nonempty[0]
        node_id = f"K{len(nodes) + 1:03d}"
        parent_id = last_seen.get(level - 1, "") if level > 1 else ""
        if level > 1 and not parent_id:
            issue("父级缺失", node_id, name, LEVEL_COLS[level - 1], "", "无法根据课程目录顺序确定父级节点")
        node = {
            "id": node_id,
            "name": name,
            "level": level,
            "parent_id": parent_id,
            "excel_row": index + 3,
        }
        node.update({col: clean(row[col]) for col in ATTR_COLS})
        # 关系字段在建边时使用，不直接作为节点属性导出。
        node["_relations"] = {col: row[col] for col in REL_COLS}
        nodes.append(node)
        name_to_ids[name].append(node_id)
        last_seen[level] = node_id
        for higher in [k for k in last_seen if k > level]:
            del last_seen[higher]

    for name, ids in name_to_ids.items():
        if len(ids) > 1:
            issue("知识点同名", ",".join(ids), name, "知识点名称", name, "名称重复，但ID不同；涉及该名称的跨节点关系须人工确认")

    edges_by_key: dict[tuple[str, str, str], dict] = {}

    def add_edge(src: str, dst: str, relation: str, origin: str, status: str = "待核验") -> None:
        # 关联关系按无向关系处理，其余关系保留方向。
        if relation == "关联关系":
            src, dst = sorted((src, dst))
        key = (src, dst, relation)
        if key not in edges_by_key:
            edges_by_key[key] = {
                "source_id": src,
                "target_id": dst,
                "relation_type": relation,
                "source_columns": set(),
                "review_status": status,
            }
        edges_by_key[key]["source_columns"].add(origin)

    for node in nodes:
        src_id = node["id"]
        if node["parent_id"]:
            add_edge(node["parent_id"], src_id, "层级关系", "课程目录", "按目录生成")
        for col in REL_COLS:
            for target_name in split_names(node["_relations"][col]):
                target_ids = name_to_ids.get(target_name, [])
                if len(target_ids) == 0:
                    issue("关系指向未知知识点", src_id, node["name"], col, target_name, "未找到对应节点，未创建该关系")
                    continue
                if len(target_ids) > 1:
                    issue("关系目标存在歧义", src_id, node["name"], col, target_name, "目标存在多个同名知识点，未自动选取")
                    continue
                target_id = target_ids[0]
                if src_id == target_id:
                    issue("自关联", src_id, node["name"], col, target_name, "知识点指向自身，未创建关系")
                    continue
                if col == "前置知识点":
                    # A的前置是B -> 建立 B→A
                    add_edge(target_id, src_id, "先修关系", col)
                elif col == "后置知识点":
                    # A的后置是B -> 建立 A→B
                    add_edge(src_id, target_id, "先修关系", col)
                else:
                    add_edge(src_id, target_id, "关联关系", col)

    for edge in edges_by_key.values():
        if edge["relation_type"] == "先修关系":
            # 双字段互相印证，只表明录入一致；仍不等于教师审核通过。
            two_sides = {"前置知识点", "后置知识点"}.issubset(edge["source_columns"])
            edge["review_status"] = "字段双向一致(待教师核验)" if two_sides else "仅单侧记录(待教师核验)"
        edge["source_columns"] = ";".join(sorted(edge["source_columns"]))

    graph = nx.DiGraph()
    graph.add_nodes_from(node["id"] for node in nodes)
    graph.add_edges_from((edge["source_id"], edge["target_id"])
                         for edge in edges_by_key.values() if edge["relation_type"] == "先修关系")
    # 仅输出前20个环的样例，避免含环图无限扩张式枚举。
    sampled_cycles = []
    for cycle in nx.simple_cycles(graph):
        sampled_cycles.append(cycle)
        issue("先修关系成环", ",".join(cycle), "", "先修关系", "→".join(cycle + [cycle[0]]), "先修依赖形成有向环，须人工检查关系语义")
        if len(sampled_cycles) >= 20:
            break

    node_export = [{k: v for k, v in node.items() if k != "_relations"} for node in nodes]
    edge_export = list(edges_by_key.values())
    pd.DataFrame(node_export).to_csv(OUTPUT / "nodes.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(edge_export, columns=["source_id", "target_id", "relation_type", "source_columns", "review_status"]).to_csv(
        OUTPUT / "edges.csv", index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(issues, columns=["问题类型", "节点ID", "知识点", "字段", "原始值", "说明"]).to_csv(
        OUTPUT / "issues.csv", index=False, encoding="utf-8-sig"
    )
    from collections import Counter
    summary = {
        "原始记录数": len(df),
        "已提取知识点数": len(nodes),
        "唯一名称数": len(name_to_ids),
        "层级统计": dict(sorted(Counter(str(n["level"]) for n in nodes).items())),
        "关系统计": dict(sorted(Counter(e["relation_type"] for e in edge_export).items())),
        "异常记录数": len(issues),
        "异常类型统计": dict(sorted(Counter(i["问题类型"] for i in issues).items())),
        "先修关系是否无环": nx.is_directed_acyclic_graph(graph),
        "环示例数量(最多20)": len(sampled_cycles),
        "备注": "15视作空值；重复名称的目标关系不自动消歧；先修边不代表已经教师审核。",
    }
    (OUTPUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("===== 知识图谱数据预处理完成 =====")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("输出目录：", OUTPUT)


if __name__ == "__main__":
    main()
