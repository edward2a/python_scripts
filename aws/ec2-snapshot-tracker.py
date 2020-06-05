#!/usr/bin/env python3

import argparse
import boto3


def load_args():
    p = argparse.ArgumentParser()

    p.add_argument('-k', '--tag-key', required=False, default='Name',
        help='The tag key to use for filtering')

    p.add_argument('-v', '--tag-value', required=True,
        help='The tag value to use for filtering')

    return p.parse_args()

def lookup_snapshots(client, query):
    """
    Look up snapshots in EC2.

    Parameters:
    client(boto3.client): The ec2 client
    :query: namespace containing
        tag_key: filter tag key
        tag_value: filter tag value

    Returns:
    list: snapshots sorted by date

    TODO: use a paginator
    """
    snapshots = client.describe_snapshots(Filters=[
        {
            'Name': 'tag:{}'.format(query.tag_key),
            'Values': [query.tag_value]
        }
    ])['Snapshots']

    snapshots.sort(key = lambda s: s['StartTime'])

    return snapshots


def printer(snaps):
    """Parse results and print something usable."""
    for s in snaps:

        # Look for the name tag
        for t in s['Tags']:
            if t['Key'] == 'Name':
                s['name'] = t['Value']
                break

        print('{} {} {} {}'.format(
            str(s['StartTime']),
            s.get('name', 'MISSING NAME TAG!!!'),
            s['SnapshotId'],
            s.get('KmsKeyId', 'MISSING KMS KEY!!!')
        ))


def main():
    """Main function."""
    args = load_args()
    ec2 = boto3.client('ec2')
    snaps = lookup_snapshots(ec2, args)
    printer(snaps)


if __name__ == '__main__':
    main()

