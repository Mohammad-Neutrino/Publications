#!/usr/bin/env python3
"""Sync an INSPIRE-HEP Cite-All BibTeX export into a curated publication list.

Read-only by default. With --apply, updates main.tex, collaborative_publications.tex,
and (optionally) INSPIRE-CiteAll.bib after validation. Python 3.9+, stdlib only.

The current CV is fetched by default directly from the public CV GitHub repository
(trunk/cv.tex) for lead-analysis preprints and selected collaborative works.
Use --cv only to override with a local CV. An inaccessible GitHub CV causes the
sync to stop rather than silently use stale classifications.

Example:
  python3 scripts/sync_inspire.py ~/Downloads/INSPIRE-CiteAll.bib
  python3 scripts/sync_inspire.py ~/Downloads/INSPIRE-CiteAll.bib --apply
"""
import argparse
import difflib
import html
import re
import sys
import unicodedata
import shutil
import tempfile
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

MAIN = 'main.tex'
COLLAB = 'collaborative_publications.tex'
BIB_SNAPSHOT = 'INSPIRE-CiteAll.bib'
HEADINGS = {
    'ARA': 'Askaryan Radio Array (ARA) Collaboration',
    'RNO-G': 'Radio Neutrino Observatory in Greenland (RNO-G) Collaboration',
    'IceCube': 'IceCube Neutrino Observatory (IceCube) Collaboration',
    'IceCube-Gen2': 'IceCube-Gen2 Collaboration',
    'PUEO': 'Payload for Ultrahigh Energy Observations (PUEO) Collaboration',
    'RET': 'Radar Echo Telescope (RET) Collaboration',
    'TAROGE': 'TAROGE-M / ARIANNA Collaboration',
    'Joint': 'Joint / Multi-Collaborations',
    'Other': 'Other Multi-Institution Publications',
}
PROCEEDINGS = 'Conference Proceedings'
JOURNALS = 'Peer-Reviewed Journal Articles'
PREPRINTS = 'Preprints and Manuscripts'
CV_LEAD = 'Preprints and Submitted Manuscripts (Core Analysis Team)'
CV_URL = 'https://raw.githubusercontent.com/Mohammad-Neutrino/CV/trunk/cv.tex'

# Reviewed INSPIRE exceptions. These refer to distinct scholarly records or
# harmless title variants already checked against the existing publication list.
COLLABORATION_OVERRIDES = {'2610.20163': 'IceCube'}
VERIFIED_TITLE_VARIANTS = {'2103.06079', '2304.06181', '2308.07292'}
# Same title, but distinct proceedings and full papers. Both must be retained.
VERIFIED_DISTINCT_PAIRS = (
    frozenset(('2610.20163', '10.22323/1.501.1145')),
    frozenset(('10.1017/jog.2026.10133', '10.22323/1.501.1121')),
)



def norm(value):
    value = html.unescape(str(value or ''))
    value = value.replace(r'\&', '&').replace(r'\-', '-').replace(r'\textendash', '-')
    value = re.sub(r'\\[a-zA-Z]+', '', value)
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().lower()
    return re.sub('[^a-z0-9]', '', value)


def identifier(value):
    return re.sub(r'\s+', '', str(value or '')).lower().rstrip('.,;')


def download_cv(url=CV_URL):
    # Public, read-only GitHub source. Never write or alter the CV repository.
    req = Request(url, headers={'User-Agent': 'INSPIRE-Publications-Sync/1.0'})
    with urlopen(req, timeout=20) as resp:
        data = resp.read(250_000)
    return data.decode('utf-8')


def tex_title(value):
    # The BibTeX export contains LaTeX-formatted titles. Preserve TeX mathematics,
    # but avoid guessing how to render uncommon macros or nested TeX commands.
    value = re.sub(r'(?<!\\)[{}]', '', value).strip()
    value = value.replace('&', r'\&').replace('%', r'\%').replace('#', r'\#')
    return re.sub(r'\s+', ' ', value)


def balanced_field(s, i):
    opener = s[i]
    if opener == '{':
        depth, j = 1, i + 1
        while j < len(s):
            if s[j] == '{' and (j == 0 or s[j-1] != '\\'):
                depth += 1
            elif s[j] == '}' and (j == 0 or s[j-1] != '\\'):
                depth -= 1
                if depth == 0:
                    return s[i+1:j], j+1
            j += 1
        raise ValueError('Unterminated BibTeX braced value')
    if opener == '"':
        j = i + 1
        while j < len(s):
            if s[j] == '"' and s[j-1] != '\\':
                return s[i+1:j], j+1
            j += 1
        raise ValueError('Unterminated BibTeX quoted value')
    j = i
    while j < len(s) and s[j] not in ',\r\n}':
        j += 1
    return s[i:j].strip(), j


