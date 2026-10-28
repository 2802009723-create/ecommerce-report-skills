#!/usr/bin/env python3
"""将实际分析结果嵌入空白 HTML。仅标准库；不读取原表、不调用模型。"""
import argparse
import datetime
import json
import math
import re
from pathlib import Path


def require(ok, message):
    if not ok:
        raise ValueError(message)


def numeric(v):
    return v is None or (isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v))


def validate(data):
    require(isinstance(data, dict) and data.get('schema_version') == '1.0', 'schema_version 应为 1.0')
    report = data.get('report')
    require(isinstance(report, dict), '缺少 report 对象')
    require(report.get('status') in ['template', 'draft', 'partial', 'ready'], 'report.status 不受支持')
    for key in ['title', 'type', 'task_id', 'scope', 'period', 'updated_at']:
        require(isinstance(report.get(key), str), 'report.' + key + ' 应为文字')
    for key in ['summary', 'modules', 'actions', 'sources', 'limitations']:
        require(isinstance(data.get(key), list), key + ' 应为列表')
    sources = data['sources']
    ids = []
    for s in sources:
        require(isinstance(s, dict), 'source 应为对象')
        require(isinstance(s.get('id'), str) and re.fullmatch(r'[A-Za-z0-9_-]{1,100}', s['id']), 'source.id 格式错误')
        require(all(isinstance(s.get(k), str) for k in ['file', 'sheet', 'range', 'version', 'note']), '来源需包含 file/sheet/range/version/note 文字字段')
        require(bool(s['file'].strip()), '来源文件名不能为空')
        ids.append(s['id'])
    require(len(ids) == len(set(ids)), '来源 ID 重复')
    def refs(obj, required=False):
        values = obj.get('source_ids', [])
        require(isinstance(values, list) and all(isinstance(x, str) and x in ids for x in values), '引用了未登记的 source_id')
        if required:
            require(bool(values), '数值指标/图表需要来源引用')
    def finding(f):
        require(isinstance(f, dict) and f.get('kind') in ['fact', 'inference', 'pending'] and isinstance(f.get('text'), str), '发现需包含 kind 和 text')
        refs(f, f.get('kind') != 'pending')
    for f in data['summary']:
        finding(f)
    module_ids = set()
    for m in data['modules']:
        require(isinstance(m, dict), '模块应为对象')
        mid = m.get('id')
        require(isinstance(mid, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,100}', mid) and mid not in module_ids, '模块 ID 格式错误或重复')
        module_ids.add(mid)
        require(m.get('status') in ['ready', 'partial', 'blocked', 'draft'], '模块状态不受支持')
        require(isinstance(m.get('title'), str) and m['title'].strip(), '模块名称不能为空')
        require(isinstance(m.get('question'), str), '模块 question 应为文字')
        for key in ['agents', 'metrics', 'charts', 'findings', 'recommendations', 'evidence', 'limitations']:
            require(isinstance(m.get(key), list), '模块缺少列表 ' + key)
        require(all(isinstance(a, str) and a.strip() for a in m['agents']), 'agents 应填写角色编号及名称文本')
        require(all(isinstance(x, str) for x in m['limitations']), '模块 limitations 应为文字列表')
        if not m['charts']:
            require(bool(m['limitations']), '无图表的模块需说明缺口或不适用原因')
        for metric in m['metrics']:
            require(isinstance(metric, dict) and all(isinstance(metric.get(k), str) for k in ['name', 'unit', 'definition']), '指标缺名称/单位/口径')
            require('value' in metric and numeric(metric['value']), '指标 value 只能是有限数字或 null')
            refs(metric, metric['value'] is not None)
        for f in m['findings']:
            finding(f)
        for a in m['recommendations']:
            require(isinstance(a, dict) and all(isinstance(a.get(k), str) for k in ['action','reason','owner','due','verify']), '建议需包含 action/reason/owner/due/verify')
        for ev in m['evidence']:
            require(isinstance(ev, dict) and ev.get('source_id') in ids and all(isinstance(ev.get(k), str) for k in ['locator', 'calculation']), '计算依据需定位来源')
        for c in m['charts']:
            require(isinstance(c, dict) and c.get('kind') in ['line','column','bar','table'], '图表 kind 只能为 line/column/bar/table')
            require(all(isinstance(c.get(k), str) for k in ['title','scope','unit','caption']), '图表缺少标题、范围、单位或图注字段')
            require(c['title'].strip() and c['scope'].strip(), '图表标题和范围不能为空')
            refs(c, True)
            if c['kind'] == 'table':
                require(isinstance(c.get('columns'),list) and c['columns'] and isinstance(c.get('rows'),list) and c['rows'], '明细表需 columns 和 rows')
                keys=[]
                for col in c['columns']:
                    require(isinstance(col,dict) and all(isinstance(col.get(k),str) for k in ['key','title','unit']), '表格列需 key/title/unit')
                    require(col['key'] not in ['__proto__','constructor','prototype','name'] and re.fullmatch(r'[A-Za-z0-9_]{1,80}',col['key']), '表格列 key 需为安全标识，name 保留给行名')
                    keys.append(col['key'])
                require(len(keys)==len(set(keys)), '表格列 key 重复')
                for row in c['rows']:
                    require(isinstance(row,dict) and isinstance(row.get('name'),str), '表格每行需要 name')
                    for key in keys:
                        v=row.get(key)
                        require(isinstance(v,str) or numeric(v), '单元格只能是文字、数字或 null')
            else:
                require(bool(c['unit'].strip()), '数值图表单位不能为空')
                labels,series=c.get('labels'),c.get('series')
                require(isinstance(labels,list) and labels and all(isinstance(x,str) and x.strip() for x in labels), 'labels 应为非空文字列表')
                require(isinstance(series,list) and series, 'series 不能为空')
                count=0
                for s in series:
                    require(isinstance(s,dict) and isinstance(s.get('name'),str) and s['name'].strip() and isinstance(s.get('values'),list), '序列需 name 和 values')
                    values=s['values']
                    require(len(values)==len(labels) and all(numeric(v) for v in values), '序列长度或数值格式错误；不要把数字写成文本')
                    count+=sum(v is not None for v in values)
                    require(c['kind']=='line' or all(v is not None for v in values), '分类图有未知值，请用明细表或说明后仅画有效范围')
                require(count>0, '图表没有可绘制数值')
                if c['kind']=='line':
                    dates=[]
                    for v in labels:
                        require(re.fullmatch(r'\d{4}-\d{2}-\d{2}',v), '本模板折线 labels 请使用 YYYY-MM-DD 日期')
                        dates.append(datetime.date.fromisoformat(v))
                    require(all(b>a for a,b in zip(dates,dates[1:])), '折线日期必须严格递增')
    for action in data['actions']:
        require(isinstance(action,dict) and all(isinstance(action.get(k),str) for k in ['object','action','owner','due','verify','status']), '行动记录字段不完整')
    require(all(isinstance(x,str) for x in data['limitations']), 'limitations 应为文字列表')
    review=report.get('review')
    require(isinstance(review,dict) and review.get('status') in ['not_run','needs_review','checked'], '复核状态不正确')
    require(isinstance(review.get('mode'),str) and isinstance(review.get('summary'),str) and isinstance(review.get('checks'),list), '复核记录字段不完整')
    for c in review['checks']:
        require(isinstance(c,dict) and c.get('status') in ['pass','fail','not_run','na'] and isinstance(c.get('item'),str) and isinstance(c.get('evidence'),str), '检查记录需 item/status/evidence')
    if review['status']=='checked':
        require(review['mode'].strip() and review['checks'], '已记录复核须填写方式与实际检查')
        require(all(c['evidence'].strip() and c['status'] in ['pass','na'] for c in review['checks']), '有未检查/未通过项目时不能将复核设为 checked')
    if report['status']=='ready':
        require(data['modules'] and data['sources'] and review['status']=='checked', 'ready 需实际模块、来源和已记录复核')
        require(all(m['status']=='ready' for m in data['modules']), '有部分交付或阻塞模块时，整份日报应为 partial')
    return data


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', required=True, help='实际分析结果 JSON')
    parser.add_argument('--output', required=True, help='新生成的 HTML 路径')
    parser.add_argument('--template', default=str(Path(__file__).resolve().parent.parent/'assets'/'report-template.html'))
    args=parser.parse_args()
    src,template,out=map(lambda p:Path(p).expanduser().resolve(),[args.data,args.template,args.output])
    require(src.stat().st_size<=10*1024*1024,'结果JSON超过10MB，请汇总后再嵌入；原表单独保存')
    require(out.suffix.lower()=='.html','输出扩展名应为.html')
    require(out not in [src,template] and not out.exists(),'输出文件已存在或与输入相同，请选择新文件名')
    def reject(v):
        raise ValueError('JSON 不允许 NaN 或 Infinity')
    data=validate(json.loads(src.read_text(encoding='utf-8'),parse_constant=reject))
    content=template.read_text(encoding='utf-8')
    pattern=r'(<script\b(?=[^>]*\bid=["\x27]report-data["\x27])[^>]*>)[\s\S]*?(</script>)'
    require(len(re.findall(pattern,content))==1,'模板应有且仅有一个 report-data 数据块')
    payload=json.dumps(data,ensure_ascii=False,allow_nan=False,indent=2).replace('<','\\u003c')
    result=re.sub(pattern,lambda m:m.group(1)+'\n'+payload+'\n'+m.group(2),content,count=1)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x',encoding='utf-8') as f:
        f.write(result)
    print('已生成：'+str(out))
    print('仅完成数据结构检查与文件生成；请实际打开页面，并回查原表验证数字。')

if __name__=='__main__':
    try:
        main()
    except (ValueError,OSError,KeyError,TypeError) as e:
        raise SystemExit('未生成：'+str(e))
