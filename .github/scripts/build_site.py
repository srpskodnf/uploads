"""Builds the gallery's data and search-engine pages.

Run by GitHub Actions on every upload (see .github/workflows/gallery.yml).
Save this file in your repository as:  .github/scripts/build_site.py

It creates, inside the published site only (nothing is committed back):
  files.json        the list the gallery page reads
  view/<name>.html  one simple page per file, for search engines and sharing
  sitemap.xml       every page and image, for Google Search Console
and fills the plain list of all files into index.html.
"""
import html
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timezone
from urllib.parse import quote

SITE_URL = os.environ.get('SITE_URL', '').rstrip('/') + '/'
IMAGE_EXT = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.avif', '.bmp', '.svg'}
DOC_EXT = {'.pdf', '.doc', '.docx'}
PAGES_DIR = 'view'

if os.path.exists(PAGES_DIR):
    sys.exit(f'A folder named "{PAGES_DIR}" already exists in the repository. '
             f'Rename it, or change PAGES_DIR in this script.')


def enc(path):
    """URL-encode a path the same way the gallery page does."""
    return '/'.join(quote(part, safe="!'()*~") for part in path.split('/'))


def kind(ext):
    if ext in IMAGE_EXT:
        return 'image'
    return 'pdf' if ext == '.pdf' else 'word'


KIND_LABEL = {'image': 'Image', 'pdf': 'PDF document', 'word': 'Word document'}


def fmt_size(b):
    if b < 1024:
        return f'{b} B'
    if b < 1048576:
        return f'{b / 1024:.1f} KB' if b < 10240 else f'{b / 1024:.0f} KB'
    return f'{b / 1048576:.1f} MB'


