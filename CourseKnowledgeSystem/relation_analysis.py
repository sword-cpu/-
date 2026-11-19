
# -*- coding: utf-8 -*-
"""课程知识网络三类关系对比分析"""

import networkx as nx
import pandas as pd
import streamlit as st


RELATIONS = ["层级关系", "先修关系", "关联关系"]


def build_relation_graphs(nodes, edges, relation):
    """分别构建原始关系网络和无向分析网络。"""

    ids = set(nodes["id"].astype(str))
    data = edges[
        (edges["relation_type"] == relation)
        & edges["source_id"].isin(ids)
        & edges["target_id"].isin(ids)
    ]

    # 层级和先修关系是有向图，关联关系按无向图分析
    if relation == "关联关系":
        original = nx.Graph()
    else:
        original = nx.DiGraph()

    original.add_nodes_from(ids)

    for source, target in data[
        ["source_id", "target_id"]
    ].itertuples(index=False, name=None):
        original.add_edge(source, target)

    # 使用无向投影计算可比较的结构指标
    G = nx.Graph()
    G.add_nodes_from(ids)
    G.add_edges_from(original.edges())

    return original, G


def render_relation_analysis(nodes, edges):

    st.header("三类知识关系网络对比分析")

    st.info(
        "依据教师提供的课程知识点表，"
        "分别分析层级关系、先修关系和关联关系。"
    )

    name_map = nodes.set_index("id")["name"].to_dict()

    graphs = {}
    summary = []

    for relation in RELATIONS:
        original, G = build_relation_graphs(
            nodes, edges, relation
        )

        graphs[relation] = (original, G)

        active = [
            n for n in G.nodes()
            if G.degree(n) > 0
        ]

        summary.append({
            "关系类型": relation,
            "知识点总数": G.number_of_nodes(),
            "参与关系的知识点数": len(active),
            "关系边数": original.number_of_edges(),
            "无向网络密度": round(nx.density(G), 4),
            "平均聚类系数": round(
                nx.average_clustering(G), 4
            ),
            "连通分量数": nx.number_connected_components(G),
            "孤立节点数": nx.number_of_isolates(G)
        })

    summary_df = pd.DataFrame(summary)

    # 1. 三类关系网络基本指标
    st.subheader("1. 三类关系网络基本指标")

    st.dataframe(
        summary_df,
        hide_index=True,
        use_container_width=True
    )

    st.caption(
        "为保证比较口径一致，网络密度、聚类系数"
        "和连通分量均采用108个节点的无向投影计算。"
        "先修关系的方向信息另行保留。"
    )

    # 2. 网络指标对比
    st.subheader("2. 网络结构指标对比")

    left, right = st.columns(2)

    with left:
        st.markdown("**关系边数对比**")
        st.bar_chart(
            summary_df.set_index("关系类型")[["关系边数"]]
        )

    with right:
        st.markdown("**无向网络密度对比**")
        st.bar_chart(
            summary_df.set_index("关系类型")[
                ["无向网络密度"]
            ]
        )

    # 3. 分关系识别关键知识点
    st.subheader("3. 各类关系中的关键知识点")

    relation = st.selectbox(
        "选择分析的关系网络",
        RELATIONS,
        key="relation_analysis_select"
    )

    original, G = graphs[relation]

    degree = dict(G.degree())
    betweenness = nx.betweenness_centrality(G)

    ranking = []

    for uid in G.nodes():
        item = {
            "知识点ID": uid,
            "知识点名称": name_map[uid],
            "节点度": degree[uid],
            "中介中心性": round(betweenness[uid], 4)
        }

        if relation != "关联关系":
            item["入度"] = original.in_degree(uid)
            item["出度"] = original.out_degree(uid)

        ranking.append(item)

    ranking_df = pd.DataFrame(ranking)

    if relation == "先修关系":
        primary = "出度"
    elif relation == "层级关系":
        primary = "出度"
    else:
        primary = "节点度"

    ranking_df = ranking_df.sort_values(
        [primary, "中介中心性"],
        ascending=[False, False]
    ).reset_index(drop=True)

    st.dataframe(
        ranking_df.head(15),
        hide_index=True,
        use_container_width=True
    )

    if relation == "先修关系":
        st.caption(
            "先修关系中，出度反映某知识点被多少"
            "后续知识点直接依赖，入度反映其直接"
            "前置知识点数量。"
        )
    elif relation == "层级关系":
        st.caption(
            "层级关系中的出度代表直接下级知识点数量，"
            "中介中心性反映节点在层级结构中的桥梁作用。"
        )
    else:
        st.caption(
            "关联网络中的节点度反映直接关联的"
            "其他知识点数量。"
        )

    # 4. 度分布
    st.subheader("4. 节点度分布")

    degree_count = (
        pd.Series(list(degree.values()))
        .value_counts()
        .sort_index()
    )

    degree_count.index.name = "节点度"
    degree_count.name = "知识点数量"

    st.bar_chart(degree_count)

    # 5. 先修网络结构检查
    if relation == "先修关系":
        st.subheader("5. 先修关系结构检查")

        if nx.is_directed_acyclic_graph(original):
            st.success("先修关系网络不存在有向环。")
        else:
            components = [
                c for c in nx.strongly_connected_components(original)
                if len(c) > 1
                or any(original.has_edge(n, n) for n in c)
            ]

            st.warning(
                "先修关系网络存在循环依赖结构。"
                f"检测到 {len(components)} 个含环强连通分量。"
            )

            st.caption(
                "该结果用于描述课程表所形成的网络结构，"
                "不自动修改原始先修关系。"
            )

    # 6. 导出结果
    st.subheader("5. 分析结果导出" if relation != "先修关系"
                 else "6. 分析结果导出")

    col1, col2 = st.columns(2)

    with col1:
        st.download_button(
            "导出三类网络指标",
            summary_df.to_csv(
                index=False
            ).encode("utf-8-sig"),
            file_name="课程知识网络指标对比.csv",
            mime="text/csv"
        )

    with col2:
        st.download_button(
            "导出知识点中心性排名",
            ranking_df.to_csv(
                index=False
            ).encode("utf-8-sig"),
            file_name=f"{relation}_关键知识点.csv",
            mime="text/csv"
        )
