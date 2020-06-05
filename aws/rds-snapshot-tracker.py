#!/usr/bin/env python3

import argparse
import boto3


def load_args():
    p = argparse.ArgumentParser()

    p.add_argument('-t', '--snap-type', required=False, default='automated',
        help='The tag key to use for filtering', choices=['automated', 'manual'])

    p.add_argument('-i', '--db-instance', required=True,
        help='The tag value to use for filtering')

    return p.parse_args()

def lookup_snapshots(client, query):
    """
    Look up snapshots in EC2.

    Parameters:
    client(boto3.client): The ec2 client
    :query: namespace containing
        snap_type: filter tag key
        db_instance: filter tag value

    Returns:
    list: snapshots sorted by date

    TODO: use a paginator
    """
    snapshots = client.describe_db_snapshots(
        SnapshotType=query.snap_type,
        DBInstanceIdentifier=query.db_instance
    )['DBSnapshots']

    snapshots.sort(key = lambda s: s['SnapshotCreateTime'])

    return snapshots


def printer(snaps):
    """Parse results and print something usable."""
    for s in snaps:

        print('{} {} {} {}'.format(
            str(s['SnapshotCreateTime']),
            s['DBSnapshotIdentifier'],
            s['DBInstanceIdentifier'],
            s.get('KmsKeyId', 'MISSING KMS KEY!!!')
        ))


def main():
    """Main function."""
    args = load_args()
    rds = boto3.client('rds')
    snaps = lookup_snapshots(rds, args)
    printer(snaps)


if __name__ == '__main__':
    main()

