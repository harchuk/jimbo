from flask import Flask, render_template_string, redirect, url_for
from git import Repo
import subprocess
import os

app = Flask(__name__)
repo = Repo('.', search_parent_directories=True)
SNAPSHOT_DIR = os.path.join(os.path.dirname(__file__), '..', 'snapshots')

TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta charset='utf-8'>
  <title>Cluster Snapshots</title>
  <style>
    body { font-family: Arial, sans-serif; padding: 20px; }
    .timeline { position: relative; max-width: 600px; margin: 0 auto; }
    .timeline::after { content: ''; position: absolute; width: 6px; background: #ddd; top: 0; bottom: 0; left: 50%; margin-left: -3px; }
    .entry { padding: 10px 40px; position: relative; width: 50%; }
    .entry::before { content: ''; position: absolute; width: 16px; height: 16px; border-radius: 50%; background: #fff; border: 4px solid #FF9F55; top: 15px; z-index: 1; }
    .left { left: 0; }
    .left::before { right: -8px; }
    .right { left: 50%; }
    .right::before { left: -8px; }
  </style>
</head>
<body>
  <h1>Snapshot Timeline</h1>
  <div class="timeline">
    {% for c in commits %}
      <div class="entry {{ 'left' if loop.index % 2 == 0 else 'right' }}">
        <h3>{{ c.committed_datetime.strftime('%Y-%m-%d %H:%M:%S') }}</h3>
        <p>{{ c.message }}</p>
        <a href="{{ url_for('rollback', commit=c.hexsha) }}">Rollback</a>
      </div>
    {% endfor %}
  </div>
</body>
</html>
"""

@app.route('/')
def index():
    commits = list(repo.iter_commits('HEAD'))
    return render_template_string(TEMPLATE, commits=commits)

@app.route('/rollback/<commit>')
def rollback(commit):
    obj = repo.commit(commit)
    timestamp = obj.message.strip().split()[1]
    repo.git.checkout(commit, '--', SNAPSHOT_DIR)
    snapshot_path = os.path.join(SNAPSHOT_DIR, timestamp, 'resources.yaml')
    subprocess.run(['kubectl', 'apply', '-f', snapshot_path], check=True)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
