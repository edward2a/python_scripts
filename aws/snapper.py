#!/usr/bin/env python3

# TODO: use logging
# TODO: decent logging messages


import argparse
import boto3
import datetime
import yaml

from time import sleep


date_stamp = datetime.date.today()


def load_args():
    p = argparse.ArgumentParser()

    p.add_argument('-i', '--input', required=True,
        help='Input file for processing')
    p.add_argument('-o', '--output', required=False, default='snap-out.yml',
        help='Output file for results')
    p.add_argument('-r', '--region', required=False, default='eu-west-2',
        help='The AWS region to work on')

    return p.parse_args()


def load_input(srcfile):
    data = []
    with open(srcfile) as f:
        for line in f:
            if line != '\n':
                data.append(line.strip())

    return data


def save_output(dstfile, data):
    with open(dstfile, 'w') as f:
        f.write(yaml.safe_dump(data))


def prepare_targets(instances, client):

    # TODO: batch calls
    # TODO: consider handling reservations with multiple instances
    print('INFO: Fetching information for instances...')
    r = [r['Instances'][0] for r in client.describe_instances(InstanceIds=instances)['Reservations']]

    targets = {}

    for i in r:
        tags = {tag['Key']: tag['Value'] for tag in i['Tags']}
        targets[tags['Name']] = {
            'keyName': i['KeyName'],
            'imageId': i['ImageId'],
            'instanceType': i['InstanceType'],
            'tags': {
                'Name': tags.get('Name', 'MISSING'),
                'environment': tags.get('environment', 'MISSING'),
                'project': tags.get('project', 'MISSING'),
                'retention-ami': tags.get('retention-ami', 14),
                'retention-snap': tags.get('retention-snap', 7)
            },
            'volumes': {d['DeviceName'].lstrip('/dev/'): d['Ebs']['VolumeId'] for d in i['BlockDeviceMappings']}
        }

    return targets


def snapshot(vol, tags, client):

    r = client.create_snapshot(Description='Created by snapper on ' + str(date_stamp),
        TagSpecifications=[{
            'ResourceType': 'snapshot',
            'Tags': [{'Key': k, 'Value': v} for k,v in tags.items()]
        }],
        VolumeId=vol
    )

    print('INFO: Snapshot requested for {}: {}'.format(vol, r['SnapshotId']))
    return r['SnapshotId']


def request_snapshots(targets, client):

    for t in targets.keys():
        print('INFO: Procesing snapshots for {}'.format(t))

        snap_tags = {
            'Date': str(date_stamp),
            'DeleteOn': str(date_stamp + datetime.timedelta(days=int(targets[t]['tags']['retention-snap']))),
            'environment': targets[t]['tags']['environment'],
            'project': targets[t]['tags']['project']
        }

        for dev, vol in targets[t]['volumes'].items():
            tags = {'Name': 'SNAP-{}-{}-{}'.format(
                targets[t]['tags']['Name'].strip('restored-').strip('-instance'),
                dev, str(date_stamp)
            )}
            tags.update(snap_tags)
            snap = snapshot(vol, tags, client)

            # Update target vol to snap
            targets[t]['volumes'][dev] = snap
            print('INFO: Waiting 5 seconds for next snapshot request...')
            sleep(5)


def main():
    args = load_args()
    instances = load_input(args.input)
    targets = {}

    try:
        ec2 = boto3.client('ec2', region_name=args.region)
        targets.update(prepare_targets(instances, ec2))

        # Register state
        for t in targets.keys():
            targets[t]['status'] = 'pending'

        request_snapshots(targets, ec2)

    except:
        raise

    finally:
        save_output(args.output, targets)


if __name__ == '__main__':
    main()
