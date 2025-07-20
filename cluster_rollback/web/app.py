from flask import Flask, render_template_string, redirect, url_for, request, flash
from git import Repo
from kubernetes import client, config, utils
import os
from cluster_rollback.snapshot import take_snapshot, ensure_repo
import threading
from kubernetes import watch
import time
from kubernetes.config import ConfigException

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
    body { font-family: Arial, sans-serif; background: #f4f6fb; margin: 0; padding: 0; }
    .container { max-width: 700px; margin: 40px auto; background: #fff; border-radius: 12px; box-shadow: 0 4px 24px #0001; padding: 32px 24px; }
    h1 { text-align: center; margin-bottom: 32px; }
    .timeline { position: relative; margin: 0; padding: 0 0 0 40px; }
    .timeline::before { content: ''; position: absolute; left: 20px; top: 0; bottom: 0; width: 4px; background: #e0e4ea; border-radius: 2px; }
    .timeline-event { position: relative; margin-bottom: 36px; }
    .timeline-dot { position: absolute; left: 10px; top: 8px; width: 20px; height: 20px; background: #4CAF50; border-radius: 50%; border: 4px solid #fff; box-shadow: 0 2px 8px #0002; z-index: 2; }
    .timeline-content { margin-left: 40px; background: #f9fafc; border-radius: 8px; padding: 16px 20px; box-shadow: 0 2px 8px #0001; }
    .timeline-content h3 { margin: 0 0 8px 0; font-size: 1.1em; }
    .timeline-content .meta { color: #888; font-size: 0.95em; margin-bottom: 8px; }
    .timeline-content .hash { font-family: monospace; font-size: 0.95em; color: #aaa; }
    .timeline-content .actions { margin-top: 10px; }
    .timeline-content .actions button, .timeline-content .actions a { margin-right: 10px; padding: 6px 16px; border: none; border-radius: 4px; font-size: 0.98em; cursor: pointer; }
    .timeline-content .actions .rollback-btn { background: #ff5252; color: #fff; }
    .timeline-content .actions .diff-btn { background: #1976d2; color: #fff; }
    .timeline-content .actions .rollback-btn:hover { background: #c62828; }
    .timeline-content .actions .diff-btn:hover { background: #0d47a1; }
    .timeline-content .actions .disabled { background: #ccc; color: #fff; cursor: not-allowed; }
    @media (max-width: 600px) {
      .container { padding: 10px 2px; }
      .timeline-content { padding: 10px 8px; }
    }
    /* Модальное окно */
    .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100vw; height: 100vh; overflow: auto; background: rgba(0,0,0,0.35); }
    .modal-content { background: #222; color: #eee; margin: 60px auto; padding: 24px; border-radius: 8px; max-width: 900px; min-width: 320px; box-shadow: 0 8px 32px #0005; position: relative; }
    .modal-close { position: absolute; right: 18px; top: 12px; color: #fff; font-size: 1.5em; cursor: pointer; }
    pre { overflow-x: auto; background: #222; color: #eee; padding: 12px; border-radius: 6px; }
  </style>
</head>
<body>
  <div class="container">
    <h1>История снапшотов</h1>
    <form method="post" action="{{ url_for('snapshot') }}" style="text-align:center; margin-bottom: 30px;">
      <button type="submit" class="snapshot-btn" style="background:#4CAF50; color:#fff; font-size:1.1em;">Создать снапшот</button>
    </form>
    <div class="timeline">
      {% for c in commits %}
        <div class="timeline-event">
          <div class="timeline-dot"></div>
          <div class="timeline-content">
            <h3>{{ c.committed_datetime.strftime('%Y-%m-%d %H:%M:%S') }}</h3>
            <div class="meta">Автор: {{ c.author.name }} | <span class="hash">{{ c.hexsha[:8] }}</span></div>
            <div>{{ c.message }}</div>
            <div class="actions">
              <button class="rollback-btn" onclick="showRollbackModal('{{ url_for('rollback', commit=c.hexsha) }}', '{{ c.hexsha[:8] }}')">Rollback</button>
              {% if not loop.last %}
                <button class="diff-btn" onclick="showDiffModal('{{ url_for('diff', commit=c.hexsha) }}', '{{ c.hexsha[:8] }}')">Diff</button>
              {% else %}
                <button class="diff-btn disabled" disabled>Diff</button>
              {% endif %}
            </div>
          </div>
        </div>
      {% endfor %}
    </div>
  </div>
  <!-- Модалка для diff -->
  <div id="diffModal" class="modal"><div class="modal-content"><span class="modal-close" onclick="closeModal('diffModal')">&times;</span><h2>Diff</h2><pre id="diffContent">Загрузка...</pre></div></div>
  <!-- Модалка для rollback -->
  <div id="rollbackModal" class="modal"><div class="modal-content"><span class="modal-close" onclick="closeModal('rollbackModal')">&times;</span><h2>Подтвердите откат</h2><div id="rollbackText"></div><form id="rollbackForm" method="get"><button type="submit" class="rollback-btn">Откатить</button></form></div></div>
  <script>
    function showDiffModal(url, hash) {
      document.getElementById('diffModal').style.display = 'block';
      document.getElementById('diffContent').textContent = 'Загрузка...';
      fetch(url).then(r => r.text()).then(t => {
        // Парсим только <pre>...</pre> из ответа
        let m = t.match(/<pre[^>]*>([\s\S]*?)<\/pre>/);
        document.getElementById('diffContent').textContent = m ? m[1] : t;
      });
    }
    function showRollbackModal(url, hash) {
      document.getElementById('rollbackModal').style.display = 'block';
      document.getElementById('rollbackText').textContent = 'Вы уверены, что хотите откатиться к снапшоту ' + hash + '?';
      document.getElementById('rollbackForm').action = url;
    }
    function closeModal(id) {
      document.getElementById(id).style.display = 'none';
    }
    window.onclick = function(event) {
      if (event.target.classList.contains('modal')) closeModal(event.target.id);
    }
  </script>
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
    load_kube_config_auto()
    try:
        utils.create_from_yaml(client.ApiClient(), snapshot_path)
    except Exception as e:
        return f"Ошибка при применении снапшота: {e}", 500
    return redirect(url_for('index'))

@app.route('/diff/<commit>')
def diff(commit):
    import tempfile
    import yaml
    # Получаем путь к снапшоту для выбранного коммита
    obj = repo.commit(commit)
    timestamp = obj.message.strip().split()[1]
    snapshot_path = os.path.join(SNAPSHOT_DIR, timestamp, 'resources.yaml')
    # Получаем текущее состояние кластера
    config.load_incluster_config() if 'KUBERNETES_SERVICE_HOST' in os.environ else config.load_kube_config()
    api_client = client.ApiClient()
    core = client.CoreV1Api(api_client)
    apps = client.AppsV1Api(api_client)
    resources = []
    for item in core.list_pod_for_all_namespaces().items:
        obj = api_client.sanitize_for_serialization(item)
        if obj and 'kind' in obj:
            resources.append(obj)
    for item in core.list_service_for_all_namespaces().items:
        obj = api_client.sanitize_for_serialization(item)
        if obj and 'kind' in obj:
            resources.append(obj)
    for item in apps.list_deployment_for_all_namespaces().items:
        obj = api_client.sanitize_for_serialization(item)
        if obj and 'kind' in obj:
            resources.append(obj)
    for item in apps.list_replica_set_for_all_namespaces().items:
        obj = api_client.sanitize_for_serialization(item)
        if obj and 'kind' in obj:
            resources.append(obj)
    for item in apps.list_stateful_set_for_all_namespaces().items:
        obj = api_client.sanitize_for_serialization(item)
        if obj and 'kind' in obj:
            resources.append(obj)
    for item in apps.list_daemon_set_for_all_namespaces().items:
        obj = api_client.sanitize_for_serialization(item)
        if obj and 'kind' in obj:
            resources.append(obj)
    # Сохраняем текущее состояние во временный файл
    with tempfile.NamedTemporaryFile('w+', delete=False) as tmp:
        yaml.safe_dump_all(resources, tmp)
        tmp_path = tmp.name
    # Сравниваем снапшот с текущим состоянием
    import difflib
    with open(snapshot_path, 'r') as f1, open(tmp_path, 'r') as f2:
        snapshot_lines = f1.readlines()
        current_lines = f2.readlines()
    diff_lines = difflib.unified_diff(current_lines, snapshot_lines, fromfile='current_cluster.yaml', tofile='snapshot.yaml')
    diff_text = ''.join(diff_lines)
    if not diff_text:
        diff_text = 'Нет различий: кластер уже соответствует выбранному снапшоту.'
    # Удаляем временный файл
    os.remove(tmp_path)
    return f"""
    <html><head><meta charset='utf-8'><title>Diff</title></head><body>
    <h2>Diff между текущим состоянием кластера и выбранным снапшотом</h2>
    <pre style='background:#222;color:#eee;padding:10px;overflow-x:auto;'>{diff_text}</pre>
    <a href='{url_for('index')}'>Назад</a>
    </body></html>
    """

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
    load_kube_config_auto()
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

def load_kube_config_auto():
    try:
        # В кластере
        if 'KUBERNETES_SERVICE_HOST' in os.environ:
            config.load_incluster_config()
        else:
            config.load_kube_config()
    except ConfigException as e:
        print(f"[ERROR] Не удалось загрузить kubeconfig: {e}")
        raise

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
