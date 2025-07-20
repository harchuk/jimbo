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


def take_snapshot():
    timestamp = datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    path = os.path.join(SNAPSHOT_DIR, timestamp)
    os.makedirs(path, exist_ok=True)
    outfile = os.path.join(path, 'resources.yaml')

    config.load_incluster_config()
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

    with open(outfile, 'w') as f:
        yaml.safe_dump_all(resources, f)

    repo = ensure_repo()
    # Проверяем, отличается ли новый снапшот от предыдущего
    commits = list(repo.iter_commits('HEAD'))
    if commits:
        prev_commit = commits[0]
        prev_tree = prev_commit.tree / f'{prev_commit.message.strip().split()[1]}/resources.yaml'
        with open(outfile, 'r') as f_new:
            new_content = f_new.read()
        prev_content = prev_tree.data_stream.read().decode('utf-8')
        if new_content == prev_content:
            print('Изменений нет, снапшот не создан.')
            # Удаляем пустую папку
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
