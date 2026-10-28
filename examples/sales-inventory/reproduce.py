import sys, json, hashlib, collections, datetime
from pathlib import Path
from decimal import Decimal
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
SKILL = ROOT.parents[1] / 'skills/ecommerce-daily-report'
sys.path.insert(0, str(SKILL / 'scripts'))
from tables import read_grid
WORK = ROOT / 'generated'
if (WORK/'report.html').exists():
    raise SystemExit('generated/report.html 已存在，请先移走旧结果以免覆盖。')
WORK.mkdir(exist_ok=True)
RUN = 'ecom-forward-20261027-v1'
def dump(name, obj): (WORK/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def read(name):
    grid, sheet = read_grid(ROOT/'input'/name)
    return [dict(zip(grid[0], row)) for row in grid[1:]],sheet
sales, ss = read('销售.csv'); stock, si = read('库存.csv')
assert len(sales)==6 and len(stock)==2
assert len({(r['日期'],r['SKU'],r['店铺']) for r in sales})==len(sales)
assert len({(r['快照时间'],r['SKU'],r['仓库']) for r in stock})==len(stock)
assert all(all(v is not None and v!='' for v in r.values()) for r in sales+stock)
assert {r['数量单位'] for r in sales+stock}=={'盒'}
dates=sorted({r['日期'] for r in sales}); skus=sorted({r['SKU'] for r in sales})
assert all(len([r for r in sales if r['日期']==d and r['SKU']==sku])==1 for d in dates for sku in skus)
metrics = ['支付件数','支付金额_元','当日发生退款金额_元']
def aggregate(rows): return {k:float(sum(Decimal(str(r[k])) for r in rows)) for k in metrics}
totals=aggregate(sales); daily={d:aggregate([r for r in sales if r['日期']==d]) for d in dates}; by_sku={s:aggregate([r for r in sales if r['SKU']==s]) for s in skus}
inventory={r['SKU']:float(Decimal(str(r['可售数量']))) for r in stock}
avg={s:by_sku[s]['支付件数']/len(dates) for s in skus}
cover={s:inventory[s]/avg[s] for s in skus}
shares={s:by_sku[s]['支付金额_元']/totals['支付金额_元']*100 for s in skus}
calc={'totals':totals,'daily':daily,'by_sku':by_sku,'inventory':inventory,'average_paid_units_per_observed_day':avg,'conditional_cover_days':cover,'paid_amount_shares_pct':shares,'inventory_total':sum(inventory.values()),'days':len(dates)}
dump('calculation.json',calc)
period=f'{dates[0]}—{dates[-1]}'
scope='店甲 · SKU A/B · 原表完整 6 条销售记录'
inv_scope='仓甲 · SKU A/B · 2026-10-22 23:59 单一库存快照'
condition='仅当仓甲对应店甲供给范围、以这 3 个观察日的支付件数均值作需求替代时成立；映射与需求适用性待确认。未计在途与其他需求，非缺货日期或采购量预测。'
source_list=[]
for i,name,sheet,ran,note in [('s1','销售.csv',ss,'A1:G7','全部 6 条数据行，表内日期 2026-10-20 至 10-22；未筛除、去重或改值。'),('s2','库存.csv',si,'A1:E3','全部 2 条数据行，同一快照 2026-10-22 23:59；可售字段直接使用，无重复扣减。')]:
    source_list.append({'id':i,'file':name,'sheet':sheet,'range':ran,'version':'SHA256 '+hashlib.sha256((ROOT/'input'/name).read_bytes()).hexdigest(),'note':note})
record={'run_id':RUN,'request':'用电商日报助手分析附件销售.csv、库存.csv，做销售、库存与补货可视化日报；有缺口写待确认，先交付能做的部分。','dataset_kind':'纯合成测试资料，不代表真实经营','sources':source_list,'roles':['AG01','AG02','AG03','AG04','AG05','AG23'],'execution_mode':'同一助手按角色方法分阶段执行与复算；未启动六个独立专家','sales_grain':['日期','SKU','店铺'],'inventory_grain':['快照时间','SKU','仓库'],'field_map':{k:k for k in sales[0]}|{k:k for k in stock[0]},'rules':['只描述附件实际观察期间，不称今天','销售、退款分别汇总，不计算净收入、订单数或客单价','库存为单份可售快照，不称对账一致','日期业务定义、时区和全天完整性未证实','同SKU可直接匹配为观察对象；仓店供给范围仍待确认','三日均值仅为短样本覆盖参考分母，非已确认预测需求','缺失在途/交期/MOQ不填零，不输出采购量'],'data_quality':{'sales_rows':len(sales),'inventory_rows':len(stock),'missing_cells':0,'duplicate_candidate_keys':0,'excluded_rows':0,'nonpositive_observed_values':'退款字段存在真实0；销量/金额/库存均为正','sku_match':'2/2 SKU标识及盒单位相同，供给关系待确认'},'readiness':{'sales':'partial：原字段汇总可用；净额和期间业务完整性待确认','inventory':'partial：可售快照展示可用；无独立对照表','replenishment':'partial：条件覆盖参考可用；采购量待确认'}}
dump('task_record.json',record)
def metric(name,value,unit,definition,refs):return dict(name=name,value=value,unit=unit,definition=definition,source_ids=refs)
def fact(text,refs,kind='fact'):return dict(kind=kind,text=text,source_ids=refs)
def chart(kind,title,unit,labels,series,refs,scope_,caption):return dict(kind=kind,title=title,unit=unit,scope=scope_,caption=caption,labels=labels,series=[dict(name=n,values=v) for n,v in series],source_ids=refs)
def rec(action,reason,verify):return dict(action=action,reason=reason,owner='待确认',due='待确认',verify=verify)
refund_gap='待确认：支付金额是否已扣退款、日期业务含义及订单归属；本期发生退款单列，未计算净收入或退款率。'
replenishment_gap='待确认：仓甲对店甲的供给范围、完整有效需求历史、缺货/活动、在途数量与到货日、交期、复核周期、安全库存、MOQ/箱规及供应约束。'
report={'schema_version':'1.0','report':{'title':'销售、库存与补货日报｜10月20—22日','type':'销售经营 + 库存快照 + 补货参考','task_id':RUN,'scope':'合成数据试用｜店甲销售与仓甲库存；SKU A/B。历史资料快照，缺口保留待确认。','period':period+'（沿用原表日期，业务时区与完整性待确认）','updated_at':'库存：2026-10-22 23:59；销售末日：2026-10-22；生成：'+'2026-10-28（公开合成示例）','status':'partial','review':{'status':'not_run','mode':'同一助手分阶段复算与呈现检查','summary':'草稿已由原表计算，等待独立计算路径与实际页面检查。','checks':[]}},'summary':[fact(f'资料覆盖 {period}，支付金额 {totals["支付金额_元"]:g} 元、支付件数 {totals["支付件数"]:g} 盒；当日发生退款合计 {totals["当日发生退款金额_元"]:g} 元单列。',['s1']),fact(f'2026-10-22 23:59 仓甲可售共 {sum(inventory.values()):g} 盒：A {inventory["A"]:g} 盒，B {inventory["B"]:g} 盒。',['s2']),fact('补货采购量待确认。三日均销条件参考下，A 覆盖 1.5 天、B 6 天；优先核实 A 的供给条件，不据此直接下单。',['s1','s2'],'inference')],'modules':[],'actions':[],'sources':source_list,'limitations':['本报告使用合成测试数据；未验证外部业务事实。','仅 3 个观察日期，未证实每天导出完整，也不足以判断长期趋势。',refund_gap,replenishment_gap,'缺独立可比库存来源，未完成账实或跨系统对账。','源表未提供业务时区；金额单位沿用“元”，不作币种换算。']}
report['modules'].append({'id':'sales','title':'销售与商品表现','question':'附件记录了多少支付，哪些 SKU 贡献较大？','agents':['AG03 销售经营分析','AG01 数据理解与校验'],'status':'partial','metrics':[metric('支付金额',totals['支付金额_元'],'元','销售.csv 第2—7行支付金额字段加总；按表内日期覆盖'+period+'，未扣退款。',['s1']),metric('支付件数',totals['支付件数'],'盒','销售.csv 第2—7行支付件数字段加总，不等于订单数或净销量。',['s1']),metric('当日发生退款',totals['当日发生退款金额_元'],'元','销售.csv 第2—7行当日发生退款金额字段加总；可能涉及跨期订单。',['s1'])],'charts':[chart('line','三日支付金额：1,250 → 1,450 → 1,050','元',dates,[('支付金额',[daily[d]['支付金额_元'] for d in dates])],['s1'],scope+'；'+period,'仅描述原表记录变化；完整性、可比性及变动原因待确认，不将短期波动认作长期趋势。'),chart('bar','A 占附件支付金额的 80%','元',skus,[('支付金额',[by_sku[s]['支付金额_元'] for s in skus])],['s1'],scope+'；'+period,'分母为本附件支付金额 3,750 元；A 3,000 元，B 750 元。')],'findings':[fact('A 支付 30 盒、3,000 元；B 支付 15 盒、750 元；金额贡献分别为 80% 与 20%。',['s1']),fact('10月22日记录支付 1,050 元、13 盒；A 800 元、B 250 元。',['s1']),fact('100 元发生退款全部记录在 10月21日 SKU A；其原订单归属期待确认。',['s1'])],'recommendations':[rec('核实店甲 SKU A 的日度销售变化','A 占资料支付金额80%，观察支付件数10→12→8盒；缺流量、活动和缺货佐证。','补齐同日期完整数据及活动/缺货记录后，再判断变化原因。'),rec('确认退款与支付金额口径','发生退款100元；未确认支付字段是否已扣退款。','取得字段说明和退款订单归属，再决定是否可算净额。')],'evidence':[{'source_id':'s1','locator':'CSV A1:G7；日期×SKU×店铺全部6行','calculation':'金额、支付件数、发生退款分别求和；按日期与SKU聚合回到总额。SKU贡献=SKU支付金额/3750；无去重、过滤、连接或退款二次扣减。'}],'limitations':[refund_gap,'未提供订单ID、访客、成本或目标，因此不推断订单数、转化、利润或达成率。']})
report['modules'].append({'id':'inventory','title':'可售库存快照','question':'仓甲在快照时点记录了多少可售库存？','agents':['AG02 库存核对'],'status':'partial','metrics':[metric('可售库存',sum(inventory.values()),'盒','库存.csv 第2—3行同一快照可售数量之和；两SKU均为盒。',['s2']),metric('SKU A 可售',inventory['A'],'盒','仓甲 2026-10-22 23:59 原表可售字段，未额外扣占用。',['s2']),metric('SKU B 可售',inventory['B'],'盒','仓甲 2026-10-22 23:59 原表可售字段，未额外扣占用。',['s2'])],'charts':[chart('column','可售库存：A 15 盒，B 30 盒','盒',skus,[('可售数量',[inventory[s] for s in skus])],['s2'],inv_scope,'仅展示单一来源；未与另一库存来源对账，不等于实物盘点结果。')],'findings':[fact('快照共45盒，两条记录未发现空值、重复候选键或负数。',['s2']),fact('原表已命名“可售数量”，本报告直接使用该字段，不重复扣减占用或冻结。',['s2']),fact('库存对账待确认：缺同SKU、同仓、同状态及可比时点的独立来源。',['s2'],'pending')],'recommendations':[rec('确认仓甲可售字段与供给范围','A/B的库存单位与销售表一致，但仓店供给关系未提供。','提供仓库覆盖店铺和可售字段说明；确认是否含共享池或其他店需求。'),rec('补充独立可比库存依据','只有一份库存快照，不能得出库存已对账结论。','以同一截止时点的ERP/WMS或盘点数据逐SKU核对。')],'evidence':[{'source_id':'s2','locator':'CSV A1:E3；第2行A、第3行B','calculation':'15+30=45盒；按快照×SKU×仓库检查候选键唯一；未做跨时点相加。'}],'limitations':['缺独立对照来源，仅完成快照结构检查。','没有批次、效期、成本或出入库流水，无法判断临期、库存成本和差异原因。']})
report['modules'].append({'id':'replenishment','title':'覆盖参考与补货待确认','question':'现有资料可支持哪些供给观察，补货决策还缺什么？','agents':['AG04 趋势与补货建议'],'status':'partial','metrics':[metric('A 条件覆盖参考',cover['A'],'天','15盒÷(观察期支付30盒÷3天)=1.5天。'+condition,['s1','s2']),metric('B 条件覆盖参考',cover['B'],'天','30盒÷(观察期支付15盒÷3天)=6天。'+condition,['s1','s2']),metric('采购数量',None,'盒','需求窗口、仓店映射、在途、交期、安全库存和MOQ/箱规缺失，不计算。',['s1','s2'])],'charts':[chart('bar','仅按三日支付均值计算的条件覆盖','天',skus,[('条件覆盖参考',[cover[s] for s in skus])],['s1','s2'],inv_scope+'；需求替代窗口 '+period,condition),{'kind':'table','title':'采购测算保留缺口','scope':'SKU A/B；观察窗口 '+period,'unit':'各列单位见列名','caption':'三日均销为观察均值，正式补货量保持待确认。','source_ids':['s1','s2'],'columns':[{'key':'daily','title':'观察日均支付','unit':'盒/日'},{'key':'available','title':'快照可售','unit':'盒'},{'key':'purchase','title':'采购数量','unit':'盒'},{'key':'inputs','title':'必要条件','unit':''}],'rows':[{'name':s,'daily':avg[s],'available':inventory[s],'purchase':'待确认','inputs':'映射/交期/在途/需求政策待确认'} for s in skus]}],'findings':[fact('观察期A日均支付10盒，B日均支付5盒；只用附件3个日期，不补造7天或30天数据。',['s1']),fact('若仓甲对应同一需求范围且观察均值适用，A静态覆盖小于B，宜优先核实供给条件。',['s1','s2'],'inference'),fact('确定采购数量、到货方案和缺货日期均待确认；未知在途未被填为零。',['s1','s2'],'pending')],'recommendations':[rec('优先核实 SKU A 的供给条件','A条件覆盖参考1.5天；该判断依赖仓店供给关系和需求方法成立。','确认范围、在途数量及到货日、交期后，检查供给时序与库存覆盖。'),rec('确认补货参数后再生成采购候选','仅3日历史，缺活动/缺货与MOQ等必要约束。','按已确认需求窗口、安全库存、有效在途及包装约束复算并人工确认。')],'evidence':[{'source_id':'s1','locator':'CSV第2/4/6行A，第3/5/7行B','calculation':'观察日期共3个；A(10+12+8)/3=10盒/日；B(5+5+5)/3=5盒/日。'}, {'source_id':'s2','locator':'CSV第2—3行','calculation':'可售15与30分别除以观察日均10与5，得到1.5与6天条件参考；未由此推出采购量。'}],'limitations':[condition,replenishment_gap]})
report['actions']=[{'object':'SKU A 供给条件','action':'确认仓店范围、在途和交期后重新评估','owner':'待确认','due':'待确认','verify':'检查到货时序和已确认需求窗口','status':'建议候选，待确认'},{'object':'销售退款与库存依据','action':'补齐退款字段说明及同口径独立库存快照','owner':'待确认','due':'待确认','verify':'净额口径确认；逐SKU库存对账','status':'建议候选，待确认'}]
dump('report.json',report)
out=WORK/'report.html'
if out.exists():
    raise SystemExit('generated/report.html 已存在，请先移走旧结果以免覆盖。')
import subprocess
subprocess.run([sys.executable,str(SKILL/'scripts/render_report.py'),'--data',str(WORK/'report.json'),'--output',str(out)],check=True)
print('合成示例已生成；此脚本执行固定示例计算，不调用 AI，不适用于任意表格。')
