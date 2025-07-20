import os
import datetime
from git import Repo
from kubernetes import client, config, utils
import yaml

SNAPSHOT_DIR = os.path.join(os.path.dirname(__file__), 'snapshots')


def ensure_repo():
    # Используем отдельный git-репозиторий для снапшотов
    git_dir = os.path.join(SNAPSHOT_DIR, '.git')
    if not os.path.exists(git_dir):
        os.makedirs(SNAPSHOT_DIR, exist_ok=True)
        Repo.init(SNAPSHOT_DIR)
    repo = Repo(SNAPSHOT_DIR)
    return repo


def collect_resources(api_client):
    resources = []
    core = client.CoreV1Api(api_client)
    apps = client.AppsV1Api(api_client)
    batch = client.BatchV1Api(api_client)
    batchv1b = client.BatchV1beta1Api(api_client) if hasattr(client, 'BatchV1beta1Api') else None
    networking = client.NetworkingV1Api(api_client)
    autoscaling = client.AutoscalingV1Api(api_client)
    rbac = client.RbacAuthorizationV1Api(api_client)

    def safe_list(fn, name):
        try:
            items = fn()
            print(f"[SNAPSHOT] {name}: {len(items)} объектов")
            return items
        except Exception as e:
            print(f"[ERROR] Не удалось получить {name}: {e}")
            return []

    # Core
    for item in safe_list(lambda: core.list_pod_for_all_namespaces().items, 'pods'):
        obj = api_client.sanitize_for_serialization(item)
        if obj and 'kind' in obj:
            resources.append(obj)
    for item in safe_list(lambda: core.list_service_for_all_namespaces().items, 'services'):
        obj = api_client.sanitize_for_serialization(item)
        if obj and 'kind' in obj:
            resources.append(obj)
    for item in safe_list(lambda: core.list_config_map_for_all_namespaces().items, 'configmaps'):
        obj = api_client.sanitize_for_serialization(item)
        if obj and 'kind' in obj:
            resources.append(obj)
    for item in safe_list(lambda: core.list_persistent_volume_claim_for_all_namespaces().items, 'persistentvolumeclaims'):
        obj = api_client.sanitize_for_serialization(item)
        if obj and 'kind' in obj:
            resources.append(obj)
    for item in safe_list(lambda: core.list_persistent_volume().items, 'persistentvolumes'):
        obj = api_client.sanitize_for_serialization(item)
        if obj and 'kind' in obj:
            resources.append(obj)
    for item in safe_list(lambda: core.list_service_account_for_all_namespaces().items, 'serviceaccounts'):
        obj = api_client.sanitize_for_serialization(item)
        if obj and 'kind' in obj:
            resources.append(obj)

    # Apps
    for item in safe_list(lambda: apps.list_deployment_for_all_namespaces().items, 'deployments'):
        obj = api_client.sanitize_for_serialization(item)
        if obj and 'kind' in obj:
            resources.append(obj)
    for item in safe_list(lambda: apps.list_replica_set_for_all_namespaces().items, 'replicasets'):
        obj = api_client.sanitize_for_serialization(item)
        if obj and 'kind' in obj:
            resources.append(obj)
    for item in safe_list(lambda: apps.list_stateful_set_for_all_namespaces().items, 'statefulsets'):
        obj = api_client.sanitize_for_serialization(item)
        if obj and 'kind' in obj:
            resources.append(obj)
    for item in safe_list(lambda: apps.list_daemon_set_for_all_namespaces().items, 'daemonsets'):
        obj = api_client.sanitize_for_serialization(item)
        if obj and 'kind' in obj:
            resources.append(obj)

    # Batch
    for item in safe_list(lambda: batch.list_job_for_all_namespaces().items, 'jobs'):
        obj = api_client.sanitize_for_serialization(item)
        if obj and 'kind' in obj:
            resources.append(obj)
    if batchv1b:
        for item in safe_list(lambda: batchv1b.list_cron_job_for_all_namespaces().items, 'cronjobs'):
            obj = api_client.sanitize_for_serialization(item)
            if obj and 'kind' in obj:
                resources.append(obj)

    # Networking
    for item in safe_list(lambda: networking.list_ingress_for_all_namespaces().items, 'ingresses'):
        obj = api_client.sanitize_for_serialization(item)
        if obj and 'kind' in obj:
            resources.append(obj)
    for item in safe_list(lambda: networking.list_network_policy_for_all_namespaces().items, 'networkpolicies'):
        obj = api_client.sanitize_for_serialization(item)
        if obj and 'kind' in obj:
            resources.append(obj)

    # Autoscaling
    for item in safe_list(lambda: autoscaling.list_horizontal_pod_autoscaler_for_all_namespaces().items, 'horizontalpodautoscalers'):
        obj = api_client.sanitize_for_serialization(item)
        if obj and 'kind' in obj:
            resources.append(obj)

    # RBAC
    for item in safe_list(lambda: rbac.list_role_for_all_namespaces().items, 'roles'):
        obj = api_client.sanitize_for_serialization(item)
        if obj and 'kind' in obj:
            resources.append(obj)
    for item in safe_list(lambda: rbac.list_role_binding_for_all_namespaces().items, 'rolebindings'):
        obj = api_client.sanitize_for_serialization(item)
        if obj and 'kind' in obj:
            resources.append(obj)
    for item in safe_list(lambda: rbac.list_cluster_role().items, 'clusterroles'):
        obj = api_client.sanitize_for_serialization(item)
        if obj and 'kind' in obj:
            resources.append(obj)
    for item in safe_list(lambda: rbac.list_cluster_role_binding().items, 'clusterrolebindings'):
        obj = api_client.sanitize_for_serialization(item)
        if obj and 'kind' in obj:
            resources.append(obj)

    return resources


