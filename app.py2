from __future__ import annotations

from collections import Counter
from pathlib import Path
import json

import networkx as nx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "processed"
NODE_FILE = DATA / "nodes.csv"
EDGE_FILE = DATA / "edges.csv"
ISSUE_FILE = DATA / "issues.csv"
SUMMARY_FILE = DATA / "summary.json"

COLORS = {1: "#172554", 2: "#2563eb", 3: "#06b6d4", 4: "#f59e0b", 5: "#f97316", 6: "#dc2626", 7: "#9333ea"}
REL_COLORS = {"层级关系": "#94a3b8", "先修关系": "#2563eb", "关联关系": "#10b981"}


@st.cache_data(show_spinner=False)
def load_data():
    for path in (NODE_FILE, EDGE_FILE, ISSUE_FILE, SUMMARY_FILE):
        if not path.exists():
            raise FileNotFoundError(f"缺少数据文件：{path.relative_to(ROOT)}。请先运行 preprocessing/clean_data.py。")
    nodes = pd.read_csv(NODE_FILE, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    edges = pd.read_csv(EDGE_FILE, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    issues = pd.read_csv(ISSUE_FILE, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    with SUMMARY_FILE.open(encoding="utf-8") as f:
        summary = json.load(f)
    nodes["level_num"] = pd.to_numeric(nodes["level"], errors="coerce").fillna(0).astype(int)
    return nodes, edges, issues, summary


def get_descendants(nodes: pd.DataFrame, root_id: str) -> set[str]:
    by_parent = nodes.groupby("parent_id")["id"].apply(list).to_dict()
    result = {root_id}
    stack = [root_id]
    while stack:
        parent = stack.pop()
        for child in by_parent.get(parent, []):
            if child not in result:
                result.add(child)
                stack.append(child)
    return result


def graph_figure(nodes: pd.DataFrame, edges: pd.DataFrame, selected_relations: list[str], focus_id: str | None = None):
    visible_nodes = nodes.copy()
    if focus_id:
        nearby = {focus_id}
        chosen_edges = edges[edges["relation_type"].isin(selected_relations)]
        for _ in range(2):
            linked = set(chosen_edges.loc[chosen_edges.source_id.isin(nearby), "target_id"])
            linked |= set(chosen_edges.loc[chosen_edges.target_id.isin(nearby), "source_id"])
            nearby |= linked
        visible_nodes = visible_nodes[visible_nodes.id.isin(nearby)]
    elif len(visible_nodes) > 80:
        # The overview defaults to a compact, readable module view.
        visible_nodes = visible_nodes[visible_nodes.level_num <= 2]

    allowed = set(visible_nodes.id)
    visible_edges = edges[
        edges.relation_type.isin(selected_relations)
        & edges.source_id.isin(allowed)
        & edges.target_id.isin(allowed)
    ].copy()
    graph = nx.Graph()
    graph.add_nodes_from(visible_nodes.id)
    graph.add_edges_from(zip(visible_edges.source_id, visible_edges.target_id))
    positions = nx.spring_layout(graph, seed=28, k=0.9, iterations=80)

    fig = go.Figure()
    for relation in selected_relations:
        part = visible_edges[visible_edges.relation_type == relation]
        xs, ys = [], []
        for row in part.itertuples(index=False):
            x0, y0 = positions[row.source_id]
            x1, y1 = positions[row.target_id]
            xs.extend([x0, x1, None])
            ys.extend([y0, y1, None])
        if xs:
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line={"width": 1.2, "color": REL_COLORS.get(relation, "#94a3b8")},
                                     hoverinfo="none", name=relation))
    for level, part in visible_nodes.groupby("level_num"):
        xs = [positions[node_id][0] for node_id in part.id]
        ys = [positions[node_id][1] for node_id in part.id]
        hover = []
        for row in part.itertuples(index=False):
            hover.append(f"{row.name}<br>ID：{row.id}<br>层级：{row.level}级<br>所属路径：{row.parent_id or '课程根节点'}")
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="markers+text", text=part.name, textposition="top center",
            textfont={"size": 10}, hovertext=hover, hoverinfo="text", name=f"{level}级知识点",
            marker={"size": 15 if level <= 2 else 11, "color": COLORS.get(int(level), "#64748b"),
                    "line": {"width": 1, "color": "white"}},
        ))
    fig.update_layout(height=660, margin={"l": 5, "r": 5, "t": 10, "b": 5},
                      legend={"orientation": "h", "y": -0.08}, plot_bgcolor="white",
                      xaxis={"visible": False}, yaxis={"visible": False}, hovermode="closest")
    return fig, len(visible_nodes), len(visible_edges)