def fmt_date(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime('%-d %B %Y') if t else ''


def iso_date(t):
    return datetime.fromtimestamp(t or time.time(), timezone.utc).strftime('%Y-%m-%d')


def readable(name):
    """'blue_sky-2019.png' -> 'blue sky 2019' (used for alt text and titles)."""
    stem = os.path.splitext(name)[0]
    return re.sub(r'[_\-]+', ' ', stem).strip() or stem


def slugify(path):
    s = unicodedata.normalize('NFKD', path).encode('ascii', 'ignore').decode().lower()
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s or 'file'


# ---------------------------------------------------------------- find files
paths = []
for root, dirs, names in os.walk('.'):
    dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
    for name in names:
        if os.path.splitext(name)[1].lower() in IMAGE_EXT | DOC_EXT:
            paths.append(os.path.relpath(os.path.join(root, name), '.').replace(os.sep, '/'))
paths.sort(key=str.lower)

# When was each file added? (git log lists newest first, so keep the first one seen)
log = subprocess.run(
    ['git', '-c', 'core.quotepath=off', 'log', '--no-renames', '--diff-filter=A',
     '--name-only', '--format=%x01%ct'],
    capture_output=True, text=True, check=True).stdout
added, stamp = {}, 0
for line in log.splitlines():
    if line.startswith('\x01'):
        stamp = int(line[1:])
    elif line:
        added.setdefault(line, stamp)

files, used = [], set()
for p in paths:
    slug = base = slugify(p)
    n = 2
    while slug in used:
        slug, n = f'{base}-{n}', n + 1
    used.add(slug)
    ext = os.path.splitext(p)[1].lower()
    files.append({
        'p': p,
        's': os.path.getsize(p),
        't': added.get(p, 0),
        'u': f'{PAGES_DIR}/{slug}.html',
        'k': kind(ext),
    })

# ---------------------------------------------------------------- site title
index_src = open('index.html', encoding='utf-8').read()
m = re.search(r'<title>(.*?)</title>', index_src, re.S)
site_title = html.unescape(m.group(1).strip()) if m else 'Files'

# ---------------------------------------------------------------- files.json
with open('files.json', 'w', encoding='utf-8') as f:
    json.dump({'generated': int(time.time()), 'count': len(files),
               'files': [{k: x[k] for k in ('p', 's', 't', 'u')} for x in files]},
              f, ensure_ascii=False, separators=(',', ':'))

# ---------------------------------------------------------------- one page per file
PAGE_CSS = """
:root{--paper:#ECEFF2;--surface:#fff;--well:#E1E6EB;--ink:#18212C;--muted:#5E6A78;--line:#CBD3DC;--accent:#245E7A;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--paper:#12161B;--surface:#1B2128;--well:#232A33;--ink:#E4E9EE;--muted:#97A3B0;--line:#2F3843;--accent:#7DB6D2;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.5 "Atkinson Hyperlegible",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:900px;margin:0 auto;padding:24px clamp(12px,3vw,32px) 64px}
a{color:var(--accent)}.back{font-size:.95rem}
h1{font-size:1.4rem;margin:16px 0 4px;overflow-wrap:anywhere}
.meta{color:var(--muted);font-size:.9rem;margin:0 0 16px}
.stage{background:var(--well);border:1px solid var(--line);border-radius:10px;padding:20px;display:grid;place-items:center;min-height:160px}
.stage img{max-width:100%;max-height:70vh;display:block}
.dl{font-size:1.1rem;font-weight:700}
dl{display:grid;grid-template-columns:8em 1fr;gap:8px 12px;margin:20px 0}
dt{color:var(--muted);font-size:.9rem}dd{margin:0;min-width:0}
code{font:.85rem/1.4 ui-monospace,Consolas,"Courier New",monospace;background:var(--surface);border:1px solid var(--line);border-radius:6px;padding:.3em .5em;display:block;overflow-x:auto;white-space:nowrap}
nav.pn{display:flex;justify-content:space-between;gap:16px;border-top:1px solid var(--line);padding-top:16px;font-size:.9rem}
nav.pn a{overflow-wrap:anywhere;max-width:48%}
@media (max-width:560px){dl{grid-template-columns:1fr}}
"""

os.makedirs(PAGES_DIR, exist_ok=True)
for i, f in enumerate(files):
    p, name = f['p'], f['p'].rsplit('/', 1)[-1]
    folder = p.rsplit('/', 1)[0] if '/' in p else ''
    file_abs = SITE_URL + enc(p)
    page_abs = SITE_URL + f['u']
    rel_file = '../' + enc(p)
    e = html.escape
    desc_parts = [f"{name}: {KIND_LABEL[f['k']].lower()}, {fmt_size(f['s'])}"]
    if folder:
        desc_parts.append(f'in folder {folder}')
    desc = ', '.join(desc_parts) + f'. Part of {site_title}.'

    meta = [KIND_LABEL[f['k']], fmt_size(f['s'])]
    if f['t']:
        meta.append('Added ' + fmt_date(f['t']))
    if folder:
        meta.append('Folder: ' + folder)

    if f['k'] == 'image':
        stage = f'<img src="{e(rel_file)}" alt="{e(readable(name))}">'
        forum = f'[img]{file_abs}[/img]'
        og_img = f'<meta property="og:image" content="{e(file_abs)}">\n'
    else:
        label = 'Open the PDF' if f['k'] == 'pdf' else 'Download the Word file'
        stage = f'<a class="dl" href="{e(rel_file)}">{label}</a>'
        forum = f'[url={file_abs}]{name}[/url]'
        og_img = ''

    prev_link = next_link = '<span></span>'
    if i > 0:
        q = files[i - 1]
        prev_link = f'<a rel="prev" href="../{e(q["u"])}">← {e(q["p"].rsplit("/", 1)[-1])}</a>'
    if i < len(files) - 1:
        q = files[i + 1]
        next_link = f'<a rel="next" href="../{e(q["u"])}">{e(q["p"].rsplit("/", 1)[-1])} →</a>'

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(name)} | {e(site_title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(page_abs)}">
<meta property="og:title" content="{e(name)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(page_abs)}">
<meta property="og:type" content="website">
{og_img}<style>{PAGE_CSS}</style>
</head>
<body>
<main>
<a class="back" href="../#{e(quote(p, safe=''))}">← All files in {e(site_title)}</a>
<h1>{e(name)}</h1>
<p class="meta">{e(', '.join(meta))}</p>
<div class="stage">{stage}</div>
<dl>
<dt>Direct link</dt><dd><code>{e(file_abs)}</code></dd>
<dt>Forum code</dt><dd><code>{e(forum)}</code></dd>
</dl>
<nav class="pn" aria-label="Neighbouring files">{prev_link}{next_link}</nav>
</main>
</body>
</html>
"""
    with open(f['u'], 'w', encoding='utf-8') as out:
        out.write(page)

# ---------------------------------------------------------------- sitemap.xml
x = html.escape
rows = [f'<url><loc>{x(SITE_URL)}</loc><lastmod>{iso_date(None)}</lastmod></url>']
for f in files:
    loc = SITE_URL + f['u']
    file_abs = SITE_URL + enc(f['p'])
    entry = f'<url><loc>{x(loc)}</loc><lastmod>{iso_date(f["t"])}</lastmod>'
    if f['k'] == 'image':
        entry += f'<image:image><image:loc>{x(file_abs)}</image:loc></image:image>'
    entry += '</url>'
    rows.append(entry)
    if f['k'] != 'image':
        rows.append(f'<url><loc>{x(file_abs)}</loc><lastmod>{iso_date(f["t"])}</lastmod></url>')
with open('sitemap.xml', 'w', encoding='utf-8') as out:
    out.write('<?xml version="1.0" encoding="UTF-8"?>\n'
              '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
              'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n'
              + '\n'.join(rows) + '\n</urlset>\n')

# ---------------------------------------------------------------- plain list in index.html
items = '\n'.join(
    f'<li><a href="{html.escape(f["u"])}">{html.escape(f["p"])}</a></li>' for f in files)
if '<!-- FILE_LIST -->' in index_src:
    with open('index.html', 'w', encoding='utf-8') as out:
        out.write(index_src.replace('<!-- FILE_LIST -->', items))

print(f'Built {len(files)} file pages, sitemap.xml and files.json for {SITE_URL}')