def take_snapshot():
    timestamp = datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    path = os.path.join(SNAPSHOT_DIR, timestamp)
    os.makedirs(path, exist_ok=True)
    outfile = os.path.join(path, 'resources.yaml')

    config.load_incluster_config()
    api_client = client.ApiClient()
    resources = collect_resources(api_client)

    with open(outfile, 'w') as f:
        yaml.safe_dump_all(resources, f)

    repo = ensure_repo()
    try:
        commits = list(repo.iter_commits('HEAD'))
    except Exception:
        commits = []
    if commits:
        prev_commit = commits[0]
        prev_tree = prev_commit.tree / f'{prev_commit.message.strip().split()[1]}/resources.yaml'
        with open(outfile, 'r') as f_new:
            new_content = f_new.read()
        prev_content = prev_tree.data_stream.read().decode('utf-8')
        if new_content == prev_content:
            print('Изменений нет, снапшот не создан.')
            os.remove(outfile)
            os.rmdir(path)
            return
    repo.index.add([outfile])
    repo.index.commit(f'Snapshot {timestamp}')
    print(f'Snapshot saved to {outfile}')


def rollback(commit):
    repo = ensure_repo()
    obj = repo.commit(commit)
    # Extract timestamp from commit message "Snapshot <timestamp>"
    parts = obj.message.strip().split()
    timestamp = parts[1] if len(parts) > 1 else ''

    repo.git.checkout(commit, '--', SNAPSHOT_DIR)
    snapshot_path = os.path.join(SNAPSHOT_DIR, timestamp, 'resources.yaml')

    config.load_incluster_config()
    utils.create_from_yaml(client.ApiClient(), snapshot_path)
    print(f'Rolled back to commit {commit}')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Snapshot Kubernetes resources')
    subparsers = parser.add_subparsers(dest='command')

    parser_snapshot = subparsers.add_parser('snapshot')
    parser_rollback = subparsers.add_parser('rollback')
    parser_rollback.add_argument('commit', help='Git commit hash to rollback to')

    args = parser.parse_args()
    if args.command == 'snapshot':
        take_snapshot()
    elif args.command == 'rollback':
        rollback(args.commit)
    else:
        parser.print_help()
