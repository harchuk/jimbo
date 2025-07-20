from flask import Flask, render_template_string, redirect, url_for, request, flash
from git import Repo
from kubernetes import client, config, utils
import os
from cluster_rollback.snapshot import take_snapshot, ensure_repo

app = Flask(__name__)
SNAPSHOT_DIR = os.path.join(os.path.dirname(__file__), '..', 'snapshots')
repo = ensure_repo()

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
    .snapshot-btn { display: inline-block; margin-bottom: 20px; padding: 10px 20px; background: #4CAF50; color: #fff; border: none; border-radius: 4px; text-decoration: none; font-size: 16px; cursor: pointer; }
    .snapshot-btn:hover { background: #388E3C; }
  </style>
</head>
<body>
  <h1>Snapshot Timeline</h1>
  <form method="post" action="{{ url_for('snapshot') }}">
    <button type="submit" class="snapshot-btn">Создать снапшот</button>
  </form>
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
    config.load_kube_config()
    utils.create_from_yaml(client.ApiClient(), snapshot_path)
    return redirect(url_for('index'))

@app.route('/snapshot', methods=['POST'])
def snapshot():
    take_snapshot()
    return redirect(url_for('index'))

if __name__ == '__main__':
    # При старте приложения — если нет ни одного снапшота, создать первый
    if not list(repo.iter_commits('HEAD')):
        take_snapshot()
    app.run(host='0.0.0.0', port=8000)
