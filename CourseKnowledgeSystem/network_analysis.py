
# -*- coding: utf-8 -*-
"""课程知识网络结构分析模块"""

from itertools import islice

import networkx as nx
import pandas as pd
import streamlit as st


def render_network_analysis(nodes, edges):

    st.subheader("复杂网络结构分析")
    st.caption("基于课程知识点和候选关系进行网络分析")

    # 1. 检查节点与关系
    names = nodes.set_index("id")["name"].to_dict()
    ids = set(names)

    valid = edges[
        edges["source_id"].isin(ids)
        & edges["target_id"].isin(ids)
    ].copy()

    relation_types = [
        r for r in ["层级关系", "先修关系", "关联关系"]
        if r in set(valid["relation_type"])
    ]

    chosen_types = st.multiselect(
        "选择参与综合网络分析的关系",
        relation_types,
        default=relation_types,
        key="network_analysis_types"
    )

    if not chosen_types:
        st.info("请至少选择一种关系类型")
        return

    chosen = valid[
        valid["relation_type"].isin(chosen_types)
    ]

    # 2. 构建综合无向网络
    G = nx.Graph()
    G.add_nodes_from(ids)

    G.add_edges_from(
        (row.source_id, row.target_id)
        for row in chosen.itertuples(index=False)
        if row.source_id != row.target_id
    )

    st.markdown("### 1. 网络基本统计")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("知识点数", G.number_of_nodes())
    c2.metric("网络边数", G.number_of_edges())
    c3.metric("网络密度", f"{nx.density(G):.4f}")
    c4.metric("连通分量数", nx.number_connected_components(G))

    c5, c6 = st.columns(2)
    c5.metric(
        "平均聚类系数",
        f"{nx.average_clustering(G):.4f}"
    )
    c6.metric(
        "孤立知识点数",
        nx.number_of_isolates(G)
    )

    st.caption(
        "综合网络为无向简单图。多种关系连接同一对知识点时，"
        "在该网络中只计算一条边。"
    )

    # 3. 计算网络中心性
    st.markdown("### 2. 关键知识点识别")

    degree = dict(G.degree())
    degree_center = nx.degree_centrality(G)
    between_center = nx.betweenness_centrality(G)

    ranking = pd.DataFrame([
        {
            "知识点": f"{uid}｜{names[uid]}",
            "节点度": degree[uid],
            "度中心性": round(degree_center[uid], 4),
            "中介中心性": round(between_center[uid], 4)
        }
        for uid in G.nodes()
    ])

    ranking = ranking.sort_values(
        ["节点度", "中介中心性"],
        ascending=[False, False]
    ).head(15).reset_index(drop=True)

    st.dataframe(
        ranking,
        hide_index=True,
        use_container_width=True
    )

    st.markdown("### 3. 节点度分布")

    degree_distribution = (
        pd.Series(list(degree.values()))
        .value_counts()
        .sort_index()
    )

    degree_distribution.index.name = "节点度"
    degree_distribution.name = "知识点数量"

    st.bar_chart(degree_distribution)

    st.caption(
        "节点度表示连接的其他知识点数量；"
        "中介中心性表示节点在网络最短路径中的桥梁作用。"
    )

    # 4. 构建有向先修关系网络
    st.markdown("### 4. 先修关系网络分析")

    prereq = valid[
        valid["relation_type"] == "先修关系"
    ]

    P = nx.DiGraph()
    P.add_nodes_from(ids)

    P.add_edges_from(
        (row.source_id, row.target_id)
        for row in prereq.itertuples(index=False)
    )

    is_dag = nx.is_directed_acyclic_graph(P)

    cyclic_components = [
        comp for comp in nx.strongly_connected_components(P)
        if len(comp) > 1
        or any(P.has_edge(n, n) for n in comp)
    ]

    p1, p2, p3 = st.columns(3)

    p1.metric("候选先修关系数", P.number_of_edges())
    p2.metric("是否为有向无环图", "是" if is_dag else "否")
    p3.metric("含环强连通分量数", len(cyclic_components))

    # 5. 分析知识点的先修入度与出度
    st.markdown("### 5. 先修依赖程度分析")

    prior = pd.DataFrame([
        {
            "知识点": f"{uid}｜{names[uid]}",
            "前置知识数（入度）": P.in_degree(uid),
            "后续依赖数（出度）": P.out_degree(uid)
        }
        for uid in P.nodes()
    ])

    prior = prior[
        (prior["前置知识数（入度）"] > 0)
        | (prior["后续依赖数（出度）"] > 0)
    ]

    prior = prior.sort_values(
        ["后续依赖数（出度）", "前置知识数（入度）"],
        ascending=[False, False]
    )

    st.dataframe(
        prior.head(15),
        hide_index=True,
        use_container_width=True
    )

    st.caption(
        "入度表示候选前置知识数量；"
        "出度表示直接依赖该知识点的后续知识数量。"
    )

    # 6. 检测先修关系中的有向环
    st.markdown("### 6. 先修关系循环依赖检测")

    if is_dag:
        st.success("当前候选先修网络未检测到有向环")

    else:
        st.warning(
            "当前候选先修网络存在循环依赖，"
            "需要结合课程内容进行教师审核。"
        )

        # 最多列出5条示例，避免枚举过多
        examples = list(islice(nx.simple_cycles(P), 5))

        for i, cycle in enumerate(examples, 1):
            path = cycle + [cycle[0]]

            description = " → ".join(
                f"{uid}（{names[uid]}）"
                for uid in path
            )

            st.write(f"**示例环 {i}：** {description}")

        st.caption(
            "这里展示的是最多5条循环依赖示例，"
            "不代表整个网络中只有这些环。"
        )

    st.info(
        "当前先修关系均为候选关系，尚未完成教师审核。"
        "网络指标用于课程结构分析，不直接等同于"
        "知识难度或教学重要性。"
    )

    st.caption(
        "先修网络始终使用全部候选先修关系，"
        "不受上方综合网络关系筛选影响。"
    )
