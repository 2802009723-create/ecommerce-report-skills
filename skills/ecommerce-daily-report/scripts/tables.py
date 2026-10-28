"""Read value-only XLSX/CSV/TSV with Python standard library; no macros/formulas executed."""
import csv, io, re, posixpath, zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
RID='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
def node(z,name):
    raw=z.read(name)
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('不支持含 XML 实体定义的工作簿')
    return ET.fromstring(raw)
def checked_zip(path):
    z=zipfile.ZipFile(path)
    if len(z.infolist())>10000 or sum(i.file_size for i in z.infolist())>100_000_000:
        z.close(); raise ValueError('工作簿展开超过 100 MB 或文件数过多，请精简')
    return z
def sheets(z):
    wb=node(z,'xl/workbook.xml')
    rels={e.get('Id'):e for e in node(z,'xl/_rels/workbook.xml.rels')}
    result=[]
    for s in wb.findall('s:sheets/s:sheet',NS):
        rel=rels[s.get(RID)]
        if rel.get('TargetMode')=='External': raise ValueError('不读取外部工作表')
        target=rel.get('Target','')
        target=posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join('xl',target))
        if not target.startswith('xl/'): raise ValueError('工作表路径无效')
        if not rel.get('Type','').endswith('/worksheet'): continue
        result.append((s.get('name'),target))
    if not result: raise ValueError('找不到标准 XLSX 工作表，请另存为标准 .xlsx 或 CSV')
    return wb,result
def sheet_names(path):
    with checked_zip(path) as z:return [name for name,_ in sheets(z)[1]]
def date_style(z):
    if 'xl/styles.xml' not in z.namelist():return set()
    root=node(z,'xl/styles.xml')
    codes={int(e.get('numFmtId')):e.get('formatCode','') for e in root.findall('s:numFmts/s:numFmt',NS)}
    result=set()
    for i,e in enumerate(root.findall('s:cellXfs/s:xf',NS)):
        n=int(e.get('numFmtId','0'))
        code=re.sub(r'"[^"]*"|\\.|\[[^\]]*\]','',codes.get(n,'')).lower()
        if n in set(range(14,23))|set(range(27,37))|set(range(45,48))|set(range(50,59)) or re.search('[ydhs]',code):result.add(i)
    return result
def read_grid(path,sheet=None,formula_policy="reject",omitted=None):
    if formula_policy not in ("reject","exclude"):raise ValueError("未知公式读取策略")
    omitted=[] if omitted is None else omitted
    path=Path(path)
    if path.suffix.lower()!='.xlsx':
        if path.suffix.lower() not in ('.csv','.tsv'):raise ValueError('支持 .xlsx/.csv/.tsv；旧 .xls 请另存')
        raw=path.read_bytes()
        try:content=raw.decode('utf-8-sig')
        except UnicodeDecodeError:content=raw.decode('gb18030')
        rows=list(csv.reader(io.StringIO(content),delimiter='\t' if path.suffix.lower()=='.tsv' else ','))
        if len(rows)>50001 or any(len(r)>100 for r in rows):raise ValueError('首版每张表最多 5 万行、100 列')
        return rows,'CSV'
    with checked_zip(path) as z:
        wb,ss=sheets(z)
        chosen=next(((name,target) for name,target in ss if sheet is None or name==sheet),None)
        if not chosen:raise ValueError('工作表不存在：'+str(sheet))
        name,target=chosen
        strings=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            strings=[''.join(t.text or '' for t in si.iter('{'+NS['s']+'}t')) for si in node(z,'xl/sharedStrings.xml').findall('s:si',NS)]
        dates=date_style(z)
        props=wb.find('s:workbookPr',NS)
        is1904=props is not None and props.get('date1904') in ('true','1')
        tree=node(z,target)
        ranges=[]
        if formula_policy=='exclude':
            def coords(ref):
                m=re.fullmatch(r'([A-Z]+)([0-9]+)',ref)
                if not m:raise ValueError('公式范围无效')
                col=0
                for ch in m.group(1):col=col*26+ord(ch)-64
                return int(m.group(2)),col
            for f in tree.findall('.//s:f',NS):
                if f.get('ref'):
                    ends=f.get('ref').split(':')
                    ranges.append((coords(ends[0]),coords(ends[-1])))
        rows=[]
        for r in tree.findall('s:sheetData/s:row',NS):
            ri=int(r.get('r',len(rows)+1))
            if ri<1 or ri>50001:raise ValueError('首版每张表最多 5 万行')
            if ri<=len(rows):raise ValueError('工作表行号重复或倒序')
            while len(rows)<ri:rows.append([])
            row=rows[-1]
            for c in r.findall('s:c',NS):
                ref=c.get('r','');match=re.fullmatch(r'([A-Z]+)([0-9]+)',ref)
                if not match or int(match.group(2))!=ri:raise ValueError('工作表单元格坐标无效')
                col=0
                for letter in match.group(1):col=col*26+ord(letter)-64
                if col>100:raise ValueError('首版每张表最多 100 列')
                if col<=len(row):raise ValueError('单元格重复或倒序')
                while len(row)<col:row.append(None)
                is_formula=c.find('s:f',NS) is not None or any(a[0]<=ri<=b[0] and a[1]<=col<=b[1] for a,b in ranges)
                if is_formula:
                    if formula_policy=='reject':raise ValueError('工作簿含公式，请复制为数值后另存，避免缓存值过期')
                    omitted.append({'cell':ref,'kind':'formula'});continue
                if c.get('t')=='e' and formula_policy=='exclude':
                    omitted.append({'cell':ref,'kind':'error'});continue
                v=c.find('s:v',NS);value=v.text if v is not None else None
                t=c.get('t','n')
                if t=='inlineStr':value=''.join(n.text or '' for n in c.findall('.//s:t',NS))
                elif t=='s':value=strings[int(value)] if value is not None else None
                elif t=='b':value=value=='1'
                elif t=='e':raise ValueError('工作簿含错误单元格：'+ref+' '+str(value))
                elif t=='d':value=datetime.fromisoformat(value.replace('Z','+00:00')) if value else None
                elif t=='n' and value is not None:
                    value=float(value)
                    if int(c.get('s','0')) in dates:
                        offset=value+1 if not is1904 and 0<value<60 else value
                        value=(datetime(1904,1,1) if is1904 else datetime(1899,12,30))+timedelta(days=offset)
                    elif value.is_integer():value=int(value)
                row[col-1]=value
        return rows,name