def parse_bib(path):
    data = path.read_text(encoding='utf-8-sig')
    out = []
    pos = 0
    while (m := re.search(r'(?m)^\s*@([A-Za-z]+)\s*\{', data[pos:])) is not None:
        kind, i = m.group(1).lower(), pos + m.end()
        key_end = data.find(',', i)
        if key_end < 0:
            raise ValueError('Malformed BibTeX entry without key: ' + data[i:i+60])
        entry_key, i = data[i:key_end].strip(), key_end+1
        fields = {}
        while True:
            while i < len(data) and data[i] in '\r\n\t ,':
                i += 1
            if i >= len(data):
                raise ValueError('Unterminated BibTeX entry ' + entry_key)
            if data[i] == '}':
                i += 1
                break
            k = re.match(r'[A-Za-z][A-Za-z0-9_-]*\s*=\s*', data[i:])
            if not k:
                raise ValueError('Unsupported BibTeX field near ' + repr(data[i:i+70]) + ' in ' + entry_key)
            field_name = k.group(0).split('=')[0].strip().lower()
            i += k.end()
            value, i = balanced_field(data, i)
            fields[field_name] = value.strip()
        pos = i
        if kind in ('comment', 'preamble', 'string'):
            continue
        out.append(BibRecord(kind, entry_key, fields))
    if not out:
        raise ValueError('No BibTeX entries found')
    if len({r.key for r in out}) != len(out):
        raise ValueError('Repeated BibTeX citation keys')
    return out, data


@dataclass
class BibRecord:
    entry_type: str
    key: str
    fields: dict

    @property
    def title(self):
        return re.sub(r'^\{(.*)\}$', r'\1', self.fields.get('title', '').strip()).strip()

    @property
    def doi(self):
        return identifier(self.fields.get('doi', ''))

    @property
    def arxiv(self):
        return identifier(self.fields.get('eprint', '')) if self.fields.get('archiveprefix','').lower() in ('', 'arxiv') else ''

    @property
    def year(self):
        return re.search(r'20\d\d', self.fields.get('year', '') or '')[0] if re.search(r'20\d\d', self.fields.get('year', '') or '') else ''

    @property
    def category(self):
        if self.arxiv in COLLABORATION_OVERRIDES:
            return COLLABORATION_OVERRIDES[self.arxiv]
        c = self.fields.get('collaboration', '').lower()
        c = re.sub(r'\{\\[^{}]*\}', '', c)
        c = c.replace('icecube-gen2','icecubegen2')
        if ('icecube' in c and any(x in c for x in ('ligo','virgo','hawc','act','auger','h.e.s.s.','magic','fact','veritas'))) or ('icecubegen2' in c and 'auger' in c):
            return 'Joint'
        if 'icecubegen2' in c:
            return 'IceCube-Gen2'
        if 'icecube' in c:
            return 'IceCube'
        if 'rno-g' in c:
            return 'RNO-G'
        if re.search(r'\bara\b', c) or 'askaryan radio array' in c:
            return 'ARA'
        if 'pueo' in c:
            return 'PUEO'
        if 'radar echo telescope' in c or re.search(r'\bret\b', c):
            return 'RET'
        if 'taroge' in c or 'arianna' in c:
            return 'TAROGE'
        return 'Other'

    @property
    def kind(self):
        journal = self.fields.get('journal','').lower()
        if self.entry_type in ('inproceedings', 'proceedings', 'conference') or journal.startswith('pos') or self.doi.startswith('10.22323/'):
            return PROCEEDINGS
        if self.fields.get('journal') and self.fields.get('volume'):
            return JOURNALS
        return PREPRINTS

    @property
    def year_sort(self):
        # Prefer arXiv date for preprints; publication year otherwise.
        y = int(self.year or 0)
        mon = self.fields.get('month','')
        if self.arxiv and re.match(r'^\d{4}\.\d+$',self.arxiv):
            return (int('20'+self.arxiv[:2]),int(self.arxiv[2:4]),int(self.arxiv[5:]))
        return (y,int(mon) if mon.isdigit() else 0,0)


