# 信息科学基础课程知识网络系统

这是在第一步课程数据预处理项目基础上增加的第二步原型。第一步的数据和 `preprocessing/clean_data.py` 保留；新增 Streamlit 浏览器界面，用于展示知识网络、查询知识点、查看网络结构概况、检查学习路径，并浏览数据核查问题。

## 在 PyCharm 中启动

1. 解压本项目，并用 PyCharm 打开包含 `app.py`、`data`、`preprocessing` 的项目根目录。
2. 在 PyCharm Terminal 确认当前目录是项目根目录，再运行：

   ```powershell
   python -m pip install -r requirements.txt
   python -m streamlit run app.py
   ```

3. 浏览器打开 Streamlit 显示的本机地址，通常是 `http://localhost:8501`。

如果提示缺少 `data/processed` 文件，可先运行：

```powershell
python preprocessing/clean_data.py
```

## 系统页面

- **系统总览**：查看知识点、层级、关系及数据异常概况。
- **知识网络**：按关系类型筛选网络；搜索节点后查看其两层邻域。可缩放、平移并悬停查看节点信息。
- **知识点查询**：查看层级属性、教学目标、知识说明及相邻关系。
- **学习路径检查**：按顺序输入知识点名称或 ID，查看路径内顺序冲突和缺少的候选前置点。
- **数据问题清单**：筛选、查看并下载第一步生成的异常记录。

## 模型解释边界

图中的“先修关系”来自课程表字段，`字段双向一致`表示前置与后续字段相互印证，不等于教师已审核其教学合理性。路径检查结果是基于当前候选关系的规则检查，适合演示和关系复核，不代表学习效果预测。原表中的重名、关系目标歧义和有向环仍需要教师或课程内容核验。

## 主要技术

Python、pandas、NetworkX、Streamlit、Plotly。当前版本用 Plotly 绘制可缩放交互网络，不需要单独配置图数据库。
