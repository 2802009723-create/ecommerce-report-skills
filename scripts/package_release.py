"""Build deterministic public downloads from the checked-in skill and demo files."""
from pathlib import Path
import hashlib
import json
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills/ecommerce-daily-report'
OUT = ROOT / 'docs/downloads'
VERSION = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
if not re.fullmatch(r'\d+\.\d+\.\d+', VERSION):
    raise SystemExit('VERSION must contain a semantic version such as 1.2.0')
SKILL_ZIP = f'ecommerce-daily-report-v{VERSION}.zip'
SAMPLE_ZIP = 'sample-tables-and-report.zip'
OFFLINE_ZIP = 'ecommerce-report-offline.zip'
EXPECTED_ZIPS = {SKILL_ZIP, SAMPLE_ZIP, OFFLINE_ZIP}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def members():
    return sorted(p for p in SKILL.rglob('*') if p.is_file()
                  and p.name not in ('package-manifest.json', '.DS_Store')
                  and '__pycache__' not in p.parts and p.suffix != '.pyc')


def pack(path, entries):
    """UTF-8 filenames, fixed timestamps, no local paths or OS metadata."""
    names = set()
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(entries):
            if name in names or name.startswith('/') or '..' in Path(name).parts:
                raise ValueError(f'Invalid or duplicate archive path: {name}')
            names.add(name)
            item = zipfile.ZipInfo(name, date_time=(2026, 10, 28, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.create_system = 3
            item.external_attr = 0o100644 << 16
            archive.writestr(item, data)


def lines_for(names):
    return ''.join(f'{digest((OUT / name).read_bytes())}  {name}\n' for name in sorted(names))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    files = members()
    for p in files:
        if p.is_symlink():
            raise ValueError(f'Skill may not package external symlinks: {p.name}')
    manifest = {
        'name': 'ecommerce-daily-report', 'display_name': '电商日报助手',
        'version': VERSION,
        'role_count': len(list((SKILL / 'references/roles').glob('AG*.md'))),
        'report_type_count': len(list((SKILL / 'references/report-types').glob('*.md'))),
        'files_sha256': {p.relative_to(SKILL).as_posix(): digest(p.read_bytes()) for p in files},
    }
    manifest_file = SKILL / 'package-manifest.json'
    manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    pack(OUT / SKILL_ZIP, [
        ('ecommerce-daily-report/' + p.relative_to(SKILL).as_posix(), p.read_bytes())
        for p in files + [manifest_file]
    ])

    source_readme = (ROOT / 'examples/sales-inventory/README.md').read_text(encoding='utf-8')
    # This small data pack has no Python tools; do not advertise a command absent from it.
    source_readme = re.split(r'(?m)^## 无模型复现图表\s*$', source_readme)[0].rstrip()
    sample_readme = source_readme + '''\n\n## 此下载包包含什么\n\ninput/ 中的两份合成表格，以及“示例日报.html”。双击 HTML 可离线查看参考结果。\n如需用固定 Python 脚本复现，请下载 GitHub 仓库源码，按仓库 README 操作；此表格包不包含脚本或 Skill。\n'''
    sample_entries = [
        (p.relative_to(ROOT / 'examples/sales-inventory').as_posix(), p.read_bytes())
        for p in sorted((ROOT / 'examples/sales-inventory/input').glob('*.csv'))
    ]
    sample_demo = (ROOT / 'docs/demo.html').read_text(encoding='utf-8')
    sample_demo = re.sub(r'<aside\b(?=[^>]*(?:data-site-nav|public-demo-nav))[^>]*>.*?</aside>', '', sample_demo, flags=re.S)
    sample_entries += [('README.md', sample_readme.encode('utf-8')),
                       ('示例日报.html', sample_demo.encode('utf-8'))]
    pack(OUT / SAMPLE_ZIP, sample_entries)

    offline_entries = []
    for name in ('index.html', 'generator.html', 'demo.html', 'install.html', 'roles.html', 'validation.html'):
        content = (ROOT / 'docs' / name).read_bytes()
        if name in ('index.html', 'install.html'):
            text = content.decode('utf-8')
            text = re.sub(
                r'<a\b[^>]*href=["\x27][^"\x27]*ecommerce-report-offline\.zip["\x27][^>]*>.*?</a>',
                '<a class="button" href="install.html">查看安装说明</a>', text, flags=re.S)
            content = text.encode('utf-8')
        offline_entries.append((name, content))
    for name in ('quickstart.md', 'VALIDATION.md'):
        p = ROOT / 'docs' / name
        if p.is_file():
            offline_entries.append((name, p.read_bytes()))
    offline_entries += [(p.relative_to(ROOT / 'docs').as_posix(), p.read_bytes())
                        for p in sorted((ROOT / 'docs/assets').rglob('*')) if p.is_file()
                        and p.name != '.DS_Store']
    offline_entries += [('downloads/' + name, (OUT / name).read_bytes())
                        for name in (SKILL_ZIP, SAMPLE_ZIP, 'report-template.html')]
    offline_entries.append(('downloads/SHA256SUMS.txt', lines_for([SKILL_ZIP, SAMPLE_ZIP]).encode('utf-8')))
    pack(OUT / OFFLINE_ZIP, offline_entries)

    # Only remove this builder's older versioned Skill downloads, never arbitrary files.
    for p in OUT.glob('ecommerce-daily-report-v*.zip'):
        if p.name != SKILL_ZIP:
            p.unlink()
    unexpected = {p.name for p in OUT.glob('*.zip')} - EXPECTED_ZIPS
    if unexpected:
        raise ValueError(f'Unexpected ZIPs in downloads; review explicitly: {sorted(unexpected)}')
    checksums = lines_for(EXPECTED_ZIPS)
    (OUT / 'SHA256SUMS.txt').write_text(checksums, encoding='utf-8')
    print(checksums, end='')
    print(f'Built {VERSION}: Skill, synthetic example and offline experience packages.')


if __name__ == '__main__':
    main()