@dataclass
class Entry:
    filename: str
    start: int
    end: int
    text: str
    title: str
    dois: tuple
    arxivs: tuple
    section: str
    subsection: str
    subsubsection: str

    @property
    def kind(self):
        if 'Conference Proceedings' in self.subsection or 'Conference Proceedings' in self.subsubsection:
            return PROCEEDINGS
        if 'Journal Publications' in self.subsection or 'Journal Articles' in self.subsubsection:
            return JOURNALS
        if 'Preprints' in self.subsection or 'Manuscripts' in self.subsection or 'Preprints' in self.subsubsection:
            return PREPRINTS
        return ''


def extract_quoted_title(value):
    # Existing CV/LaTeX titles use TeX open and close quotes. An internal prime
    # such as 4'' must not be mistaken for the end of the article title.
    a=value.find('``')
    if a<0:return ''
    b=value.rfind("''")
    return value[a+2:b] if b>a+2 else ''


def ids_tex(text):
    a = tuple(identifier(x) for x in re.findall(r'\\arxiv\{([^}]+)\}', text))
    d = [identifier(x) for x in re.findall(r'\\doi\{([^}]+)\}', text)]
    d += [identifier(x) for x in re.findall(r'https?://doi\.org/([^}\s]+)', text)]
    return tuple(dict.fromkeys(d)),tuple(dict.fromkeys(a))


def parse_tex(text,filename):
    # Parse only items inside publication sections, not unrelated LaTeX list items.
    sections = list(re.finditer(r'(?m)^\\(section|subsection|subsubsection)\*?\{([^\n}]*)\}',text))
    items = list(re.finditer(r'(?m)^[ \t]*\\item[ \t]+',text))
    out=[]
    for n,m in enumerate(items):
        loc=m.start()
        past=[s for s in sections if s.start()<loc]
        sec=next((s.group(2) for s in reversed(past) if s.group(1)=='section'),'')
        sub=next((s.group(2) for s in reversed(past) if s.group(1)=='subsection'),'')
        subsub=next((s.group(2) for s in reversed(past) if s.group(1)=='subsubsection'),'')
        if filename==MAIN and sec not in ('First-Author Works and Lead Research Contributions','Selected Collaborative Works'):
            continue
        following=items[n+1].start() if n+1<len(items) else len(text)
        stop=[following]
        end_itemize=text.find(r'\end{itemize}',m.end(),following)
        if end_itemize>=0:stop.append(end_itemize)
        next_sec=next((s.start() for s in sections if m.end()<s.start()<following),None)
        if next_sec is not None:stop.append(next_sec)
        end=min(stop)
        raw=text[loc:end]
        title=extract_quoted_title(raw)
        if not title:
            continue
        doi,arxiv=ids_tex(raw)
        out.append(Entry(filename,loc,end,raw,title,doi,arxiv,sec,sub,subsub))
    return out


def entries(files):
    return [e for path,txt in files.items() for e in parse_tex(txt,path)]


def match_record(rec,all_entries):
    by_id=[e for e in all_entries if rec.arxiv and rec.arxiv in e.arxivs or rec.doi and rec.doi in e.dois]
    if by_id:
        return 'id',by_id
    by_title=[e for e in all_entries if norm(e.title)==norm(rec.title)]
    return ('title',by_title) if by_title else ('new',[])


def bib_venue(r):
    j=r.fields.get('journal','').strip()
    vol=r.fields.get('volume','').strip()
    num=r.fields.get('number','').strip()
    pages=r.fields.get('pages','').strip()
    if not j:
        return ''
    if j=='PoS' and vol and pages:
        return f'PoS({vol}){pages}'
    if vol:
        j+=' '+vol
    if num:
        j+='('+num+')'
    if pages:
        j+=', '+pages
    return j


def item_for(r, heading=''):
    title=tex_title(r.title)
    if not title or re.search(r'\\[a-zA-Z]|\$',title):
        raise ValueError('Title needs manual LaTeX rendering: '+r.title)
    head = r'\item \textit{(' + (r.year or '?') + ')}. '
    line = head + '``' + title + ".''"
    venue = bib_venue(r)
    if venue:
        line+=' '+r'\textit{' + venue.replace('&',r'\&') + '}.'
    if r.doi:
        line+=' '+r' \doi{' + r.doi + '}'
    if r.arxiv:
        line+=' '+r' \arxiv{' + r.arxiv + '}'
    return line+'\n'


def replace_entry(files,e,text):
    s=files[e.filename]
    if s[e.start:e.end]!=e.text:
        raise ValueError('Stale source range for '+e.title)
    files[e.filename]=s[:e.start]+text+s[e.end:]


