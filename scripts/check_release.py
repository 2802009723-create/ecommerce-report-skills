"""Check the actual public downloads, offline links and synthetic arithmetic. No network."""
from pathlib import Path, PurePosixPath
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit
from decimal import Decimal
import csv
import hashlib
import importlib.util
import json
import posixpath
import re
import sys
import zipfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills/ecommerce-daily-report'
OUT = ROOT / 'docs/downloads'
VERSION = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
SKILL_ZIP = f'ecommerce-daily-report-v{VERSION}.zip'
SAMPLE_ZIP = 'sample-tables-and-report.zip'
OFFLINE_ZIP = 'ecommerce-report-offline.zip'
CHECKS = []


def require(condition, message):
    if not condition:
        raise ValueError(message)


def passed(message):
    CHECKS.append(message)
    print('PASS: ' + message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Document(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.payloads = {}
        self.capture = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for key in ('href', 'src'):
            if a.get(key):
                self.links.append(a[key])
        if tag == 'script' and a.get('type') == 'application/json' and a.get('id'):
            self.capture = a['id']
            self.payloads[self.capture] = ''

    def handle_data(self, data):
        if self.capture:
            self.payloads[self.capture] += data

    def handle_endtag(self, tag):
        if tag == 'script':
            self.capture = None


def html_links(name, raw, available):
    doc = Document()
    doc.feed(raw.decode('utf-8'))
    for link in doc.links:
        url = urlsplit(link)
        if url.scheme or url.netloc or not url.path:
            continue
        require(not url.path.startswith('/'), f'{name}: root-relative link fails under project Pages: {link}')
        target = posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(url.path)))
        if target.endswith('/'):
            target += 'index.html'
        require(not target.startswith('../') and target in available, f'{name}: broken local link {link}')
    return doc


def parse_checksums(text):
    rows = {}
    for line in text.splitlines():
        parts = line.split('  ')
        require(len(parts) == 2 and re.fullmatch(r'[a-f0-9]{64}', parts[0]), 'Invalid checksum line')
        digest, name = parts
        require(name not in rows and '/' not in name and '\\' not in name, 'Invalid or duplicate checksum filename')
        rows[name] = digest
    return rows


