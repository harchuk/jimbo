from flask import Flask, render_template_string, redirect, url_for, request, flash
from git import Repo
from kubernetes import client, config, utils
import os
from cluster_rollback.snapshot import take_snapshot, ensure_repo
import threading
from kubernetes import watch
import time

# Глобальные переменные для защиты от частых снапшотов
last_snapshot_time = 0
snapshot_lock = threading.Lock()

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
    try:
        commits = list(repo.iter_commits('HEAD'))
    except Exception:
        commits = []
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

def safe_take_snapshot():
    global last_snapshot_time
    with snapshot_lock:
        now = time.time()
        # Не чаще одного раза в 60 секунд
        if now - last_snapshot_time >= 60:
            take_snapshot()
            last_snapshot_time = now
        else:
            print("Слишком частые события, снапшот не создан.")

@app.route('/snapshot', methods=['POST'])
def snapshot():
    safe_take_snapshot()
    return redirect(url_for('index'))

def watch_cluster_resources():
    config.load_kube_config()
    w = watch.Watch()
    core = client.CoreV1Api()
    apps = client.AppsV1Api()
    # Слушаем события по Pod, Service, Deployment, ReplicaSet, StatefulSet, DaemonSet
    resource_watchers = [
        (core.list_pod_for_all_namespaces, "Pod"),
        (core.list_service_for_all_namespaces, "Service"),
        (apps.list_deployment_for_all_namespaces, "Deployment"),
        (apps.list_replica_set_for_all_namespaces, "ReplicaSet"),
        (apps.list_stateful_set_for_all_namespaces, "StatefulSet"),
        (apps.list_daemon_set_for_all_namespaces, "DaemonSet"),
    ]
    for func, name in resource_watchers:
        threading.Thread(target=watch_resource, args=(w, func, name), daemon=True).start()

def watch_resource(w, func, name):
    for event in w.stream(func, timeout_seconds=0):
        print(f"Detected {event['type']} on {name}: {event['object'].metadata.name}")
        safe_take_snapshot()

if __name__ == '__main__':
    # При старте приложения — если нет ни одного снапшота, создать первый
    try:
        has_commits = repo.head.is_valid()
    except Exception:
        has_commits = False
    if not has_commits:
        take_snapshot()
        import time as _t; last_snapshot_time = _t.time()
    watch_cluster_resources()
    app.run(host='0.0.0.0', port=8000)
