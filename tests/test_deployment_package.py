"""Import the application from exactly the sources included in the Docker image."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys


def test_docker_copy_includes_all_runtime_modules(tmp_path):
    root = Path(__file__).resolve().parents[1]
    for line in (root/'Dockerfile').read_text().splitlines():
        if not line.startswith('COPY '):
            continue
        parts = shlex.split(line)
        for source in parts[1:-1]:
            src = root/source
            if src.is_dir():
                destination = tmp_path/parts[-1]
                shutil.copytree(src,destination,dirs_exist_ok=True)
            else:
                destination = tmp_path/parts[-1]/src.name
                shutil.copy2(src,destination)
    check = subprocess.run([sys.executable,'-I','-c',
        'import sys;from pathlib import Path;sys.path.insert(0,str(Path.cwd()));'
        'import server;assert (Path.cwd()/"static/index.html").is_file();'
        'assert len(server.demo_state()["guides"])==3'],
        cwd=tmp_path,env={**os.environ,'HARU_DB':str(tmp_path/'package.db')},capture_output=True,text=True)
    assert check.returncode==0,check.stderr
