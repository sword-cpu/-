# 课程知识网络系统：第一步——数据预处理

当前版本只完成课程知识数据清洗与关系标准化，尚未开发前端系统或机器学习模型。

## PyCharm运行

1. 解压整个项目后，在 PyCharm 选择 **Open**，打开 `CourseKnowledgeSystem` 文件夹。
2. 确认已选择 Python 解释器，打开 PyCharm 下方 **Terminal**。
3. 在项目根目录执行：

   ```bash
   python -m pip install -r requirements.txt
   python preprocessing/clean_data.py
   ```

4. 执行后，检查 `data/processed/` 目录：
   - `nodes.csv`：知识点ID、名称、层级、父节点、教学属性
   - `edges.csv`：知识点关系（层级、先修、关联）及证据字段
   - `issues.csv`：需要人工核查的数据异常
   - `summary.json`：节点、关系、异常统计信息

## 处理原则

- 原Excel第一行是标题，第二行才是真正的表头。
- 数据中的 `15` 被视作占位值，不算知识点名称或关系。
- 不用知识点名称作唯一标识，因为有同名知识点；以 `K001` 这样的内部ID识别。
- 先修方向定义为 `前置知识 -> 后续知识`。
- 关联关系按无向关系存储，防止重复。
- 对于不在知识点表中的关系目标，以及目标重名造成歧义的关系，只登记异常，不猜测连接对象。
- `先修关系` 的双向字段印证仅说明录入一致，不等于教师已验证。
- 父级ID依据Excel中逐行的课程目录顺序推断，应结合原课程目录核验。
- 一旦发生原始课程表内容或目录顺序变化，需要重新运行脚本。

## 下一个开发任务

在 `nodes.csv` 和 `edges.csv` 的基础上使用 NetworkX 构建图谱，并通过 Streamlit + PyVis 实现浏览器可视化。
