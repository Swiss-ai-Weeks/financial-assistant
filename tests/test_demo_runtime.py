"""Linux process identity checks with real subprocesses; no external service required."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def test_detached_identity_status_stop_rejects_unrelated_pid(tmp_path):
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    for name in ('demo_common.sh', 'demo_status.sh', 'demo_stop.sh'):
        shutil.copy(ROOT / 'scripts' / name, scripts / name)
    runtime = tmp_path / '.run'
    runtime.mkdir()
    backend = scripts / 'anomaly_api.py'
    backend.write_text('import time\ntime.sleep(60)\n')
    owned = subprocess.Popen([sys.executable, str(backend)], start_new_session=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    unrelated = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    def record(name, process, stamp=None):
        actual = Path(f'/proc/{process.pid}/stat').read_text().split()[21]
        (runtime / f'{name}.pid').write_text(f'{process.pid} {stamp or actual}\n')
    try:
        record('backend', owned)
        record('frontend', unrelated)
        status = subprocess.check_output(['bash', str(scripts / 'demo_status.sh')], text=True)
        assert 'backend RUNNING' in status and 'frontend STOPPED' in status
        # Kernel start-time mismatch must also refuse a matching command.
        record('backend', owned, '0')
        subprocess.run(['bash', str(scripts / 'demo_stop.sh')], check=True)
        assert owned.poll() is None and unrelated.poll() is None
        record('backend', owned)
        subprocess.run(['bash', str(scripts / 'demo_stop.sh')], check=True)
        owned.wait(timeout=10)
        assert unrelated.poll() is None
    finally:
        for process in (owned, unrelated):
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)


def test_start_uses_terminal_independent_exact_executables():
    source = (ROOT / 'scripts/demo_start.sh').read_text()
    assert 'nohup setsid "$@" </dev/null' in source
    assert '9>&-' in source  # Detached children cannot retain the lifecycle lock.
    assert 'node "$ROOT/frontend/node_modules/vite/bin/vite.js" --strictPort' in source
    assert 'unset BOOKREADER_API_TOKEN' in source
    subprocess.run(['bash', '-n', str(ROOT / 'scripts/demo_start.sh')], check=True)


def test_start_survives_parent_exit_and_is_idempotent(tmp_path):
    import socket
    import pytest
    if not shutil.which('node') or not shutil.which('setsid'):
        pytest.skip('Linux demo runtime tools unavailable')
    for port in (8001, 5173):
        with socket.socket() as sock:
            try:
                sock.bind(('127.0.0.1', port))
            except OSError:
                pytest.skip('Demo ports unavailable for isolated runtime test')
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    for path in (ROOT / 'scripts').glob('demo_*.sh'):
        shutil.copy(path, scripts / path.name)
    python = tmp_path / '.venv/bin/python'
    python.parent.mkdir(parents=True)
    python.symlink_to(sys.executable)
    market = tmp_path / 'data/cache/market'
    market.mkdir(parents=True)
    for name in ('global_demo_daily.csv', 'demo_pair_fits.json'):
        (market / name).touch()
    (scripts / 'anomaly_api.py').write_text('''from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200); self.end_headers(); self.wfile.write(b'{}')
HTTPServer(('127.0.0.1',8001), Handler).serve_forever()
''')
    vite = tmp_path / 'frontend/node_modules/vite/bin/vite.js'
    vite.parent.mkdir(parents=True)
    vite.write_text("if (process.env.BOOKREADER_API_TOKEN) process.exit(9); require('http').createServer((q,r)=>r.end('ok')).listen(5173, '127.0.0.1');")
    env = {**os.environ, 'BOOKREADER_API_TOKEN':'test-server-only-token'}
    env.pop('BOOKREADER_ENV_FILE', None)
    try:
        subprocess.run(['bash', str(scripts / 'demo_start.sh')], env=env, check=True, timeout=40, capture_output=True)
        # The launching shell has exited; both services still answer and retain their PIDs.
        before = {name: (tmp_path / f'.run/{name}.pid').read_text() for name in ('backend', 'frontend')}
        status = subprocess.check_output(['bash', str(scripts / 'demo_status.sh')], text=True)
        assert status.count('RUNNING') == 2
        subprocess.run(['bash', str(scripts / 'demo_start.sh')], env=env, check=True, timeout=10, capture_output=True)
        assert before == {name: (tmp_path / f'.run/{name}.pid').read_text() for name in before}
    finally:
        subprocess.run(['bash', str(scripts / 'demo_stop.sh')], check=True, timeout=20, capture_output=True)
