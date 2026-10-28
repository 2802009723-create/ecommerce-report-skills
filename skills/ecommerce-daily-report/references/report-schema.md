日报 HTML 模板填写规范 v1.0（给 AG05 / 执行 AI）

交付流程
1. 用原表完成计算，先生成draft草稿供复核，再根据真实复核记录更新；准备以下结构的结果 JSON。来源只登记实际读取的文件；不沿用角色验收案例中的虚构数字。
2. 复制 assets/report-template.html 为一个新文件，只替换 id="report-data" 的 JSON 数据块。保留内联图表库和样式，不需要重写或逐行阅读库代码。
3. 有 Python 3 时可执行：python3 "<技能目录>/scripts/render_report.py" --data "分析结果.json" --output "我的日报.html"。默认自动定位包内模板；可用 --template 指定另一份模板。脚本拒绝覆盖已有文件。无 Python 时可自行替换数据块：用标准 JSON 序列化，把所有小于号 < 转义为 \u003c，避免文本中的脚本结束标记破坏 HTML。
4. 实际打开新 HTML 验证图表与数据；结构检查只检查字段和引用，不会证明原表真实、指标算对或口径适用。

顶层结构（占位文字与空列表不是成品内容；按真实任务填入）
{
  "schema_version": "1.0",
  "report": {
    "title": "填写日报名称", "type": "填写日报类型", "task_id": "本次任务ID（由助手生成）",
    "scope": "实际业务范围", "period": "实际统计周期及时区", "updated_at": "资料版本或截至时间",
    "status": "draft",
    "review": {"status": "not_run", "mode": "", "summary": "", "checks": []}
  },
  "summary": [], "modules": [], "actions": [], "sources": [], "limitations": []
}

模块 modules：按用户需求和可用数据确定的模块添加，每个模块结构如下。
{
  "id": "唯一英文字母数字下划线标识", "title": "模块名称", "question": "本模块回答的问题",
  "agents": ["AG编号及名称"], "status": "partial",
  "metrics": [], "charts": [], "findings": [], "recommendations": [], "evidence": [],
  "limitations": ["实际缺口或结论范围；无图表时必须解释缺口或不适用原因"]
}

各字段明细
• sources 每项：{"id":"s1","file":"实际文件名","sheet":"真实Sheet","range":"真实数据范围","version":"真实附件版本或文件哈希","note":"读取、过滤或快照说明"}。id 唯一。source_ids 只能引用这些来源ID。
• metrics 每项：{"name":"指标名","value":null,"unit":"单位","definition":"公式、分母、周期及范围","source_ids":[]}。value 只能是数字或 null，未知不填零。百分数按最终展示尺度填写，并注明单位%，不得把比值与百分数混用。
• summary 和 findings 每项：{"kind":"fact","text":"有依据的发现","source_ids":["s1"]}。kind 支持 fact、inference、pending；有确定事实或判断时须有来源。首页与模块各优先展示不超过三条，其余折叠。
• recommendations 每项：{"action":"具体动作","reason":"依据与条件","owner":"待确认或实际责任岗位","due":"待确认或实际时限","verify":"验证方法"}。优先展示两条，其余折叠。
• evidence 每项：{"source_id":"s1","locator":"原表Sheet/原行/筛选范围","calculation":"计算过程、排除规则及对账说明"}。
• actions 每项：{"object":"关联问题或对象","action":"动作","owner":"责任岗位或待确认","due":"时限或待确认","verify":"验证方法","status":"真实状态"}。
• limitations 是文字列表；跨模块的缺口也在顶层保留。

charts：仅用真实数值，支持下面四种形态，按实际问题选择，无需凑齐。
数值图表：
{"kind":"line","title":"有依据的发现或中性图题","scope":"范围与周期","unit":"单位","caption":"解释及限制","source_ids":["s1"],"labels":[],"series":[{"name":"序列名称","values":[]}]}
• line：labels 使用严格递增的 YYYY-MM-DD 日期。values 与 labels 等长，只能为数字或 null；null 会保留断点。不可用商品、店铺等类别做折线横轴。预测与实测分图呈现。
• column：分类柱形图。labels 为分类名称，values 为数字；保留负值，不设置截断基线。
• bar：分类条形图，结构同 column；需要排序时同时调整分类与各序列，不能只重排数值。
• 数值图每条序列长度都应与 labels 相同，unit、scope、source_ids 必填。分类图有未知值时先说明受影响范围后只绘制有效部分，或改用明细表，不能自动填零。没有有效数值不画图。
明细表：
{"kind":"table","title":"表标题","scope":"统计范围","unit":"各列单位见列名","caption":"阅读说明","source_ids":["s1"],"columns":[{"key":"value","title":"列名","unit":"单位"}],"rows":[]}
• rows 每行含 name（行对象）和对应 key 的单元格；单元格可以是文本、数字、null。列 key 唯一，只用英文字母数字下划线，不使用 name、__proto__、constructor、prototype。
• 复杂字段或精确数字优先用 table；它不是靠虚构指标补出的图形。其他图种需要另行实现和真实验证，不能只修改 kind 名称。

状态与复核
• report.status：template 只用于空模板；draft 为待复核；partial 为有明确缺口的部分交付；ready 为约定范围已完成且已记录复核。模块 status 支持 draft、ready、partial、blocked。
• review.status：not_run、needs_review、checked。mode 如实说明同一助手分阶段复核或实际独立复核，不把多个角色名当作多个独立模型。
• review.checks 每项：{"item":"实际检查项","status":"not_run","evidence":"检查方法、来源、观察结果"}，status 支持 pass、fail、not_run、na。
• checked 必须有实际检查记录和依据，所有检查为 pass 或有理由的 na。有 fail / not_run 时使用 needs_review。ready 需所有已请求模块 ready、真实来源及 checked 复核记录；不要为通过结构校验虚填记录。

最后核对：任务范围和版本一致，指标与图表共用计算结果，源表位置可回查，每个模块有对应 Ag 的简短建议；实际打开后无空白图框、图表错误提示或溢出。
