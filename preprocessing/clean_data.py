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
RULES = Path(__file__).with_name("resolution_rules.json")
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
    resolution_log: list[dict] = []
    rules = json.loads(RULES.read_text(encoding="utf-8")) if RULES.exists() else []
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
            issue("知识点同名", ",".join(ids), name, "知识点名称", name,
                  "名称重复，按课程层级保留不同节点ID；检查关系引用时使用节点路径区分")

    edges_by_key: dict[tuple[str, str, str], dict] = {}

    def add_edge(src: str, dst: str, relation: str, origin: str, status: str = "单字段记录") -> None:
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
                "field_consistency": status,
            }
        edges_by_key[key]["source_columns"].add(origin)

    for node in nodes:
        src_id = node["id"]
        if node["parent_id"]:
            add_edge(node["parent_id"], src_id, "层级关系", "课程目录", "按目录生成")
        for col in REL_COLS:
            for target_name in split_names(node["_relations"][col]):
                target_ids = name_to_ids.get(target_name, [])
                method = "名称唯一匹配"
                reason = ""
                if len(target_ids) != 1:
                    matches = [rule for rule in rules if rule["source_name"] == node["name"]
                               and rule["source_level"] == node["level"] and rule["field"] == col
                               and rule["raw_target"] == target_name and rule.get("enabled", True)]
                    if len(matches) == 1:
                        rule = matches[0]
                        resolved = [n["id"] for n in nodes if n["name"] == rule["target_name"]
                                    and n["level"] == rule["target_level"]]
                        if len(resolved) == 1:
                            target_ids = resolved
                            method = rule["method"]
                            reason = rule["reason"]
                resolution_log.append({"原表行号": node["excel_row"], "来源ID": src_id,
                                       "来源知识点": node["name"], "字段": col, "原始目标名称": target_name,
                                       "目标ID": target_ids[0] if len(target_ids) == 1 else "",
                                       "目标名称": next((n["name"] for n in nodes if len(target_ids) == 1 and n["id"] == target_ids[0]), ""),
                                       "目标层级": next((n["level"] for n in nodes if len(target_ids) == 1 and n["id"] == target_ids[0]), ""),
                                       "处理方式": method if len(target_ids) == 1 else "未唯一解析",
                                       "依据": reason})
                if len(target_ids) == 0:
                    issue("关系目标未进入层级节点", src_id, node["name"], col, target_name,
                          "保留表格原始引用；目标不在层级节点表中，因此未自动连入节点网络")
                    continue
                if len(target_ids) > 1:
                    issue("关系目标对应多个节点", src_id, node["name"], col, target_name,
                          "保留表格原始引用；目标名称对应多个节点ID，因此未自动选取")
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
            two_sides = {"前置知识点", "后置知识点"}.issubset(edge["source_columns"])
            if two_sides:
                edge["field_consistency"] = "前置与后置字段均有记录"
            elif "前置知识点" in edge["source_columns"]:
                edge["field_consistency"] = "仅前置知识字段有记录"
            else:
                edge["field_consistency"] = "仅后置知识字段有记录"
        edge["source_columns"] = ";".join(sorted(edge["source_columns"]))

    graph = nx.DiGraph()
    graph.add_nodes_from(node["id"] for node in nodes)
    graph.add_edges_from((edge["source_id"], edge["target_id"])
                         for edge in edges_by_key.values() if edge["relation_type"] == "先修关系")
    # 按强连通分量报告循环结构，避免把互相重叠的简单环重复列为多个问题。
    cyclic_components = [component for component in nx.strongly_connected_components(graph)
                         if len(component) > 1 or any(graph.has_edge(node, node) for node in component)]
    cyclic_nodes: set[str] = set()
    for component in cyclic_components:
        cyclic_nodes.update(component)
        internal_edges = sorted((src, dst) for src, dst in graph.subgraph(component).edges())
        edge_text = ";".join(f"{src}→{dst}" for src, dst in internal_edges)
        issue("先修网络循环结构", ",".join(sorted(component)), "", "先修关系", edge_text,
              f"此循环结构包含{len(component)}个节点和{len(internal_edges)}条内部关系；按表格保留原关系，不自动删除或反转")

    node_export = [{k: v for k, v in node.items() if k != "_relations"} for node in nodes]
    edge_export = list(edges_by_key.values())
    pd.DataFrame(node_export).to_csv(OUTPUT / "nodes.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(edge_export, columns=["source_id", "target_id", "relation_type", "source_columns", "field_consistency"]).to_csv(
        OUTPUT / "edges.csv", index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(issues, columns=["问题类型", "节点ID", "知识点", "字段", "原始值", "说明"]).to_csv(
        OUTPUT / "issues.csv", index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(resolution_log).to_csv(OUTPUT / "relation_resolution.csv", index=False, encoding="utf-8-sig")
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
        "先修循环结构组数": len(cyclic_components),
        "先修循环涉及节点数": len(cyclic_nodes),
        "规则解析引用数": sum(r["处理方式"] not in {"名称唯一匹配", "未唯一解析"} for r in resolution_log),
        "未唯一解析引用数": sum(r["处理方式"] == "未唯一解析" for r in resolution_log),
        "备注": "15视作占位值；名称映射与消歧按resolution_rules.json显式建模规则执行，可查relation_resolution.csv；规则不等于教师新增确认；循环保留。",
    }
    (OUTPUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("===== 知识图谱数据预处理完成 =====")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("输出目录：", OUTPUT)


if __name__ == "__main__":
    main()
