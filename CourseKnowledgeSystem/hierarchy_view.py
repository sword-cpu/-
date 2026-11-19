
# -*- coding: utf-8 -*-
"""课程知识体系层级视图：根据教师课程表建立知识树。"""

from html import escape

import networkx as nx
import pandas as pd
import plotly.graph_objects as go

COLORS = {
    1: "#172554",
    2: "#2563eb",
    3: "#06b6d4",
    4: "#f59e0b"
}


def build_tree(nodes):
    """根据知识点ID和父节点ID建立层级树。"""
    g = nx.DiGraph()

    for _, row in nodes.iterrows():
        g.add_node(row["id"])

    ids = set(nodes["id"])

    for _, row in nodes.iterrows():
        parent = row["parent_id"]
        if parent and parent in ids and parent != row["id"]:
            g.add_edge(parent, row["id"])

    return g


def tree_positions(subtree, root):
    """生成从左至右的层级布局。"""
    x, y = {}, {}
    leaf_number = [0]

    def visit(node, depth):
        x[node] = depth
        children = list(subtree.successors(node))

        if children:
            for child in children:
                visit(child, depth + 1)
            y[node] = (
                sum(y[child] for child in children)
                / len(children)
            )
        else:
            y[node] = leaf_number[0]
            leaf_number[0] += 1

    visit(root, 0)

    return (
        x,
        {node: -value for node, value in y.items()},
        leaf_number[0]
    )


def make_tree_figure(
    subtree, root, node_data, show_labels=True
):
    """绘制课程知识层级树。"""
    x, y, leaves = tree_positions(subtree, root)
    fig = go.Figure()

    # 绘制层级连接线
    ex, ey = [], []

    for source, target in subtree.edges():
        ex.extend([x[source], x[target], None])
        ey.extend([y[source], y[target], None])

    fig.add_trace(go.Scatter(
        x=ex,
        y=ey,
        mode="lines",
        line=dict(color="#94a3b8", width=1.4),
        hoverinfo="skip",
        showlegend=False
    ))

    # 按知识层级绘制节点
    levels = sorted({
        int(node_data[k]["level"])
        for k in subtree.nodes
    })

    for level in levels:
        ids = [
            k for k in subtree.nodes
            if int(node_data[k]["level"]) == level
        ]

        hover = []

        for k in ids:
            info = node_data[k]

            hover.append(
                f"<b>{escape(str(info['name']))}</b><br>"
                f"ID：{escape(str(k))}<br>"
                f"层级：第{level}级<br>"
                f"认知维度："
                f"{escape(str(info.get('认知维度', '')))}<br>"
                f"教学目标："
                f"{escape(str(info.get('教学目标', '')))}"
            )

        fig.add_trace(go.Scatter(
            x=[x[k] for k in ids],
            y=[y[k] for k in ids],
            mode=(
                "markers+text"
                if show_labels else "markers"
            ),
            text=[
                str(node_data[k]["name"])
                for k in ids
            ],
            textposition="middle right",
            textfont=dict(size=10),
            marker=dict(
                size=14 if level <= 2 else 10,
                color=COLORS.get(level, "#64748b"),
                line=dict(color="white", width=1)
            ),
            hovertext=hover,
            hoverinfo="text",
            name=f"第{level}级"
        ))

    fig.update_layout(
        height=min(1400, max(530, 34 * leaves + 100)),
        margin=dict(l=10, r=160, t=25, b=25),
        xaxis=dict(
            visible=False,
            range=[-0.1, max(x.values()) + 0.9]
        ),
        yaxis=dict(visible=False),
        plot_bgcolor="white",
        legend=dict(orientation="h", y=-0.03),
        hovermode="closest"
    )

    return fig


def render_hierarchy_view(nodes, edges):
    """Streamlit课程层级展示页面。"""
    import streamlit as st

    st.subheader("课程知识体系层级视图")

    st.caption(
        "按照课程表中的知识点层级及父子关系展示，"
        "不混入先修关系和关联关系。"
    )

    node_data = nodes.set_index("id").to_dict("index")
    g = build_tree(nodes)

    roots = [
        k for k in g.nodes
        if g.in_degree(k) == 0
    ]

    if not roots:
        st.error("无法找到课程根节点，请检查parent_id。")
        return

    root = next(
        (
            k for k in roots
            if str(node_data[k]["level"]) == "1"
        ),
        roots[0]
    )

    modules = list(g.successors(root))
    options = [root] + modules

    # 模块选择
    scope = st.selectbox(
        "选择展示范围",
        options,
        format_func=lambda uid: (
            f"{uid}｜{node_data[uid]['name']}"
        ),
        key="hierarchy_scope"
    )

    top_level = int(node_data[scope]["level"])

    max_level = max(
        int(item["level"])
        for item in node_data.values()
    )

    # 控制树的显示深度
    depth = st.slider(
        "显示到第几级知识点",
        min_value=top_level,
        max_value=max_level,
        value=2 if scope == root else max_level,
        key=f"hierarchy_depth_{scope}"
    )

    show_labels = st.checkbox(
        "显示知识点名称",
        value=True,
        key="hierarchy_labels"
    )

    # 根据选中模块提取子树
    allowed = {
        k for k in (nx.descendants(g, scope) | {scope})
        if int(node_data[k]["level"]) <= depth
    }

    subtree = g.subgraph(allowed).copy()

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "当前知识点数",
        subtree.number_of_nodes()
    )

    c2.metric(
        "层级连接数",
        subtree.number_of_edges()
    )

    c3.metric("当前最大层级", depth)

    # 显示层级图
    fig = make_tree_figure(
        subtree, scope, node_data, show_labels
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={
            "scrollZoom": True,
            "displaylogo": False
        }
    )

    if subtree.number_of_nodes() > 50:
        st.caption(
            "节点较多，建议选择二级知识模块"
            "进行局部查看。"
        )

    # 展示课程层级目录
    st.markdown("#### 当前范围内的知识点目录")

    summary = nodes[
        nodes["id"].isin(allowed)
    ].copy()

    summary["上级知识点"] = (
        summary["parent_id"]
        .map({
            k: v["name"]
            for k, v in node_data.items()
        })
        .fillna("课程根节点")
    )

    st.dataframe(
        summary[
            [
                "id", "name", "level",
                "上级知识点", "认知维度", "分类"
            ]
        ],
        hide_index=True,
        use_container_width=True
    )

    st.download_button(
        "导出当前层级目录 CSV",
        summary.to_csv(index=False).encode("utf-8-sig"),
        file_name="课程知识体系层级目录.csv",
        mime="text/csv"
    )

    st.info(
        "层级视图用于描述知识点的从属关系。"
        "先修关系和关联关系请在知识网络页面查看。"
    )
