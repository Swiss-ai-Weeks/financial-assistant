"""Rebuild canonical catalog from ClaimGraph inputs and read-only Pythia checkout."""
import argparse
import csv
import json
from pathlib import Path
from financial_assistant.universe import merge_securities, LIMITATION


def text_rows(path, source, universe):
    sector = None
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith('#'):
            if '·' in line:
                sector = line.lstrip('# ').split('·')[0].strip()
        elif line:
            # USD is not inferred for arbitrary tickers or listings.
            yield dict(ticker=line, sector=sector, universe=universe, source=source)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reference', type=Path, default=Path('/home/codexdev/projects/teammate-pythia'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    path = root / 'data/universe/global_equities.csv'
    with path.open() as stream:
        rows = [{**r, 'source': 'claimgraph/data/universe/global_equities.csv'} for r in csv.DictReader(stream)]
    for repo, base in [('claimgraph', root), ('pythia', args.reference)]:
        for file in sorted((base / 'data/universes').glob('*.txt')):
            rows.extend(text_rows(file, f'{repo}/data/universes/{file.name}', f'{repo}:{file.stem}'))
    payload = dict(schema_version=1, limitation=LIMITATION, securities=merge_securities(rows),
                   unresolved=[r for r in rows if r.get('mapping_status', 'mapped') != 'mapped'])
    (root / 'data/universe/securities.json').write_text('{\n' + ',\n'.join(json.dumps(k) + ': ' + ('[\n' + ',\n'.join(json.dumps(row, ensure_ascii=False) for row in v) + '\n]' if isinstance(v, list) else json.dumps(v)) for k,v in payload.items()) + '\n}\n')
    print(f"{len(payload['securities'])} securities; {len(payload['unresolved'])} unresolved source rows")


if __name__ == '__main__':
    main()
