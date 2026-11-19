from __future__ import annotations

from pathlib import Path
import json

import networkx as nx
import pandas as pd
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


def tree_data(nodes: pd.DataFrame, root_id: str) -> dict:
    by_parent = nodes.groupby("parent_id")["id"].apply(list).to_dict()
    by_id = nodes.set_index("id").to_dict("index")

    def build(node_id: str) -> dict:
        row = by_id[node_id]
        children = [build(child_id) for child_id in by_parent.get(node_id, [])]
        return {"name": f"{row['name']}  [{node_id}]", "value": node_id,
                "itemStyle": {"color": COLORS.get(int(row["level_num"]), "#64748b")},
                "children": children}

    return build(root_id)


def tree_spec(root: dict) -> dict:
    return {
        "tooltip": {"trigger": "item", "triggerOn": "mousemove"},
        "series": [{"type": "tree", "data": [root], "top": "4%", "left": "9%",
                    "bottom": "4%", "right": "22%", "orient": "TB", "symbol": "emptyCircle",
                    "initialTreeDepth": 2, "expandAndCollapse": True, "roam": True,
                    "animationDuration": 450, "animationDurationUpdate": 700,
                    "label": {"position": "top", "verticalAlign": "middle", "align": "center",
                              "fontSize": 11, "color": "#172554"},
                    "leaves": {"label": {"position": "right", "align": "left", "fontSize": 10}},
                    "emphasis": {"focus": "descendant"},
                    "lineStyle": {"color": "#94a3b8", "width": 1.3, "curveness": 0.35}}],
    }


def network_spec(nodes: pd.DataFrame, edges: pd.DataFrame, relation: str, focus_id: str | None = None) -> tuple[dict, int, int]:
    visible = nodes.copy()
    if focus_id:
        subset = edges[edges.relation_type == relation]
        neighborhood = {focus_id}
        for _ in range(2):
            neighborhood |= set(subset.loc[subset.source_id.isin(neighborhood), "target_id"])
            neighborhood |= set(subset.loc[subset.target_id.isin(neighborhood), "source_id"])
        visible = visible[visible.id.isin(neighborhood)]
    allowed = set(visible.id)
    visible_edges = edges[(edges.relation_type == relation)
                          & edges.source_id.isin(allowed) & edges.target_id.isin(allowed)]
    counts = CounterLike(visible_edges.source_id.tolist() + visible_edges.target_id.tolist())
    data = [{"id": row.id, "name": row.name, "value": row.id,
             "symbolSize": min(34, 14 + counts.get(row.id, 0) * 2),
             "category": int(row.level_num) - 1,
             "itemStyle": {"color": COLORS.get(int(row.level_num), "#64748b")},
             "label": {"show": len(visible) <= 65, "fontSize": 10, "color": "#1e293b"}}
            for row in visible.itertuples(index=False)]
    directed = relation != "关联关系"
    links = []
    for row in visible_edges.itertuples(index=False):
        links.append({"source": row.source_id, "target": row.target_id,
                      "relation": relation,
                      "symbol": ["none", "arrow"] if directed else ["none", "none"],
                      "lineStyle": {"color": REL_COLORS.get(relation, "#94a3b8"),
                                    "width": 1.2, "opacity": 0.62, "curveness": 0.12}})
    spec = {
        "tooltip": {"trigger": "item", "formatter": "{b}"},
        "legend": [{"data": [f"{i}级" for i in range(1, 8)], "top": 8}],
        "series": [{"type": "graph", "layout": "force", "roam": True, "draggable": True,
                    "data": data, "links": links,
                    "categories": [{"name": f"{i}级"} for i in range(1, 8)],
                    "force": {"repulsion": 190, "gravity": 0.08, "edgeLength": 105,
                              "layoutAnimation": True},
                    "edgeSymbol": ["none", "arrow"] if directed else ["none", "none"],
                    "edgeSymbolSize": [4, 9], "label": {"position": "right"},
                    "emphasis": {"focus": "adjacency", "lineStyle": {"width": 2.5}},
                    "lineStyle": {"opacity": 0.65, "width": 1.2}}],
    }
    return spec, len(visible), len(visible_edges)


