#!/usr/bin/env python3
"""Review new INSPIRE literature records against the manually curated LaTeX publication lists.

This is intentionally read-only: it never edits main.tex or collaborative_publications.tex.
Use --from-json to test with a previously saved INSPIRE JSON search response offline.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

API = 'https://inspirehep.net/api/literature'
DEFAULT_QUERY = 'a Seikh, Mohammad Ful Hossain'


def canonical(s):
    return re.sub(r'[^a-z0-9]+', '', str(s).lower())


def tex_record_ids(root):
    texts = '\n'.join((root / name).read_text(encoding='utf-8') for name in ('main.tex', 'collaborative_publications.tex'))
    dois = {canonical(x) for x in re.findall(r'\\doi\{([^}]+)\}', texts)}
    dois.update(canonical(x) for x in re.findall(r'https://doi\.org/([^}\s]+)', texts))
    eprints = {canonical(x) for x in re.findall(r'\\arxiv\{([^}]+)\}', texts)}
    titles = {canonical(x) for x in re.findall(r"``(.*?)''", texts, flags=re.DOTALL)}
    return dois, eprints, titles


def get_json(url):
    # Do not follow API pagination to unrelated domains.
    if urlparse(url).scheme != 'https' or urlparse(url).netloc != 'inspirehep.net':
        raise ValueError(f'Refusing unexpected URL: {url}')
    req = Request(url, headers={'Accept': 'application/json', 'User-Agent': 'PersonalPublicationsChecker/1.0'})
    for attempt in range(3):
        try:
            with urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except HTTPError as ex:
            if ex.code != 429 or attempt == 2:
                raise
            time.sleep(6 * (attempt + 1))


def collect(query, max_records):
    url = API + '?' + urlencode({'q': query, 'sort': 'mostrecent', 'size': min(100, max_records)})
    records = []
    while url and len(records) < max_records:
        payload = get_json(url)
        hits = payload.get('hits', {}).get('hits', [])
        if not isinstance(hits, list):
            raise ValueError('Unexpected INSPIRE response: missing hits.hits')
        records.extend(hits)
        url = payload.get('links', {}).get('next') if hits else None
        if url and len(records) < max_records:
            time.sleep(0.5)
    return records[:max_records]


def date_year(metadata):
    for field in ('earliest_date', 'preprint_date', 'imprints'):
        val = metadata.get(field)
        if isinstance(val, str):
            return val[:4]
    info = metadata.get('publication_info', [])
    if isinstance(info, list) and info and isinstance(info[0], dict):
        return str(info[0].get('year', ''))
    return ''


def rec_data(rec):
    md = rec.get('metadata', rec)
    doi_values = [x.get('value', '') for x in md.get('dois', []) if isinstance(x, dict)]
    arxiv_values = [x.get('value', '') for x in md.get('arxiv_eprints', []) if isinstance(x, dict)]
    titles = [x.get('title', '') for x in md.get('titles', []) if isinstance(x, dict)]
    recid = rec.get('id', rec.get('recid', ''))
    link = f'https://inspirehep.net/literature/{recid}' if recid else ''
    return {'title': titles[0] if titles else '(untitled)', 'year': date_year(md), 'doi':doi_values, 'arxiv':arxiv_values, 'url':link}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--query', default=DEFAULT_QUERY, help='INSPIRE author query (check against your author page)')
    parser.add_argument('--max-records', type=int, default=500, help='Maximum INSPIRE hits to inspect (default 500)')
    parser.add_argument('--from-json', type=Path, help='Read a saved INSPIRE API JSON response instead of querying online')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, default=Path('inspire_candidates.md'))
    args = parser.parse_args()
    if args.max_records < 1:
        parser.error('--max-records must be positive')
    dois, arxiv, titles = tex_record_ids(args.root)
    try:
        if args.from_json:
            payload = json.loads(args.from_json.read_text(encoding='utf-8'))
            records = payload.get('hits', {}).get('hits', payload if isinstance(payload, list) else [])
        else:
            records = collect(args.query, args.max_records)
    except (OSError, ValueError, HTTPError, URLError, json.JSONDecodeError) as ex:
        print(f'INSPIRE query failed: {ex}', file=sys.stderr)
        return 1
    candidates = []
    for raw in records:
        data = rec_data(raw)
        known = (any(canonical(d) in dois for d in data['doi'])
                 or any(canonical(a) in arxiv for a in data['arxiv'])
                 or canonical(data['title']) in titles)
        if not known:
            candidates.append(data)
    lines = [
        '# INSPIRE candidates for manual review', '',
        f'- Query: `{args.query}`', f'- INSPIRE records inspected: {len(records)}',
        f'- Entries not identified in the LaTeX lists: {len(candidates)}', '',
        'These are **candidates**, not confirmed missing publications. Large-collaboration',
        'attribution, duplicate editions, and INSPIRE author matching require human checks.',
        'Do not add or remove entries without verifying authorship, status, dates, and DOI.', ''
    ]
    for data in candidates:
        lines.append(f"- **{data['year'] or '?'}**: {data['title']}" )
        lines.append(f"  DOI: {', '.join(data['doi']) or 'none'} | arXiv: {', '.join(data['arxiv']) or 'none'} | {data['url']}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'Scanned {len(records)} INSPIRE records; {len(candidates)} candidates -> {args.output}')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