def add_to_list(text,section,kind,line):
    target=r'\subsection{' + HEADINGS[section] + '}'
    s=re.search(r'(?m)^'+re.escape(target)+r'\s*$',text)
    if not s:
        raise ValueError('Collaboration subsection not found: '+target)
    end_match=re.search(r'(?m)^\\subsection\{',text[s.end():])
    end=s.end()+end_match.start() if end_match else len(text)
    segment=text[s.end():end]
    kind_head=r'\subsubsection{' + kind + '}'
    at=segment.find(kind_head)
    if at==-1:
        first=re.search(r'(?m)^\\subsubsection\{',segment)
        if first is None:
            raise ValueError('No publication category in '+target)
        insert=s.end()+first.start()
        # Journals should be before proceedings, preprints after proceedings.
        if kind==PREPRINTS:
            insert=end
            replacement=kind_head+'\n'+r'\begin{itemize}'+'\n'+line+r'\end{itemize}'+'\n'+r'\medskip'+'\n\n'
        else:
            replacement=kind_head+'\n'+r'\begin{itemize}'+'\n'+line+r'\end{itemize}'+'\n'
        return text[:insert]+replacement+text[insert:]
    # Insert before oldest entry, respecting approximate reverse chronology by year.
    start=s.end()+at+len(kind_head)
    block_start=text.find(r'\begin{itemize}',start,end)
    block_end=text.find(r'\end{itemize}',block_start,end)
    if block_start<0 or block_end<0:
        raise ValueError('Malformed '+kind+' list for '+section)
    # Reuse source style and prepend to list. Newly inserted records are sorted together.
    loc=text.find('\n',block_start)+1
    return text[:loc]+line+text[loc:]


def add_selected(main,item):
    start=main.index(r'\section{Selected Collaborative Works}')
    end=main.index(r'\section{Additional Collaborative Works}',start)
    pos=main.find(r'\begin{itemize}',start,end)
    if pos<0:raise ValueError('Selected works list missing')
    pos=main.index('\n',pos)+1
    return main[:pos]+item+main[pos:]


def cv_items(cv_text,title):
    marker=r'\subsection*{' + title + '}'
    pos=cv_text.find(marker)
    if pos<0:return []
    next_sub=re.search(r'(?m)^\\subsection\*?\{',cv_text[pos+len(marker):])
    end=pos+len(marker)+next_sub.start() if next_sub else len(cv_text)
    block=cv_text[pos:end]
    start_env=re.search(r'\\begin\{(cvpubnumbered|itemize)\}',block)
    if not start_env:raise ValueError('CV subsection has no publication list: '+title)
    env=start_env.group(1)
    end_env=block.find(r'\end{'+env+'}',start_env.end())
    if end_env<0:raise ValueError('CV publication list missing end: '+title)
    body=block[start_env.end():end_env]
    return re.findall(r'(?ms)^[ \t]*\\(?:cvnumitem|item)[ \t]+.*?(?=^[ \t]*\\(?:cvnumitem|item)\b|\Z)',body)


def cv_item_to_tex(item):
    item=item.strip()
    item=re.sub(r'^\\(?:cvnumitem|item)[ \t]+',r'\\item ',item)
    item=re.sub(r'\\cvdate\{([^}]+)\}',lambda m:r'\textit{('+m.group(1)+')}',item)
    return '    '+item.strip()+'\n'


def cv_lead_replace(main,cv_text):
    lead=cv_items(cv_text,CV_LEAD)
    if not lead:return main,False
    pat=r'(?m)^\\subsection\{(?:Manuscripts in Collaboration Review|Preprints and Submitted Manuscripts \(Core Analysis Team\))\}'
    start=re.search(pat,main)
    end=re.search(r'(?m)^\\subsection\{Refereed Journal Publications\}',main)
    if not start or not end or end.start()<=start.start():
        raise ValueError('Cannot find lead preprint section in main.tex')
    block=r'\subsection{'+CV_LEAD+'}'+'\n'+r'\begin{itemize}'+'\n'+''.join(cv_item_to_tex(x) for x in lead)+r'\end{itemize}'+'\n\n'
    updated=main[:start.start()]+block+main[end.start():]
    return updated,updated!=main


def add_main_first_author(main,heading,item):
    start = re.search(r'(?m)^' + re.escape(r'\subsection{' + heading + '}') + r'\s*$', main)
    if not start:
        raise ValueError('Main publication subsection missing: '+heading)
    after = re.search(r'(?m)^\\subsection\{',main[start.end():])
    end = start.end()+after.start() if after else len(main)
    pos = main.find(r'\begin{itemize}',start.end(),end)
    if pos < 0:
        raise ValueError('No itemize list in main subsection: '+heading)
    pos = main.index('\n',pos)+1
    return main[:pos]+item+main[pos:]


