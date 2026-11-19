
# -*- coding: utf-8 -*-
"""信息科学基础课程知识交互视图 V0.6

功能：
1. 知识体系层级树，点击展开和收起
2. 知识网络按层级排列，点击逐层展开
3. 先修关系和关联关系按需显示
4. 知识点搜索、定位及属性查看

适配 Streamlit 1.67+
"""

from collections import defaultdict
from html import escape

import streamlit as st


LEVEL_COLORS = {
    1: "#1e3a8a",
    2: "#2563eb",
    3: "#0d9488",
    4: "#d97706"
}

LIGHT_COLORS = {
    1: "#dbeafe",
    2: "#e0e7ff",
    3: "#ccfbf1",
    4: "#fef3c7"
}

REL_COLORS = {
    "层级关系": "#94a3b8",
    "先修关系": "#2563eb",
    "关联关系": "#10b981"
}


def _index(nodes):
    """根据知识点ID建立层级索引。"""

    rows = {
        str(r["id"]): r.to_dict()
        for _, r in nodes.iterrows()
    }

    children = defaultdict(list)

    for uid, row in rows.items():
        parent = str(row.get("parent_id", "")).strip()

        if parent in rows and parent != uid:
            children[parent].append(uid)

    roots = [
        uid for uid in rows
        if not any(uid in group for group in children.values())
    ]

    root = next(
        (
            uid for uid in roots
            if str(rows[uid].get("level")) == "1"
        ),
        roots[0] if roots else None
    )

    return rows, children, root


def _descendants(uid, children):
    """获取一个知识点的所有下级知识点。"""

    result = set()
    pending = list(children.get(uid, []))

    while pending:
        child = pending.pop()

        if child not in result:
            result.add(child)
            pending.extend(children.get(child, []))

    return result


def _visible(scope, children, expanded):
    """根据当前展开状态确定可见知识点。"""

    result = set()
    pending = [scope]

    while pending:
        uid = pending.pop()

        if uid in result:
            continue

        result.add(uid)

        if uid in expanded:
            pending.extend(
                reversed(children.get(uid, []))
            )

    return result


def _tip(uid, rows):
    """生成知识点详情提示。"""

    info = rows[uid]

    fields = [
        ("编号", uid),
        ("知识点", info.get("name", "")),
        ("层级", info.get("level", "")),
        ("认知维度", info.get("认知维度", "")),
        ("教学目标", info.get("教学目标", ""))
    ]

    return "<br/>".join(
        f"{escape(str(k))}：{escape(str(v))}"
        for k, v in fields
        if v is not None and str(v).strip()
    )


def _tree_data(uid, rows, children, visited=None):
    """生成课程知识层级树数据。"""

    if visited is None:
        visited = set()

    if uid in visited:
        return None

    level = int(rows[uid].get("level", 4))

    item = {
        "id": uid,
        "name": str(rows[uid]["name"]),
        "itemStyle": {
            "color": LEVEL_COLORS.get(
                level, "#64748b"
            ),
            "borderColor": "#ffffff",
            "borderWidth": 2
        },
        "tooltip": {
            "formatter": _tip(uid, rows)
        }
    }

    kids = [
        _tree_data(
            child,
            rows,
            children,
            visited | {uid}
        )
        for child in children.get(uid, [])
    ]

    kids = [child for child in kids if child is not None]

    if kids:
        item["children"] = kids

    return item


def _positions(scope, children, visible):
    """生成从左到右的固定层级坐标。"""

    xs = {}
    ys = {}
    ordered = []
    count = [0]

    def visit(uid, depth):

        if uid not in visible or uid in xs:
            return None

        xs[uid] = depth * 280
        ordered.append(uid)

        kids = [
            child
            for child in children.get(uid, [])
            if child in visible
        ]

        child_y = [
            visit(child, depth + 1)
            for child in kids
        ]

        child_y = [
            y for y in child_y
            if y is not None
        ]

        if child_y:
            y = sum(child_y) / len(child_y)
        else:
            y = count[0] * 94
            count[0] += 1

        ys[uid] = y
        return y

    visit(scope, 0)

    positions = {
        uid: (xs[uid], ys[uid])
        for uid in ordered
    }

    return positions, max(count[0], 1)