def check_skill():
    require(re.fullmatch(r'\d+\.\d+\.\d+', VERSION), 'VERSION must be a semantic version')
    roles = sorted((SKILL / 'references/roles').glob('AG*.md'))
    require([p.stem for p in roles] == [f'AG{i:02}' for i in range(1, 24)], 'Expected AG01 through AG23')
    require(len(list((SKILL / 'references/report-types').glob('*.md'))) == 10, 'Expected 10 report types')
    manifest = json.loads((SKILL / 'package-manifest.json').read_text(encoding='utf-8'))
    require(manifest['version'] == VERSION and manifest['role_count'] == 23 and manifest['report_type_count'] == 10,
            'Package manifest counts/version differ from source')
    role_manifest = json.loads((SKILL / 'references/role-manifest.json').read_text(encoding='utf-8'))
    require(role_manifest['version'] == VERSION, 'Role manifest version differs from release')
    skill_md = (SKILL / 'SKILL.md').read_text(encoding='utf-8')
    require(re.search(r'^version:\s*["\x27]?' + re.escape(VERSION) + r'["\x27]?\s*$', skill_md, re.M), 'SKILL version differs')
    files = {p.relative_to(SKILL).as_posix(): p for p in SKILL.rglob('*') if p.is_file()
             and p.name != 'package-manifest.json' and p.name != '.DS_Store'
             and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    require(set(files) == set(manifest['files_sha256']), 'Manifest file list is incomplete or stale')
    for name, p in files.items():
        require(not p.is_symlink(), f'Symlink in skill: {name}')
        require(sha(p.read_bytes()) == manifest['files_sha256'][name], f'Stale manifest hash: {name}')
        if p.suffix == '.md':
            for href in re.findall(r'\[[^\]]*\]\(([^)]+)\)', p.read_text(encoding='utf-8')):
                url = urlsplit(href)
                if url.scheme or url.netloc or not url.path:
                    continue
                target = (p.parent / unquote(url.path)).resolve()
                require(target.is_relative_to(SKILL.resolve()) if hasattr(target, 'is_relative_to') else str(target).startswith(str(SKILL.resolve()) + '/'), f'Reference escapes skill: {href}')
                require(target.exists(), f'Missing skill reference in {name}: {href}')
    with zipfile.ZipFile(OUT / SKILL_ZIP) as archive:
        prefix = 'ecommerce-daily-report/'
        expected = {prefix + name for name in files} | {prefix + 'package-manifest.json'}
        require(set(archive.namelist()) == expected, 'Skill ZIP differs from the source file list')
        for name in expected:
            require(archive.read(name) == (SKILL / name[len(prefix):]).read_bytes(), f'Skill ZIP content differs: {name}')
    passed(f'{VERSION}: 23 role files, 10 report types, all local references and exact manifest/ZIP parity')


def check_archives():
    expected = {SKILL_ZIP, SAMPLE_ZIP, OFFLINE_ZIP}
    require({p.name for p in OUT.glob('*.zip')} == expected, 'Downloads include stale or unexpected ZIP versions')
    sums = parse_checksums((OUT / 'SHA256SUMS.txt').read_text(encoding='utf-8'))
    require(set(sums) == expected, 'Public checksum list differs from the three ZIP downloads')
    for filename in sorted(expected):
        raw = (OUT / filename).read_bytes()
        require(sha(raw) == sums[filename], f'Checksum mismatch: {filename}')
        with zipfile.ZipFile(OUT / filename) as archive:
            names = set(archive.namelist())
            require(len(names) == len(archive.namelist()) and archive.testzip() is None, f'ZIP corrupt/duplicate: {filename}')
            for info in archive.infolist():
                n = info.filename
                require(not n.startswith('/') and '..' not in PurePosixPath(n).parts and '\\' not in n and '.DS_Store' not in n,
                        f'Unsafe or local-only ZIP entry: {filename}/{n}')
                require(not any(ord(c) > 127 for c in n) or bool(info.flag_bits & 0x800), f'ZIP Chinese filename is not UTF-8: {n}')
                if n.endswith('.html'):
                    html_links(n, archive.read(n), names)
            if filename == OFFLINE_ZIP:
                for n in ('index.html', 'generator.html', 'demo.html', 'install.html', 'roles.html', 'validation.html', 'downloads/report-template.html'):
                    require(n in names, f'Offline experience missing {n}')
                local_sums = parse_checksums(archive.read('downloads/SHA256SUMS.txt').decode('utf-8'))
                require(set(local_sums) == {SKILL_ZIP, SAMPLE_ZIP}, 'Offline checksums must cover the two included child ZIPs')
                for n, digest in local_sums.items():
                    nested = archive.read('downloads/' + n)
                    require(sha(nested) == digest and nested == (OUT / n).read_bytes(), f'Offline nested package mismatch: {n}')
                require(archive.read('downloads/report-template.html') == (OUT / 'report-template.html').read_bytes(), 'Offline template differs')
            if filename == SAMPLE_ZIP:
                for p in (ROOT / 'examples/sales-inventory/input').glob('*.csv'):
                    require(archive.read('input/' + p.name) == p.read_bytes(), 'Sample ZIP CSV differs')
                require('python3 examples/sales-inventory/reproduce.py' not in archive.read('README.md').decode('utf-8'), 'Sample pack advertises absent script')
        passed(f'{filename}: integrity, SHA-256, UTF-8 paths, all packaged HTML links')
    require((OUT / 'report-template.html').read_bytes() == (SKILL / 'assets/report-template.html').read_bytes(), 'Downloadable template differs from Skill template')
    passed('Offline nested packages and downloadable template match the source')


def check_web_and_public_files():
    docs = ROOT / 'docs'
    available = {p.relative_to(docs).as_posix() for p in docs.rglob('*') if p.is_file()}
    for p in docs.rglob('*.html'):
        html_links(p.relative_to(docs).as_posix(), p.read_bytes(), available)
    private_patterns = [r'/Users/[A-Za-z0-9_\-]+/', r'gh[pousr]_[A-Za-z0-9]{25,}',
                        r'github_pat_[A-Za-z0-9_]{30,}', r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----']
    for p in ROOT.rglob('*'):
        if not p.is_file() or '.git' in p.parts or 'generated' in p.parts:
            continue
        require(p.name != '.DS_Store', f'Local metadata file in release: {p.relative_to(ROOT)}')
        if p.suffix in ('.md', '.html', '.txt', '.json', '.py', '.yml', '.yaml'):
            text = p.read_text(encoding='utf-8')
            require(not any(re.search(pattern, text) for pattern in private_patterns), f'Private-data pattern in {p.relative_to(ROOT)}')
    passed('All public HTML relative links resolve; UTF-8 text and common local-path/credential patterns checked')


def check_example():
    example = ROOT / 'examples/sales-inventory/input'
    with (example / '销售.csv').open(encoding='utf-8-sig', newline='') as f:
        sales = list(csv.DictReader(f))
    with (example / '库存.csv').open(encoding='utf-8-sig', newline='') as f:
        stock = list(csv.DictReader(f))
    doc = Document()
    doc.feed((ROOT / 'docs/demo.html').read_text(encoding='utf-8'))
    data = json.loads(doc.payloads['report-data'])
    spec = importlib.util.spec_from_file_location('release_render', SKILL / 'scripts/render_report.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.validate(data)
    modules = {m['id']: m for m in data['modules']}
    require(set(modules) == {'sales', 'inventory', 'replenishment'}, 'Synthetic example module set changed')
    total = lambda rows, key: float(sum((Decimal(r[key]) for r in rows), Decimal(0)))
    expected_totals = [total(sales, k) for k in ('支付金额_元', '支付件数', '当日发生退款金额_元')]
    require(expected_totals == [3750, 45, 100], 'Synthetic fixture differs from the documented answer')
    require([m['value'] for m in modules['sales']['metrics']] == expected_totals, 'Sales metric mismatch')
    dates = sorted({r['日期'] for r in sales})
    skus = sorted({r['SKU'] for r in sales})
    require(len(sales) == 6 and len(stock) == 2 and len(dates) == 3, 'Synthetic row/period coverage mismatch')
    for chart in modules['sales']['charts']:
        key = '日期' if chart['kind'] == 'line' else 'SKU'
        expected_labels = dates if key == '日期' else skus
        require(chart['labels'] == expected_labels, 'Sales chart labels/coverage mismatch')
        expected_values = [total([r for r in sales if r[key] == label], '支付金额_元') for label in expected_labels]
        require(len(chart['series']) == 1 and chart['series'][0]['values'] == expected_values, 'Sales chart values mismatch')
    inventory = {r['SKU']: float(Decimal(r['可售数量'])) for r in stock}
    expected_inventory = [sum(inventory.values())] + [inventory[s] for s in skus]
    require([m['value'] for m in modules['inventory']['metrics']] == expected_inventory, 'Inventory metric mismatch')
    inv_chart = modules['inventory']['charts'][0]
    require(inv_chart['labels'] == skus and inv_chart['series'][0]['values'] == [inventory[s] for s in skus], 'Inventory chart mismatch')
    averages = {s: total([r for r in sales if r['SKU'] == s], '支付件数') / len(dates) for s in skus}
    coverage = {s: inventory[s] / averages[s] for s in skus}
    replenishment = modules['replenishment']
    require([m['value'] for m in replenishment['metrics']] == [coverage[s] for s in skus] + [None], 'Coverage metric/purchase null mismatch')
    cov_chart = replenishment['charts'][0]
    require(cov_chart['labels'] == skus and cov_chart['series'][0]['values'] == [coverage[s] for s in skus], 'Coverage chart mismatch')
    table = replenishment['charts'][1]
    require(table['kind'] == 'table' and [r['name'] for r in table['rows']] == skus, 'Replenishment table coverage mismatch')
    for row in table['rows']:
        s = row['name']
        require(row['daily'] == averages[s] and row['available'] == inventory[s] and row['purchase'] == '待确认', 'Table cell mismatch')
    sources = {s['file']: s for s in data['sources']}
    for filename, end in [('销售.csv', 'A1:G7'), ('库存.csv', 'A1:E3')]:
        source = sources[filename]
        require(source['range'] == end and sha((example / filename).read_bytes()) in source['version'], 'Source range/hash differs from sample')
    require(data['report']['status'] == 'partial' and all(m['status'] == 'partial' for m in modules.values()), 'Missing parameters must remain partial')
    passed('Synthetic CSV independently recomputed: all 9 metrics, 4 numerical charts, table cells, source ranges/hashes and unknown purchase quantity')


def main():
    check_skill()
    check_archives()
    check_web_and_public_files()
    check_example()
    print(f'\nRelease {VERSION}: {len(CHECKS)} verification groups passed. Browser/WorkBuddy execution is checked separately.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, zipfile.BadZipFile) as error:
        raise SystemExit('FAIL: ' + str(error))
