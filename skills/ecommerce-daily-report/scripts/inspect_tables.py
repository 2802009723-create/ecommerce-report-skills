"""Read-only spreadsheet preview; formulas are excluded and explicitly reported."""
import argparse,json
from pathlib import Path
from tables import read_grid,sheet_names
p=argparse.ArgumentParser();p.add_argument('files',nargs='+');p.add_argument('--preview',type=int,default=6)
a=p.parse_args();result=[]
if not 0<=a.preview<=50:p.error('--preview 需在 0—50 之间')
for f in a.files:
    path=Path(f)
    try:
        names=sheet_names(path) if path.suffix.lower()=='.xlsx' else [None]
        for name in names:
            try:
                omitted=[];grid,sheet=read_grid(path,name,formula_policy='exclude',omitted=omitted)
                result.append({'file':path.name,'sheet':sheet,'rows':len(grid),'preview':grid[:a.preview],
                  'excluded_cells':omitted,'warning':'公式或错误单元格被排除；此预览不是完整计算' if omitted else ''})
            except Exception as e:result.append({'file':path.name,'sheet':name or 'CSV','error':str(e)})
    except Exception as e:result.append({'file':path.name,'error':str(e)})
print(json.dumps(result,ensure_ascii=False,default=str,allow_nan=False,indent=2))