def cv_main_promote(files,cv_text,events):
    sections = {
        'Refereed Journal Publications (First Author)': 'Refereed Journal Publications',
        'Conference Proceedings (First/Lead Author)': 'Conference Proceedings',
        'Editorial and Other Scientific Writing': 'Editorial and Other Scientific Writing',
    }
    for cv_heading, main_heading in sections.items():
        # Reverse iteration preserves CV order when each item is inserted first.
        for cv_item in reversed(cv_items(cv_text,cv_heading)):
            ci = cv_item_to_tex(cv_item)
            doi,arx = ids_tex(ci)
            title = extract_quoted_title(ci)
            if not title:
                events['review'].append('CV lead entry has no parsable title: '+ci[:120])
                continue
            hits = [e for e in entries(files) if any(x in e.arxivs for x in arx) or any(x in e.dois for x in doi)]
            if not hits:
                hits = [e for e in entries(files) if norm(e.title)==norm(title)]
            if len(hits)>1:
                events['review'].append('Multiple existing locations for CV lead work: '+title)
                continue
            if hits:
                e=hits[0]
                if e.filename==MAIN:
                    continue
                replace_entry(files,e,'')
            files[MAIN]=add_main_first_author(files[MAIN],main_heading,ci)
            events['moved' if hits else 'added'].append(title+' -> main.tex / '+main_heading)


def cv_selected_promote(files,cv_text,events):
    selected=cv_items(cv_text,'Selected Collaborative Publications')
    for cv_item in reversed(selected):
        ci=cv_item_to_tex(cv_item)
        doi,arx=ids_tex(ci)
        title=extract_quoted_title(ci)
        if not title:continue
        hits=[e for e in entries(files) if any(x in e.arxivs for x in arx) or any(x in e.dois for x in doi)]
        if not hits:
            hits=[e for e in entries(files) if norm(e.title)==norm(title)]
        in_selected=[e for e in hits if e.filename==MAIN and e.section=='Selected Collaborative Works']
        if in_selected:
            if len(in_selected)>1:events['review'].append('Already duplicated selected CV work: '+title)
            continue
        if len(hits)>1:
            events['review'].append('Multiple locations for CV selection: '+title)
            continue
        if hits and hits[0].filename==MAIN:
            events['review'].append('Selected CV work already appears in lead section: '+title)
            continue
        if hits:
            replace_entry(files,hits[0],'')
        files[MAIN]=add_selected(files[MAIN],ci)
        events['moved'].append(title+' -> selected collaborative publications')


def refresh_published_venue(e, rec):
    """Update a lead/selected preprint when the journal publication is confirmed.

    Preserve the manually curated author string and entry position. Journal metadata
    must replace an existing submission note, not be appended as a second work.
    """
    if rec.kind != JOURNALS or e.filename != MAIN or e.kind != PREPRINTS:
        return e.text, []
    venue = bib_venue(rec)
    if not venue:
        return e.text, []
    # Publication metadata is authoritative for venue, but never claim publication
    # simply from the presence of a month/year or the BibTeX @article type.
    journal = r'\textit{' + tex_title(venue) + '}'
    old = e.text
    updated = re.sub(r'\\textit\{Submitted to [^{}]+\}\.?', lambda m: journal+'.', old, count=1)
    if updated == old:
        updated = re.sub(r'\\textit\{planned submission to [^{}]+\}\.?', lambda m: journal+'.', old, count=1, flags=re.IGNORECASE)
    return updated, (['journal venue: '+venue] if updated!=old else [])


def append_ids(raw,rec):
    doi,arxiv=ids_tex(raw)
    extra=[]
    if rec.doi and rec.doi not in doi:extra.append(r'\doi{'+rec.doi+'}')
    if rec.arxiv and rec.arxiv not in arxiv:extra.append(r'\arxiv{'+rec.arxiv+'}')
    if not extra:return raw,[]
    # Insert before any trailing newline. This keeps the LaTeX item boundary intact.
    return raw.rstrip()+ ' '+' '.join(extra)+'\n',extra


def strong_duplicate_issues(es):
    issues=[]
    for field in ('dois','arxivs'):
        seen=defaultdict(list)
        for e in es:
            for k in getattr(e,field):
                seen[k].append(e)
        for k,locs in seen.items():
            if len(locs)>1:
                issues.append(f'{field}={k}: '+', '.join(x.filename+': '+x.title for x in locs))
    return issues