def resolve_path_tokens(text: str, nodes: pd.DataFrame):
    by_id = nodes.set_index("id")["name"].to_dict()
    by_name = nodes.groupby("name")["id"].apply(list).to_dict()
    tokens = [t.strip() for line in text.splitlines() for t in line.replace("，", ",").replace("、", ",").split(",") if t.strip()]
    resolved, problems = [], []
    for token in tokens:
        if token in by_id:
            resolved.append(token)
        elif token in by_name and len(by_name[token]) == 1:
            resolved.append(by_name[token][0])
        elif token in by_name:
            problems.append(f"“{token}”对应多个知识点，请改用节点ID：{'、'.join(by_name[token])}。")
        else:
            problems.append(f"没有找到“{token}”。请使用知识点名称或节点ID。")
    return resolved, problems


st.set_page_config(page_title="信息科学基础 · 知识网络系统", page_icon="🧭", layout="wide")
st.title("信息科学基础 · 课程知识网络系统")
st.caption("第二步原型：浏览知识网络、查询知识点、查看结构特征、检查学习路径")

try:
    nodes, edges, issues, summary = load_data()
except Exception as exc:
    st.error(str(exc))
    st.stop()

with st.sidebar:
    st.header("功能导航")
    page = st.radio("选择功能", ["系统总览", "知识网络", "知识点查询", "学习路径检查", "数据问题清单"], label_visibility="collapsed")

st.warning("先修关系来自课程表字段，当前属于候选关系，尚未经过教师逐条审核。路径检查结果用于原型演示和关系核查。")

if page == "系统总览":
    st.subheader("课程数据概况")
    level_counts = summary.get("层级统计", {})
    relation_counts = summary.get("关系统计", {})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("知识点", int(summary.get("已提取知识点数", len(nodes))))
    c2.metric("知识层级", len(level_counts))
    c3.metric("关系记录", len(edges))
    c4.metric("待核查问题", int(summary.get("异常记录数", len(issues))))
    left, right = st.columns([1, 1])
    with left:
        st.markdown("#### 知识层级分布")
        level_df = pd.DataFrame([{"层级": f"{k}级", "知识点数量": int(v)} for k, v in level_counts.items()])
        if not level_df.empty:
            st.bar_chart(level_df.set_index("层级"))
    with right:
        st.markdown("#### 关系类型")
        rel_df = pd.DataFrame([{"关系": key, "数量": int(value)} for key, value in relation_counts.items()])
        if not rel_df.empty:
            st.bar_chart(rel_df.set_index("关系"))
    st.markdown("#### 当前建模说明")
    st.write("节点使用唯一ID；层级关系由课程目录生成；前置依赖保持“前置知识 → 后续知识”的方向；关联关系用于表达内容联系，不用于判断学习先后。")

elif page == "知识网络":
    st.subheader("课程知识网络浏览")
    all_relations = [r for r in ["层级关系", "先修关系", "关联关系"] if r in set(edges.relation_type)]
    selected = st.multiselect("显示关系类型", all_relations, default=all_relations)
    query = st.text_input("聚焦知识点（可选，支持名称或ID）")
    focus_id = None
    if query.strip():
        matches = nodes[(nodes.name.str.contains(query.strip(), regex=False, na=False)) | (nodes.id == query.strip())]
        if matches.empty:
            st.info("没有找到匹配的知识点。")
        else:
            pick = st.selectbox("选择聚焦节点", matches.apply(lambda r: f"{r.id}｜{r.name}", axis=1).tolist())
            focus_id = pick.split("｜", 1)[0]
    fig, node_count, edge_count = graph_figure(nodes, edges, selected, focus_id)
    st.caption(f"当前图中显示 {node_count} 个知识点、{edge_count} 条关系。默认总览展示课程根节点和模块；搜索节点后展示其两层邻域。可缩放和平移，悬停查看节点信息。")
    st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True, "displaylogo": False})

