import os
import datetime
from git import Repo
from kubernetes import client, config, utils
import yaml

SNAPSHOT_DIR = os.path.join(os.path.dirname(__file__), 'snapshots')


def ensure_repo():
    repo = Repo('.', search_parent_directories=True)
    return repo


def take_snapshot():
    timestamp = datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    path = os.path.join(SNAPSHOT_DIR, timestamp)
    os.makedirs(path, exist_ok=True)
    outfile = os.path.join(path, 'resources.yaml')

    config.load_kube_config()
    api_client = client.ApiClient()
    core = client.CoreV1Api(api_client)
    apps = client.AppsV1Api(api_client)

    resources = []
    for item in core.list_pod_for_all_namespaces().items:
        resources.append(api_client.sanitize_for_serialization(item))
    for item in core.list_service_for_all_namespaces().items:
        resources.append(api_client.sanitize_for_serialization(item))
    for item in apps.list_deployment_for_all_namespaces().items:
        resources.append(api_client.sanitize_for_serialization(item))
    for item in apps.list_replica_set_for_all_namespaces().items:
        resources.append(api_client.sanitize_for_serialization(item))
    for item in apps.list_stateful_set_for_all_namespaces().items:
        resources.append(api_client.sanitize_for_serialization(item))
    for item in apps.list_daemon_set_for_all_namespaces().items:
        resources.append(api_client.sanitize_for_serialization(item))

    with open(outfile, 'w') as f:
        yaml.safe_dump_all(resources, f)

    repo = ensure_repo()
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

    config.load_kube_config()
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
