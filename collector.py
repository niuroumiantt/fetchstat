"""Bounded, source-first collection. No model, target or adoption permission."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

ROOT = Path(__file__).resolve().parent
MAX_BYTES = 20 * 1024 * 1024


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def allowed(url, hosts):
    u = urlsplit(url)
    if u.scheme != 'https' or u.hostname not in hosts or u.username or u.password:
        raise ValueError('URL outside registered HTTPS hosts')


class Redirects(HTTPRedirectHandler):
    def __init__(self, hosts):
        self.hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        allowed(newurl, self.hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(source):
    """Three attempts; bounded bytes, timeout and host allowlist, no credentials."""
    allowed(source['url'], source['hosts'])
    opener = build_opener(Redirects(source['hosts']))
    for attempt in range(3):
        try:
            request = Request(source['url'], headers={'User-Agent': 'inresearch-collector/1.0 (+https://inresearch.ai)'})
            with opener.open(request, timeout=30) as response:
                allowed(response.url, source['hosts'])
                data = response.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise ValueError('source exceeds 20 MiB budget')
                if not data:
                    raise ValueError('empty source')
                return data, response.headers.get_content_type(), response.url
        except HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
        except URLError:
            if attempt == 2:
                raise
        time.sleep(2 ** attempt)


def collect(source, data_root, local=None, provenance=None, revision=None):
    from adapter import extract
    from validate_handoff import validate
    started = now()
    clock = time.monotonic()
    data_root = Path(data_root).expanduser().resolve()
    data_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    revision = revision or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('committed collector revision required')
    if local:
        if not provenance:
            raise ValueError('--provenance required when reusing existing bytes')
        path = Path(local).expanduser()
        if path.stat().st_size > MAX_BYTES:
            raise ValueError('source exceeds 20 MiB budget')
        data = path.read_bytes()
        content_type, url, retrieved = source['content_type'], source['url'], None
    else:
        data, content_type, url = download(source)
        retrieved = now()
    if source['extension'] == 'pdf':
        if not data.startswith(b'%PDF-'):
            raise ValueError('not a native PDF')
    elif 'html' not in content_type or b'<html' not in data[:4096].lower():
        raise ValueError('not native HTML')
    sha = digest(data)
    original = data_root / 'originals' / (sha + '.' + source['extension'])
    original.parent.mkdir(mode=0o700, exist_ok=True)
    existed = original.exists()
    if existed and digest(original.read_bytes()) != sha:
        raise ValueError('stored original failed hash; preserve and investigate')
    if not existed:
        with original.open('xb') as f:
            f.write(data)
    meta = data_root / 'originals' / (sha + '.metadata.json')
    if not meta.exists():
        write_json(meta, {'retrieved_at': retrieved, 'provenance_id': provenance, 'first_seen_at': started})
    first = json.loads(meta.read_text())
    rows = extract(data, source, original, retrieved or started)
    if not rows:
        raise ValueError('registered field not found; original preserved, no invented candidate')
    item_id = source['id'] + ':' + sha[:24]
    relative = 'originals/' + original.name
    for row in rows:
        row.update(source_item_id=item_id, revision_of=None, conflicts_with=[], target_ids=[])
        # Candidate content identity deliberately excludes sampling/download clocks.
        identity = json.dumps({'sha': sha, 'adapter': source['adapter_version'], 'row': row}, sort_keys=True)
        row['observation_id'] = source['id'] + ':' + digest(identity.encode())[:32]
    delivery_id = source['team'] + '-' + sha[:24] + '-' + source['adapter_version']
    package = data_root / 'deliveries' / delivery_id
    if package.exists():
        report = validate(package)
        if not report['offline_valid']:
            raise ValueError('existing delivery invalid; preserve and investigate')
        return {'package': str(package), 'replayed': True, 'network_requests': 0 if local else 1, **report}
    stage = data_root / 'deliveries' / ('.' + delivery_id + '-' + str(time.time_ns()))
    (stage / 'originals').mkdir(mode=0o700, parents=True)
    shutil.copyfile(original, stage / relative)
    item = {'item_id': item_id, 'source_id': source['id'], 'source_item_id': source['native_id'],
            'url': url, 'title': source['title'], 'publisher': source['publisher'],
            'retrieved_at': first['retrieved_at'], 'sha256': sha, 'path': relative,
            'content_type': content_type, 'access_scope': 'public', 'completeness': 'complete', 'version_of': None}
    if first['retrieved_at'] is None:
        item.update(reused_at=started, provenance_id=first['provenance_id'])
    manifest = {'contract': 'fetchdata-handoff/1', 'provider_id': source['team'], 'delivery_id': delivery_id,
                'collector_revision': revision, 'generated_at': now(), 'items': [item]}
    write_json(stage / 'manifest.json', manifest)
    (stage / 'observations.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
    (stage / 'errors.jsonl').write_text('')
    (stage / 'SHA256SUMS').write_text(sha + '  ' + relative + '\n')
    counts = {'scheduled_sources': 1, 'attempted_sources': 1, 'successful_sources': 1,
              'new_originals': int(not existed), 'duplicate_originals': int(existed), 'candidates': len(rows),
              'unresolved_candidates': len(rows), 'received': 0, 'reviewed': 0, 'adopted': 0, 'published': 0}
    write_json(stage / 'run-report.json', {'team': source['team'], 'run_id': delivery_id, 'collector_revision': revision,
               'started_at': started, 'finished_at': now(), 'counts': counts,
               'duration_seconds': time.monotonic() - clock, 'bytes_downloaded': 0 if local else len(data),
               'model_calls': 0})
    report = validate(stage)
    if not report['offline_valid']:
        raise ValueError(json.dumps(report))
    stage.rename(package)
    return {'package': str(package), 'replayed': False, **report}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('check-config')
    run = sub.add_parser('run')
    run.add_argument('--data-root')
    run.add_argument('--existing', help='reuse one authorized original without network')
    run.add_argument('--provenance', help='source catalog record or receipt ID; never invent a historical download')
    verify = sub.add_parser('verify')
    verify.add_argument('package')
    args = parser.parse_args()
    source = json.loads((ROOT / 'sources.json').read_text())
    try:
        if args.command == 'verify':
            from validate_handoff import validate
            result = validate(args.package)
            if not result['offline_valid']:
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 1
        elif args.command == 'check-config':
            allowed(source['url'], source['hosts'])
            result = {'team': source['team'], 'source': source['id'], 'model_required': False,
                      'target_required': False, 'scheduled': False}
        else:
            result = collect(source, args.data_root or Path.home() / '.local/share' / source['team'],
                             args.existing, args.provenance)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        # Diagnostics never print source bodies or credential-bearing URLs.
        failure = {'at': now(), 'source_id': source['id'], 'stage': args.command,
                   'error_type': type(error).__name__, 'retryable': False,
                   'next_action': 'inspect source/adapter; original retained; do not fill missing values'}
        state = Path.home() / '.local/state' / source['team']
        state.mkdir(mode=0o700, parents=True, exist_ok=True)
        with (state / 'errors.jsonl').open('a') as f:
            f.write(json.dumps(failure) + '\n')
        print(json.dumps(failure), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