def verified_distinct_title_pair(a,b):
    ids_a=set(a.dois+a.arxivs)
    ids_b=set(b.dois+b.arxivs)
    return any((x & ids_a) and (x & ids_b) for x in VERIFIED_DISTINCT_PAIRS)


def verified_same_proceeding(e,rec):
    # The same conference paper can have a hyperlink to its PoS page in TeX,
    # while the INSPIRE record additionally supplies its DOI.
    if e.kind!=PROCEEDINGS or rec.kind!=PROCEEDINGS or not rec.doi:
        return False
    venue=bib_venue(rec)
    return bool(venue and norm(venue) in norm(e.text))


def title_collision_warnings(es):
    """Weak, title-based collisions are flagged, never merged automatically."""
    groups = defaultdict(list)
    for e in es:
        if norm(e.title):
            groups[norm(e.title)].append(e)
    notes = []
    for rows in groups.values():
        if len(rows) < 2:
            continue
        if len(rows)==2 and verified_distinct_title_pair(rows[0],rows[1]):
            continue
        # Same title may be a distinct proceeding and a journal paper. Do not
        # delete either without user confirmation, even when they share words.
        locations = '; '.join(f'{e.filename} [{e.kind}]: {e.title}' for e in rows)
        notes.append('Same normalized title in multiple entries; verify identity: '+locations)
    return notes


def md_lines(events,records,files,originals,has_cv,mode):
    r=['# INSPIRE BibTeX synchronization','',f'- Export records: **{len(records)}**',
       f'- Source: **INSPIRE BibTeX (.bib)**',f'- CV used: **{"yes" if has_cv else "no"}**',
       f'- Mode: **{mode}**',f'- LaTeX files changed: **{sum(files[x]!=originals[x] for x in originals)}**','']
    for key,label in [('added','New publications'),('updated','Updated metadata'),('moved','Moved or promoted'),('excluded','Excluded records'),('review','Needs review')]:
        r += [f'## {label} ({len(events[key])})','']
        r += ['- '+x for x in events[key]] or ['- None']
        r.append('')
    weak = title_collision_warnings(entries(files))
    r += ['## Possible title duplicates ('+str(len(weak))+')','']
    r += ['- '+x for x in weak] or ['- None']
    r.append('')
    r += ['## Validation','', '- Duplicate DOI/arXiv check passed for the two LaTeX files.', 
          '- Source entries not matched by DOI, arXiv, or unambiguous title are not overwritten.',
          '- A matching title with different bibliographic identity is reviewed, not merged.',
          '- Existing CV lead/selected classifications are preserved.','']
    return '\n'.join(r)