def CounterLike(items: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1
    return counts


def relation_graph(nodes: pd.DataFrame, edges: pd.DataFrame, relation: str):
    directed = relation != "关联关系"
    graph = nx.DiGraph() if directed else nx.Graph()
    graph.add_nodes_from(nodes.id)
    part = edges[edges.relation_type == relation]
    graph.add_edges_from(zip(part.source_id, part.target_id))
    return graph, part


def relation_analysis(nodes: pd.DataFrame, edges: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for relation in ["层级关系", "先修关系", "关联关系"]:
        graph, _ = relation_graph(nodes, edges, relation)
        if graph.is_directed():
            component_count = nx.number_weakly_connected_components(graph)
            avg_degree = sum(dict(graph.degree()).values()) / max(graph.number_of_nodes(), 1)
        else:
            component_count = nx.number_connected_components(graph)
            avg_degree = sum(dict(graph.degree()).values()) / max(graph.number_of_nodes(), 1)
        rows.append({"关系网络": relation, "节点数": graph.number_of_nodes(), "边数": graph.number_of_edges(),
                     "网络密度": round(nx.density(graph), 4), "连通分量数": component_count,
                     "孤立节点数": len(list(nx.isolates(graph))), "平均度": round(avg_degree, 3)})
    return pd.DataFrame(rows)


def centrality_table(graph: nx.Graph | nx.DiGraph, nodes: pd.DataFrame) -> pd.DataFrame:
    names = nodes.set_index("id")["name"].to_dict()
    if graph.is_directed():
        in_degree = dict(graph.in_degree())
        out_degree = dict(graph.out_degree())
        centrality = nx.degree_centrality(graph)
        undirected_for_between = graph.to_undirected()
    else:
        in_degree = dict(graph.degree())
        out_degree = {key: 0 for key in graph.nodes}
        centrality = nx.degree_centrality(graph)
        undirected_for_between = graph
    betweenness = nx.betweenness_centrality(undirected_for_between, normalized=True)
    records = [{"节点ID": node, "知识点": names.get(node, node), "入度": in_degree.get(node, 0),
                "出度": out_degree.get(node, 0), "度中心性": round(centrality.get(node, 0), 4),
                "中介中心性": round(betweenness.get(node, 0), 4)} for node in graph.nodes]
    return pd.DataFrame(records).sort_values(["度中心性", "中介中心性"], ascending=False, ignore_index=True)


st.set_page_config(page_title="信息科学基础 · 知识网络系统", page_icon="🧭", layout="wide")
st.title("信息科学基础 · 课程知识网络系统")
st.caption("第一部分：课程知识体系建模、知识网络构建与复杂网络结构分析")

try:
    nodes, edges, issues, summary = load_data()
except Exception as exc:
    st.error(str(exc))
    st.stop()

with st.sidebar:
    st.header("功能导航")
    page = st.radio("选择功能", ["系统总览", "课程知识体系", "知识关系网络", "复杂网络分析", "知识点查询", "数据一致性检查"], label_visibility="collapsed")

st.info("本系统以教师提供的《信息科学基础》课程知识点表为数据来源，构建课程知识层级网络、先修关系网络和知识关联网络，并开展复杂网络结构特征分析。")

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
            st.bar_chart(level_df.set_index("层级"), alt="课程知识点在各层级的数量分布")
    with right:
        st.markdown("#### 关系类型")
        rel_df = pd.DataFrame([{"关系": key, "数量": int(value)} for key, value in relation_counts.items()])
        if not rel_df.empty:
            st.bar_chart(rel_df.set_index("关系"), alt="层级、先修和关联关系的记录数量")
    st.markdown("#### 当前建模说明")
    st.write("节点使用唯一ID；层级关系按课程目录生成；先修关系依据表格中的前置和后续知识字段构建，方向为“前置知识 → 后续知识”；关联关系表达知识点之间的内容联系。")

elif page == "课程知识体系":
    st.subheader("课程知识体系层级图")
    roots = nodes[nodes.level_num == 1]
    module_rows = nodes[nodes.level_num == 2]
    root_options = {"全课程": roots.iloc[0].id} if not roots.empty else {}
    root_options.update({f"模块：{row.name}": row.id for row in module_rows.itertuples(index=False)})
    choice = st.selectbox("查看范围", list(root_options))
    root_id = root_options[choice]
    root = tree_data(nodes, root_id)
    descendant_count = len(get_descendants(nodes, root_id))
    st.caption(f"当前范围包括 {descendant_count} 个知识点。点击节点可逐层展开或收起；可缩放和平移查看树状结构。")
    st.echarts_chart(tree_spec(root), height=780, alt="课程知识点从课程根节点到各级知识点的层级树状图")

elif page == "知识关系网络":
    st.subheader("知识关系网络")
    relations = ["层级关系", "先修关系", "关联关系"]
    relation = st.segmented_control("选择关系网络", relations, default="先修关系", key="relation_view")
    if relation:
        st.caption({"层级关系": "有向显示父级知识点 → 子级知识点。",
                    "先修关系": "有向显示前置知识点 → 后续知识点。",
                    "关联关系": "无向显示表格中的知识点关联。"}[relation])
        query = st.text_input("聚焦知识点（可选）", placeholder="输入名称或节点ID")
        focus_id = None
        if query.strip():
            matches = nodes[(nodes.name.str.contains(query.strip(), regex=False, na=False)) | (nodes.id == query.strip())]
            if matches.empty:
                st.info("没有找到匹配的知识点。")
            else:
                labels = [f"{row.id}｜{row.name}" for row in matches.itertuples(index=False)]
                chosen = st.selectbox("选择节点", labels)
                focus_id = chosen.split("｜", 1)[0]
        spec, node_count, edge_count = network_spec(nodes, edges, relation, focus_id)
        st.caption(f"当前视图：{node_count} 个知识点，{edge_count} 条{relation}。未搜索时显示全课程网络；搜索后显示该节点的两层邻域。")
        st.echarts_chart(spec, height=720, alt=f"{relation}的交互式课程知识网络图")

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
            st.dataframe(pd.DataFrame([{"属性": k, "内容": v or "（空）"} for k, v in details.items()]), hide_index=True, alt="知识点教学属性和说明")
            related = edges[(edges.source_id == row["id"]) | (edges.target_id == row["id"])]
            if related.empty:
                st.caption("当前没有记录到关联关系。")
            else:
                rel_rows = []
                for edge in related.itertuples(index=False):
                    other = edge.target_id if edge.source_id == row["id"] else edge.source_id
                    rel_rows.append({"方向": "→" if edge.source_id == row["id"] else "←", "关系": edge.relation_type,
                                     "关系来源": edge.source_columns,
                                     "关联知识点": f"{other}｜{names.get(other, other)}"})
                st.dataframe(pd.DataFrame(rel_rows), hide_index=True, alt="该知识点的层级、先修和关联关系")

elif page == "复杂网络分析":
    st.subheader("复杂网络结构分析")
    st.markdown("#### 三类关系网络指标比较")
    comparison = relation_analysis(nodes, edges)
    st.dataframe(comparison, hide_index=True, alt="层级、先修、关联网络的结构指标比较")
    st.download_button("导出关系网络指标", comparison.to_csv(index=False).encode("utf-8-sig"),
                       "network_metrics.csv", "text/csv")
    relation = st.selectbox("深入分析关系网络", ["层级关系", "先修关系", "关联关系"], key="analysis_relation")
    graph, selected_edges = relation_graph(nodes, edges, relation)
    ranking = centrality_table(graph, nodes)
    top_count = min(20, len(ranking))
    left, right = st.columns([1, 1])
    with left:
        st.markdown("#### 节点度分布")
        degrees = pd.Series(dict(graph.degree()), name="节点度").value_counts().sort_index()
        degree_df = pd.DataFrame({"节点度": degrees.index.astype(str), "节点数量": degrees.values})
        st.bar_chart(degree_df.set_index("节点度"), alt=f"{relation}网络的节点度分布")
    with right:
        st.markdown("#### 中心性排名（前20）")
        st.dataframe(ranking.head(top_count), hide_index=True, alt=f"{relation}网络中心性排名")
        st.download_button("导出当前网络节点排名", ranking.to_csv(index=False).encode("utf-8-sig"),
                           f"{relation}_centrality.csv", "text/csv")
    st.markdown("#### 关键知识点局部结构")
    labels = [f"{row.id}｜{row.name}" for row in nodes.itertuples(index=False)]
    chosen = st.selectbox("选择知识点", labels, key="local_structure_node")
    focus_id = chosen.split("｜", 1)[0]
    local_spec, local_nodes, local_edges = network_spec(nodes, edges, relation, focus_id)
    st.caption(f"所选知识点的两层局部结构：{local_nodes} 个节点、{local_edges} 条{relation}。")
    st.echarts_chart(local_spec, height=600, alt=f"{chosen}在{relation}网络中的局部结构")

elif page == "数据一致性检查":
    st.subheader("数据一致性检查")
    st.caption("检查内容包括同名知识点、关系目标缺失或歧义、先修关系成环等技术一致性问题。该页面用于呈现表格数据的结构检查结果。")
    if issues.empty:
        st.success("当前异常清单为空。")
    else:
        issue_types = sorted(issues.issue_type.unique().tolist())
        selected_types = st.multiselect("筛选问题类型", issue_types, default=issue_types)
        visible = issues[issues.issue_type.isin(selected_types)]
        st.caption(f"显示 {len(visible)} / {len(issues)} 条异常记录")
        st.dataframe(visible, hide_index=True, alt="课程知识数据一致性检查问题清单", height=560)
    st.download_button("下载数据一致性检查清单", issues.to_csv(index=False).encode("utf-8-sig"), "issues.csv", "text/csv")

