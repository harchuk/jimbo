import os
import subprocess
import datetime
from git import Repo

SNAPSHOT_DIR = os.path.join(os.path.dirname(__file__), 'snapshots')


def ensure_repo():
    repo = Repo('.', search_parent_directories=True)
    return repo


def take_snapshot():
    timestamp = datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    path = os.path.join(SNAPSHOT_DIR, timestamp)
    os.makedirs(path, exist_ok=True)
    outfile = os.path.join(path, 'resources.yaml')

    with open(outfile, 'w') as f:
        subprocess.run(['kubectl', 'get', 'all', '--all-namespaces', '-o', 'yaml'], stdout=f, check=True)

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
    subprocess.run(['kubectl', 'apply', '-f', snapshot_path], check=True)
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