def sync(records,originals,cv_text):
    files=originals.copy()
    ev={x:[] for x in ('added','updated','moved','excluded','review')}
    before_dups=strong_duplicate_issues(entries(files))
    if before_dups:
        raise ValueError('Source already has duplicate strong IDs: '+ '; '.join(before_dups[:4]))
    if cv_text:
        files[MAIN],changed=cv_lead_replace(files[MAIN],cv_text)
        if changed:ev['updated'].append('Reconciled lead-analysis manuscript entries with CV')
        cv_main_promote(files,cv_text,ev)
        cv_selected_promote(files,cv_text,ev)
    # Export is usually in newest-first order. Reversed iteration plus prepend keeps
    # added publications newest first without changing existing publication order.
    for rec in reversed(records):
        if rec.entry_type in ('phdthesis','mastersthesis','thesis','book'):
            ev['excluded'].append(rec.title+' ('+rec.entry_type+')')
            continue
        if not rec.title:
            ev['review'].append(rec.key+': missing title')
            continue
        es=entries(files)
        how,hits=match_record(rec,es)
        if how=='id':
            if len(hits)>1:
                ev['review'].append(rec.key+': multiple matches for '+rec.title)
                continue
            e=hits[0]
            if norm(e.title)!=norm(rec.title):
                # Preserve preferred titles; known title variants need no repeated review.
                if rec.arxiv not in VERIFIED_TITLE_VARIANTS:
                    ev['review'].append('Same DOI/arXiv but different title (preserved): '+rec.title+' vs '+e.title)
            # Upgrade published preprint in Additional Collaborative Works to journal.
            if e.filename==COLLAB and e.kind==PREPRINTS and rec.kind==JOURNALS:
                try:
                    fresh=item_for(rec)
                except ValueError as ex:
                    ev['review'].append(str(ex))
                    continue
                # Journal promotion must stay in the same collaboration grouping.
                section=next((k for k,v in HEADINGS.items() if v in e.subsection),None)
                if section is None:
                    ev['review'].append('Cannot find category for published preprint: '+rec.title)
                    continue
                replace_entry(files,e,'')
                files[COLLAB]=add_to_list(files[COLLAB],section,JOURNALS,fresh)
                ev['moved'].append(rec.title+': preprint -> peer-reviewed journal')
            else:
                venue_updated,venue_changes=refresh_published_venue(e,rec)
                updated,identifiers=append_ids(venue_updated,rec)
                identifiers=venue_changes+identifiers
                if identifiers:
                    replace_entry(files,e,updated)
                    ev['updated'].append(rec.title+': '+', '.join(identifiers))
            continue
        if how=='title':
            # Same title, different bibliographic identity. This may be a preprint
            # for the existing work or a distinct proceedings/journal record.
            if len(hits)>1:
                ev['review'].append('Ambiguous title shared by several entries: '+rec.title)
                continue
            e=hits[0]
            # Verified distinct conference/full-paper pair; add the newer paper
            # to the proper collaboration subsection, not as a replacement.
            paper_ids=set(filter(None,(rec.doi,rec.arxiv)))
            existing_ids=set(e.dois+e.arxivs)
            if any((x & paper_ids) and (x & existing_ids) for x in VERIFIED_DISTINCT_PAIRS):
                if rec.category=='Other':
                    ev['review'].append('Unknown collaboration for distinct record: '+rec.title)
                    continue
                try:
                    files[COLLAB]=add_to_list(files[COLLAB],rec.category,rec.kind,item_for(rec))
                    ev['added'].append(rec.title+' ('+rec.category+' / '+rec.kind+', distinct from proceeding)')
                except ValueError as ex:
                    ev['review'].append(str(ex))
                continue
            # A PoS paper with exactly the same title and conference page is
            # a strong title+venue match, even if its TeX entry lacks the DOI.
            if verified_same_proceeding(e,rec):
                updated,identifiers=append_ids(e.text,rec)
                if identifiers:
                    replace_entry(files,e,updated)
                    ev['updated'].append(rec.title+': '+', '.join(identifiers))
                continue
            if rec.kind==PROCEEDINGS and e.kind!=PROCEEDINGS or rec.kind==JOURNALS and e.kind==PROCEEDINGS or rec.kind==PREPRINTS and e.kind==PROCEEDINGS:
                ev['review'].append('Distinct proceedings/article possible; review: '+rec.title+' ('+rec.key+')')
                continue
            if not rec.doi and not rec.arxiv:
                # No identifier and exact title: do not treat as new.
                continue
            # Existing first-author main preprint with same title can gain arXiv ID.
            if e.filename==MAIN and ('Preprints' in e.subsection or 'Manuscripts' in e.subsection) and not cv_text:
                upd,newids=append_ids(e.text,rec)
                if newids:
                    replace_entry(files,e,upd)
                    ev['updated'].append(rec.title+': '+', '.join(newids))
                continue
            # Other exact-title matches with different IDs are not safely mergeable.
            ev['review'].append('Title-only match, verify identity before adding: '+rec.title+' ('+rec.key+')')
            continue
        if not rec.doi and not rec.arxiv:
            ev['review'].append('New record without DOI or arXiv: '+rec.title)
            continue
        if rec.category=='Other':
            ev['review'].append('Unknown collaboration or multi-institution authorship: '+rec.title)
            continue
        if not cv_text and rec.category=='ARA' and ('first array' in rec.title.lower() or 'analysis methodology' in rec.title.lower()):
            ev['review'].append('Potential core ARA lead paper: '+rec.title+' (supply --cv)')
            continue
        try:
            row=item_for(rec)
            files[COLLAB]=add_to_list(files[COLLAB],rec.category,rec.kind,row)
            ev['added'].append(rec.title+' ('+rec.category+' / '+rec.kind+')')
        except ValueError as ex:
            ev['review'].append(str(ex))
    after_dups=strong_duplicate_issues(entries(files))
    if after_dups:
        raise ValueError('Refusing duplicate DOI/arXiv output: '+ '; '.join(after_dups[:6]))
    return files,ev


