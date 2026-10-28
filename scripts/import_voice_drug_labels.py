"""Import public DailyMed SPL XML/ZIP files offline, without an LLM or credentials.

Usage: python scripts/import_voice_drug_labels.py document.xml --output app/data/voice_drug_sources.jsonl
Use --alias for verified spelling equivalents, never unverified brand equivalences.
The official full/periodic archives can be downloaded separately from DailyMed.
This tool does not access patient records or download proprietary databases.
"""
import argparse
import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

NS = {'h': 'urn:hl7-org:v3'}
CODES = {'34067-9': 'indications', '34070-3': 'contraindications', '43685-7': 'warnings',
         '34071-1': 'warnings', '34073-7': 'interactions', '43684-0': 'specific_populations',
         '42228-7': 'pregnancy', '34080-2': 'lactation', '34072-9': 'adverse_reactions'}


def text(node):
    return ' '.join(' '.join(node.itertext()).split()) if node is not None else ''


def parse_spl(data, aliases=()):
    if len(data) > 16000000 or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('Unsafe or oversized XML')
    root = ET.fromstring(data)
    ident = root.find('h:setId', NS)
    if ident is None or not re.fullmatch(r'[0-9a-fA-F-]{36}', ident.get('root', '')):
        raise ValueError('Missing SPL identity')
    setid = ident.get('root')
    names = set(aliases)
    # Inactive/unclassified SPL ingredients are excipients, not drug aliases.
    selectors = ['.//h:manufacturedProduct/h:name',
                 './/h:activeIngredient/h:activeIngredientSubstance/h:name']
    for active_class in ('ACTIB', 'ACTIM', 'ACTIR'):
        ingredient = './/h:ingredient[@classCode="' + active_class + '"]/h:ingredientSubstance'
        selectors.extend((ingredient + '/h:name', ingredient + '/h:activeMoiety/h:activeMoiety/h:name'))
    for selector in selectors:
        names.update(text(n).lower() for n in root.findall(selector, NS) if text(n))
    sections = []
    for section in root.findall('.//h:section', NS):
        code = section.find('h:code', NS)
        kind = CODES.get(code.get('code')) if code is not None else None
        if not kind: continue
        title = text(section.find('h:title', NS))
        paragraphs = []
        # Leaf paragraphs and table rows retain full row relationships.
        for node in section.findall('.//h:text', NS):
            for child in node.iter():
                tag = child.tag.rsplit('}', 1)[-1]
                if tag in {'paragraph', 'item', 'tr'} and not any(c.tag.rsplit('}', 1)[-1] in {'paragraph', 'item', 'tr'} for c in child.iter() if c is not child):
                    value = text(child)
                    if value and value not in paragraphs: paragraphs.append(value)
        if not paragraphs:
            value = text(section.find('h:text', NS))
            if value: paragraphs.append(value)
        sections.append({'kind': kind, 'title': title or kind, 'paragraphs': paragraphs})
    if not sections or not names: raise ValueError('No drug names or supported clinical sections')
    date = root.find('h:effectiveTime', NS); version = root.find('h:versionNumber', NS)
    return {'id': 'dailymed-' + setid, 'institution': 'NLM DailyMed (US)',
        'title': text(root.find('h:title', NS)) or ', '.join(sorted(names)),
        'url': 'https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=' + setid,
        'jurisdiction': 'US', 'effective_date': date.get('value') if date is not None else None,
        'version': version.get('value') if version is not None else None,
        'retrieved_at': datetime.now(timezone.utc).isoformat(), 'aliases': sorted(names), 'sections': sections}


def documents(path):
    if path.suffix.lower() == '.xml':
        if path.stat().st_size > 16000000: raise ValueError('XML too large')
        yield path.read_bytes()
    else:
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                if info.filename.lower().endswith('.xml'):
                    if info.file_size > 16000000: raise ValueError('XML too large')
                    yield archive.read(info)
                elif info.filename.lower().endswith('.zip'):
                    if info.file_size > 32000000: raise ValueError('Nested label archive too large')
                    with zipfile.ZipFile(io.BytesIO(archive.read(info))) as nested:
                        for child in nested.infolist():
                            if child.filename.lower().endswith('.xml'):
                                if child.file_size > 16000000: raise ValueError('XML too large')
                                yield nested.read(child)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='+', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--alias', action='append', default=[])
    args = parser.parse_args()
    if args.alias and len(args.files) != 1:
        parser.error('Aliases must be applied to exactly one verified label file')
    records = {}
    if args.output.exists():
        records = {item['id']: item for item in (json.loads(line) for line in args.output.read_text().splitlines() if line.strip())}
    for path in args.files:
        for data in documents(path):
            item = parse_spl(data, args.alias)
            previous = records.get(item['id'])
            if previous and int(previous.get('version') or 0) > int(item.get('version') or 0):
                continue
            records[item['id']] = item
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pending = args.output.with_suffix('.pending')
    pending.write_text(''.join(json.dumps(item, ensure_ascii=False) + '\n' for item in records.values()))
    pending.replace(args.output)
    print('Imported', len(records), 'versioned public drug labels')


if __name__ == '__main__': main()