elif page == "知识点查询":
    st.subheader("知识点查询")
    query = st.text_input("输入知识点名称或ID", placeholder="例如：信息论介绍 / K002")
    if query.strip():
        found = nodes[(nodes.name.str.contains(query.strip(), regex=False, na=False)) | (nodes.id == query.strip())]
    else:
        found = nodes.head(0)
    if query.strip() and found.empty:
        st.info("没有找到匹配的知识点。")
    names = nodes.set_index("id")["name"].to_dict()
    for _, row in found.iterrows():
        with st.expander(f"{row['id']}｜{row['name']}（{row['level']}级）", expanded=len(found) == 1):
            parent = names.get(row["parent_id"], "课程根节点")
            st.write(f"**上级知识点：** {parent}")
            details = {"标签": row["标签"], "认知维度": row["认知维度"], "分类": row["分类"],
                       "教学目标": row["教学目标"], "知识点说明": row["知识点说明"]}
            st.dataframe(pd.DataFrame([{"属性": k, "内容": v or "（空）"} for k, v in details.items()]), hide_index=True, use_container_width=True)
            related = edges[(edges.source_id == row["id"]) | (edges.target_id == row["id"])]
            if related.empty:
                st.caption("当前没有记录到关联关系。")
            else:
                rel_rows = []
                for edge in related.itertuples(index=False):
                    other = edge.target_id if edge.source_id == row["id"] else edge.source_id
                    rel_rows.append({"方向": "→" if edge.source_id == row.id else "←", "关系": edge.relation_type,
                                     "关联知识点": f"{other}｜{names.get(other, other)}", "核验状态": edge.review_status})
                st.dataframe(pd.DataFrame(rel_rows), hide_index=True, use_container_width=True)

elif page == "学习路径检查":
    st.subheader("学习路径顺序检查")
    st.write("按计划学习顺序输入知识点名称或ID，每行一个或用逗号分隔。重名知识点请使用K编号。")
    path_text = st.text_area("学习顺序", placeholder="K004\nK008\nK012")
    include_one_sided = st.checkbox("同时纳入仅单侧记录的先修候选关系", value=True)
    if st.button("检查路径", type="primary"):
        path, problems = resolve_path_tokens(path_text, nodes)
        if problems:
            for problem in problems:
                st.error(problem)
        elif len(path) < 2:
            st.info("至少输入两个知识点，才能检查顺序。")
        elif len(path) != len(set(path)):
            st.error("路径中有重复知识点，请去重后再检查。")
        else:
            pos = {node_id: i for i, node_id in enumerate(path)}
            prereq = edges[edges.relation_type == "先修关系"].copy()
            if not include_one_sided:
                prereq = prereq[prereq.review_status.str.contains("双向一致", na=False)]
            in_path = prereq[prereq.source_id.isin(path) & prereq.target_id.isin(path)]
            violated = in_path[in_path.apply(lambda e: pos[e.source_id] >= pos[e.target_id], axis=1)]
            missing = prereq[prereq.target_id.isin(path) & ~prereq.source_id.isin(path)]
            names = nodes.set_index("id")["name"].to_dict()
            a, b, c = st.columns(3)
            a.metric("纳入检查的先修边", len(prereq))
            b.metric("路径内顺序冲突", len(violated))
            c.metric("未包含的候选前置点", len(missing))
            if violated.empty and missing.empty:
                st.success("按当前所选候选关系，未发现顺序冲突或缺失前置点。请注意这不是教师审核结论。")
            if not violated.empty:
                st.markdown("#### 顺序冲突")
                st.dataframe(pd.DataFrame([{"先修知识": f"{e.source_id}｜{names.get(e.source_id, e.source_id)}",
                                            "后续知识": f"{e.target_id}｜{names.get(e.target_id, e.target_id)}",
                                            "记录来源": e.source_columns, "核验状态": e.review_status}
                                           for e in violated.itertuples(index=False)]), hide_index=True, use_container_width=True)
            if not missing.empty:
                st.markdown("#### 路径未包含的候选前置点")
                st.dataframe(pd.DataFrame([{"路径中的知识点": f"{e.target_id}｜{names.get(e.target_id, e.target_id)}",
                                            "候选前置点": f"{e.source_id}｜{names.get(e.source_id, e.source_id)}",
                                            "记录来源": e.source_columns, "核验状态": e.review_status}
                                           for e in missing.itertuples(index=False)]), hide_index=True, use_container_width=True)

elif page == "数据问题清单":
    st.subheader("第一步数据核查问题")
    if issues.empty:
        st.success("当前异常清单为空。")
    else:
        issue_types = sorted(issues.issue_type.unique().tolist())
        selected_types = st.multiselect("筛选问题类型", issue_types, default=issue_types)
        visible = issues[issues.issue_type.isin(selected_types)]
        st.caption(f"显示 {len(visible)} / {len(issues)} 条异常记录")
        st.dataframe(visible, hide_index=True, use_container_width=True, height=560)
    st.download_button("下载当前异常清单", issues.to_csv(index=False).encode("utf-8-sig"), "issues.csv", "text/csv")