def update_readme(readme, main):
    """Keep the descriptive selected-paper count in README aligned with main.tex."""
    try:
        n = len([e for e in parse_tex(main, MAIN) if e.section=='Selected Collaborative Works'])
    except ValueError:
        return readme
    readme = re.sub(r'(a curated selection of )\d+( collaborative publications)', lambda m: m.group(1)+str(n)+m.group(2), readme, count=1)
    readme = readme.replace('manuscripts in collaboration review, refereed journal articles', 'preprints and submitted manuscripts, refereed journal articles')
    readme = readme.replace('Manuscripts in collaboration review are identified separately from published papers; their status and intended venues are subject to change.', 'Preprints and submitted manuscripts are identified separately from published papers; submission does not imply acceptance.')
    return readme


def main():
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('bib',type=Path,nargs='?',help='Complete INSPIRE Cite-All .bib export')
    parser.add_argument('--bib',dest='bib_option',type=Path,help='Alternative to the positional BibTeX file argument')
    parser.add_argument('--root',type=Path,default=Path('.'),help='Publications repository directory (default: .)')
    parser.add_argument('--cv',type=Path,help='Optional local cv.tex override; by default fetches the latest CV from GitHub trunk')
    parser.add_argument('--offline',action='store_true',help='Do not fetch CV from GitHub; permits a preview without CV unless --cv is supplied')
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run',action='store_true',help='Preview without writing source files (default)')
    mode.add_argument('--apply',action='store_true',help='Write validated LaTeX files and refresh bibliography snapshot')
    parser.add_argument('--report',type=Path,default=Path('inspire_sync_report.md'),help='Output report (default: inspire_sync_report.md)')
    parser.add_argument('--diff',type=Path,default=Path('inspire_sync.diff'),help='Preview diff file (default: inspire_sync.diff)')
    parser.add_argument('--no-bib-copy',action='store_true',help='Do not copy the export over INSPIRE-CiteAll.bib during --apply')
    args=parser.parse_args()
    try:
        root=args.root.resolve()
        args.bib=args.bib_option or args.bib
        if args.bib is None:raise ValueError('Provide the INSPIRE BibTeX file as a positional path or with --bib')
        if not args.bib.exists():raise FileNotFoundError(args.bib)
        if args.cv:
            if not args.cv.exists():
                raise FileNotFoundError(f'CV file not found: {args.cv}')
            cv_text=args.cv.read_text(encoding='utf-8')
            cv_source=str(args.cv)
        elif args.offline:
            cv_text=None
            cv_source='offline, no CV supplied'
        else:
            try:
                cv_text=download_cv()
                cv_source=CV_URL
            except (URLError, HTTPError, TimeoutError, UnicodeError) as ex:
                raise ValueError(f'Could not download current CV from GitHub ({ex}); check internet access or pass --cv /path/to/cv.tex') from ex
        if args.apply and cv_text is None:
            raise ValueError('A current CV is required for --apply. Use the default GitHub fetch or explicitly pass --cv /path/to/cv.tex.')
        records,bib_data=parse_bib(args.bib)
        originals={p:(root/p).read_text(encoding='utf-8') for p in (MAIN,COLLAB)}
        files,ev=sync(records,originals,cv_text)
        if (root/'README.md').exists():
            originals['README.md']=(root/'README.md').read_text(encoding='utf-8')
            files['README.md']=update_readme(originals['README.md'], files[MAIN])
        report=md_lines(ev,records,files,originals,cv_text is not None,'APPLY' if args.apply else 'DRY RUN')
        args.report.write_text(report,encoding='utf-8')
        diff=''
        for filename in (MAIN,COLLAB,'README.md'):
            if filename in files and files[filename]!=originals[filename]:
                diff+=''.join(difflib.unified_diff(originals[filename].splitlines(keepends=True),files[filename].splitlines(keepends=True),fromfile='a/'+filename,tofile='b/'+filename))
        args.diff.write_text(diff,encoding='utf-8')
        if args.apply:
            for filename in (MAIN,COLLAB,'README.md'):
                if filename in files and files[filename]!=originals[filename]:
                    (root/filename).write_text(files[filename],encoding='utf-8')
            if not args.no_bib_copy:
                (root/BIB_SNAPSHOT).write_text(bib_data,encoding='utf-8')
        for name in ('added','updated','moved','excluded','review'):
            print(f'{name.title()}: {len(ev[name])}',end='  ')
        print()
        print(('Updated repository files' if args.apply else 'Dry run; source files unchanged')+f'. Report: {args.report}  Diff: {args.diff}')
        print('CV source: '+cv_source)
        if cv_text is None:
            print('NOTE: No CV found. Use --cv /path/to/cv.tex before applying.',file=sys.stderr)
        return 0
    except (ValueError,OSError) as ex:
        print('Sync aborted: '+str(ex),file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