def _graph_payload(
    scope,
    expanded,
    selected,
    mode,
    show_full,
    rows,
    children,
    edges
):
    """生成知识网络节点及连线数据。"""

    visible = _visible(
        scope, children, expanded
    )

    positions, leaves = _positions(
        scope, children, visible
    )

    shown = list(positions)

    data = []

    for uid in shown:

        row = rows[uid]
        level = int(row.get("level", 4))

        x, y = positions[uid]

        name = str(row.get("name", uid))

        if not show_full and len(name) > 12:
            name = name[:12] + "…"

        has_children = bool(children.get(uid))

        if has_children:
            marker = (
                " −" if uid in expanded else " +"
            )
        else:
            marker = ""

        data.append({
            "id": uid,
            "name": name + marker,
            "x": x,
            "y": y,
            "symbol": "roundRect",
            "symbolSize": [192, 43],
            "itemStyle": {
                "color": LIGHT_COLORS.get(
                    level, "#f8fafc"
                ),
                "borderColor": (
                    "#e87923"
                    if uid == selected
                    else LEVEL_COLORS.get(
                        level, "#64748b"
                    )
                ),
                "borderWidth": (
                    3 if uid == selected else 1.5
                )
            },
            "label": {
                "show": True,
                "position": "inside",
                "fontSize": 11,
                "fontWeight": 600,
                "color": "#1e293b"
            },
            "tooltip": {
                "formatter": _tip(uid, rows)
            }
        })

    links = []

    for edge in edges.itertuples(index=False):

        source = str(edge.source_id)
        target = str(edge.target_id)
        relation = str(edge.relation_type)

        if source not in visible or target not in visible:
            continue

        if relation not in REL_COLORS:
            continue

        if mode == "仅层级结构":
            if relation != "层级关系":
                continue

        if mode == "仅展示选中节点的跨关系":
            if relation != "层级关系":
                if selected not in (source, target):
                    continue

        links.append({
            "source": source,
            "target": target,
            "value": relation,
            "lineStyle": {
                "color": REL_COLORS[relation],
                "width": (
                    1.6
                    if relation == "层级关系"
                    else 2
                ),
                "type": (
                    "dashed"
                    if relation == "关联关系"
                    else "solid"
                ),
                "curveness": (
                    0
                    if relation == "层级关系"
                    else 0.18
                ),
                "opacity": 0.8
            },
            "tooltip": {
                "formatter": (
                    f"{escape(relation)}<br/>"
                    f"{escape(rows[source]['name'])}"
                    " → "
                    f"{escape(rows[target]['name'])}"
                )
            }
        })

    return shown, data, links, leaves


# ==========================================
# 页面一：课程知识体系层级树
# ==========================================

def render_clickable_hierarchy(nodes):

    rows, children, root = _index(nodes)

    if root is None:
        st.error("未找到课程根节点。")
        return

    st.subheader("课程知识体系 · 层级树")

    st.caption(
        "点击节点展开或收起下级知识点，"
        "支持缩放、平移和模块切换。"
    )

    choices = [root] + children.get(root, [])

    scope = st.selectbox(
        "选择课程或二级知识模块",
        choices,
        format_func=lambda uid: (
            f"{uid}｜{rows[uid]['name']}"
        ),
        key="knowledge_tree_scope_v6"
    )

    c1, c2 = st.columns(2)

    c1.metric(
        "本模块知识点数",
        len(_descendants(scope, children)) + 1
    )

    c2.metric(
        "直属下级知识点数",
        len(children.get(scope, []))
    )

    tree = _tree_data(
        scope, rows, children
    )

    spec = {
        "backgroundColor": "#ffffff",

        "tooltip": {
            "trigger": "item",
            "backgroundColor": "#ffffff",
            "borderColor": "#dbe3ed",
            "textStyle": {
                "color": "#334155"
            }
        },

        "series": [{
            "type": "tree",
            "data": [tree],
            "layout": "orthogonal",
            "orient": "LR",
            "top": "5%",
            "bottom": "5%",
            "left": "6%",
            "right": "23%",
            "symbol": "circle",
            "symbolSize": 14,
            "roam": True,
            "initialTreeDepth": 1,
            "expandAndCollapse": True,
            "edgeShape": "polyline",
            "edgeForkPosition": "60%",

            "lineStyle": {
                "color": "#b8c7d8",
                "width": 1.6
            },

            "label": {
                "position": "left",
                "align": "right",
                "fontSize": 12,
                "color": "#334155",
                "fontWeight": 600,
                "backgroundColor": "#f8fafc",
                "borderRadius": 6,
                "padding": [5, 8]
            },

            "leaves": {
                "label": {
                    "position": "right",
                    "align": "left"
                }
            },

            "emphasis": {
                "focus": "descendant"
            },

            "animationDurationUpdate": 300
        }]
    }

    st.echarts_chart(
        spec,
        key=f"knowledge_tree_chart_v6_{scope}",
        height=720,
        alt="可点击展开的课程知识体系层级树"
    )

    st.caption(
        "深蓝：一级课程 · 蓝色：二级模块 · "
        "青绿：三级单元 · 橙色：四级知识点"
    )

    with st.expander("查看当前模块知识点目录"):

        scope_ids = (
            {scope} | _descendants(scope, children)
        )

        table = nodes[
            nodes["id"].isin(scope_ids)
        ].copy()

        table["父级知识点"] = (
            table["parent_id"]
            .map({
                uid: item["name"]
                for uid, item in rows.items()
            })
            .fillna("—")
        )

        st.dataframe(
            table[
                ["id", "name", "level", "父级知识点"]
            ],
            hide_index=True,
            use_container_width=True
        )


# ==========================================
# 页面二：分层交互式知识网络
# ==========================================

def render_clickable_network(nodes, edges):

    rows, children, root = _index(nodes)

    if root is None:
        st.error("未找到课程根节点。")
        return

    state = st.session_state

    choices = [root] + children.get(root, [])

    st.subheader("课程知识网络 · 分层交互")

    st.caption(
        "点击知识点展开直属下级，"
        "再次点击已展开的节点即可收起。"
    )

    scope = st.selectbox(
        "查看课程或二级知识模块",
        choices,
        format_func=lambda uid: (
            f"{uid}｜{rows[uid]['name']}"
        ),
        key="knowledge_network_scope_v6"
    )

    if state.get("kn_last_scope_v6") != scope:

        state["kn_last_scope_v6"] = scope
        state["kn_expanded_v6"] = {scope}
        state["kn_selected_v6"] = scope
        state["kn_epoch_v6"] = (
            state.get("kn_epoch_v6", 0) + 1
        )

    def reset_chart():
        state["kn_epoch_v6"] += 1

    c1, c2, c3 = st.columns(3)

    if c1.button(
        "恢复初始视图",
        key="kn_reset_v6",
        use_container_width=True
    ):
        state["kn_expanded_v6"] = {scope}
        state["kn_selected_v6"] = scope
        reset_chart()

    if c2.button(
        "展开到三级",
        key="kn_level3_v6",
        use_container_width=True
    ):

        scope_ids = (
            {scope} | _descendants(scope, children)
        )

        state["kn_expanded_v6"] = {
            uid for uid in scope_ids
            if int(rows[uid].get("level", 4)) <= 2
        }

        state["kn_expanded_v6"].add(scope)
        reset_chart()

    if c3.button(
        "展开当前全部",
        key="kn_all_v6",
        use_container_width=True
    ):
        state["kn_expanded_v6"] = (
            {scope} | _descendants(scope, children)
        )
        reset_chart()

    # 知识点搜索定位
    scope_ids = (
        {scope} | _descendants(scope, children)
    )

    target = st.selectbox(
        "搜索或定位知识点",
        [""] + [
            uid for uid in rows
            if uid in scope_ids
        ],
        format_func=lambda uid: (
            "选择知识点"
            if not uid
            else f"{uid}｜{rows[uid]['name']}"
        ),
        key=f"kn_target_v6_{scope}"
    )

    if st.button(
        "定位并展开上级",
        key="kn_locate_v6",
        disabled=not target
    ):

        current = target

        while current in rows and current != scope:

            parent = str(
                rows[current].get("parent_id", "")
            )

            if parent not in rows:
                break

            state["kn_expanded_v6"].add(parent)
            current = parent

        state["kn_selected_v6"] = target
        reset_chart()

    # 关系展示模式
    mode = st.radio(
        "关系显示方式",
        [
            "仅层级结构",
            "仅展示选中节点的跨关系",
            "显示当前全部关系"
        ],
        horizontal=True,
        key="kn_relation_mode_v6"
    )

    show_full = st.checkbox(
        "显示完整知识点名称",
        value=True,
        key="kn_full_names_v6"
    )

    # 生成知识图谱
    shown, data, links, leaves = _graph_payload(
        scope,
        state["kn_expanded_v6"],
        state["kn_selected_v6"],
        mode,
        show_full,
        rows,
        children,
        edges
    )

    m1, m2, m3 = st.columns(3)

    m1.metric("当前知识点", len(shown))
    m2.metric("当前关系", len(links))

    m3.metric(
        "当前最大层级",
        max(int(rows[uid]["level"]) for uid in shown)
    )

    if len(shown) > 55:
        st.info(
            "当前知识点较多，建议选择二级模块"
            "进行局部查看。"
        )

    st.caption(
        "灰色：层级关系 · "
        "蓝色：先修关系 · "
        "绿色虚线：关联关系"
    )

    spec = {
        "backgroundColor": "#ffffff",

        "tooltip": {
            "trigger": "item",
            "backgroundColor": "#ffffff"
        },

        "animationDurationUpdate": 300,

        "series": [{
            "type": "graph",
            "id": "course_knowledge_graph",
            "layout": "none",
            "data": data,
            "links": links,
            "roam": True,
            "draggable": False,
            "selectedMode": "single",
            "edgeSymbol": ["none", "none"],

            "label": {
                "show": True,
                "position": "inside"
            },

            "emphasis": {
                "focus": "adjacency"
            }
        }]
    }

    height = min(
        1450,
        max(620, 86 * leaves + 100)
    )

    event = st.echarts_chart(
        spec,
        key=(
            "knowledge_network_chart_v6_"
            f"{state['kn_epoch_v6']}"
        ),
        on_select="rerun",
        height=height,
        alt="点击节点逐层展开的课程知识网络"
    )

    # 处理图谱节点点击
    for group in event.selection.selected:

        if group.get("data_type") not in (
            "main", "node"
        ):
            continue

        indexes = group.get("data_indices", [])

        if not indexes:
            continue

        idx = indexes[-1]

        if not 0 <= idx < len(shown):
            continue

        chosen = shown[idx]

        state["kn_selected_v6"] = chosen

        if children.get(chosen):

            if chosen in state["kn_expanded_v6"]:

                state["kn_expanded_v6"].difference_update(
                    {chosen} | _descendants(
                        chosen, children
                    )
                )

            else:
                state["kn_expanded_v6"].add(chosen)

        reset_chart()

        # 清除旧图表选中事件并更新画面
        st.rerun()

    # 当前知识点详情
    selected = state["kn_selected_v6"]

    if selected in rows:

        item = rows[selected]

        st.markdown(
            f"#### 当前知识点："
            f"{item['name']}（{selected}）"
        )

        st.write(
            "**层级：**",
            item.get("level", ""),
            "　**直属下级：**",
            len(children.get(selected, [])),
            "个"
        )

        st.write(
            "**认知维度：**",
            item.get("认知维度", "") or "—"
        )

        st.write(
            "**教学目标：**",
            item.get("教学目标", "") or "—"
        )

        if children.get(selected):

            st.write(
                "**下属知识点：**",
                "、".join(
                    rows[uid]["name"]
                    for uid in children[selected]
                )
            )

        related = edges[
            (edges["source_id"] == selected)
            | (edges["target_id"] == selected)
        ].copy()

        related = related[
            related["relation_type"].isin(
                ["先修关系", "关联关系"]
            )
        ]

        if not related.empty:

            name_map = {
                uid: row["name"]
                for uid, row in rows.items()
            }

            related["起点"] = (
                related["source_id"].map(name_map)
            )

            related["终点"] = (
                related["target_id"].map(name_map)
            )

            with st.expander(
                "查看该知识点的先修与关联关系"
            ):

                st.dataframe(
                    related[
                        ["relation_type", "起点", "终点"]
                    ],
                    hide_index=True,
                    use_container_width=True
                )
