#!/usr/bin/env python3

# TODO: use logging instead of print
# TODO: improve log messages
# TODO: resume operation
# TODO: skip completed
#
# Input file format (yaml):
#
# my-instance-name-tag:
#   imageId: ami-1234567812345678
#   instanceType: t2.micro
#   keyName: my-ssh-key
#   volumes:
#     sda1: snap-1234567812345678
#   tags:
#       project: something-interesting
#       cost-centre: something-not-interesting


import argparse
import boto3
import random
import yaml

from botocore.exceptions import ClientError
from time import sleep


def load_args():
    p = argparse.ArgumentParser()

    p.add_argument('-g', '--security-group', required=True,
        help='Security Group for the instances')
    p.add_argument('-i', '--input', required=True,
        help='Input file for processing')
    p.add_argument('-o', '--output', required=False, default='output.yml',
        help='Output file for result')
    p.add_argument('-r', '--region', required=False, default='eu-west-2',
        help='The target AWS region')
    p.add_argument('-s', '--subnet-id', '--sn', required=True,
        action='append', help='Target AWS subnet ID(s) for the instances')
    p.add_argument('-t', '--tag-prefix', required=False, default='restored',
        help='Prefix for the Name tag of the created resources')

    return p.parse_args()


def load_targets(srcfile):
    with open(srcfile) as f:
        return yaml.safe_load(f)


def save_targets(dstfile, data):
    with open(dstfile, 'w') as f:
        f.write(yaml.safe_dump(data))


def validate_targets(targets):
    tainted = 0
    required = [
        'imageId',
        'keyName',
        'volumes',
    ]

    for t in targets:
        for k in required:
            try:
                targets[t][k]
            except KeyError:
                print('ERROR: Target {} is missing item {}'.format(t, k))
                tainted+=1

    if tainted > 0:
        print('ERROR: Found {} tainted configuration items. Aborting...'.format(tainted))
        exit(1)


def get_az_mappings(subnets, client):
    """Resolve subnet to AZ mappings."""
    print('INFO: Mapping subnets to AZs...')
    mappings = {}
    mappings['by-sn'] = {
        s['SubnetId']: s['AvailabilityZone'] for s in client.describe_subnets(
            SubnetIds=subnets)['Subnets']
    }
    mappings['by-az'] = {v:k for k,v in mappings['by-sn'].items()}

    return mappings


def create_volume_from_snapshot(client, snap, az, tags=[]):
    return client.create_volume(
        AvailabilityZone=az,
        Encrypted=True,
        SnapshotId=snap,
        VolumeType='gp2',
        TagSpecifications=[{
            'ResourceType': 'volume',
            'Tags': tags
        }])


def process_volumes(targets, client, args, az_maps):
    """Create volumes from snaps and update targets with volume IDs."""
    for t in targets.keys():
        print('INFO: Processing system {}'.format(t))
        az = random.choice(list(az_maps['by-az'].keys()))

        for d, s in targets[t]['volumes'].items():

            tags = targets[t].get('tags', {})
            tags.update({
                'source-system': t,
                'device': d,
                'Name': args.tag_prefix + '-volume'})
            tags = [{'Key':k, 'Value':v} for k,v in tags.items()]

            print('INFO: Processing volume {} ({})'.format(d, s))
            v = create_volume_from_snapshot(client, s, az,tags)

            targets[t]['volumes'][d] = v['VolumeId']
            targets[t]['subnetId'] = az_maps['by-az'][az]
            print('INFO: Created volume {}'.format(v['VolumeId']))


def volume_waiter(target, client):
    """Wait for volumes to become available."""
    state = lambda x: client.describe_volumes(VolumeIds=[x])['Volumes'][0]['State']

    for v in target['volumes'].values():

        try:
            loop = 0

            while (state(v) != 'available' and loop < 30):
                print('INFO: Waiting on volume {} to become available...'.format(v))
                sleep(10)
                loop+=1

        except ClientError as e:

            # Return false if something fails
            print('ERROR:', e)
            return False

    return True


def create_instance(system, target, client, args):
    """Create vanilla instances."""

    tags = target.get('tags', {})
    tags.update({
        'Name': '{}-{}-instance'.format(args.tag_prefix, system)
    })
    tags = [{'Key':k, 'Value':v} for k,v in tags.items()]

    r = client.run_instances(
        ImageId=target['imageId'],
        InstanceType=target.get('instanceType', 't2.micro'),
        KeyName=target['keyName'],
        MaxCount=1,
        MinCount=1,
        SecurityGroupIds=[args.security_group],
        SubnetId=target['subnetId'],
        TagSpecifications=[{
            'ResourceType': 'instance',
            'Tags': tags
        }])

    return r['Instances'][0]['InstanceId']


def instance_waiter(i, s, client):
    """Wait for an instance to be s."""
    state = lambda x: client.describe_instances(InstanceIds=[x])['Reservations'][0]['Instances'][0]['State']['Name']

    loop = 0
    while (state(i) != s and loop < 30):
        print('INFO: Waiting for {} to be stopped.'.format(i))
        loop+=1
        sleep(10)

    if loop == 30:
        return False

    return True


def replace_root(system, target, client):
    """Remove root volume, delete it and attach all restored volumes."""
    i = client.describe_instances(
        InstanceIds=[target['instanceId']])['Reservations'][0]['Instances'][0]
    vol_id = i['BlockDeviceMappings'][0]['Ebs']['VolumeId']

    # Wait for instance to be stopped
    if not instance_waiter(target['instanceId'], 'stopped', client):
        print('ERROR: Timed out waiting for {} to stop, skipping...'.format(target['instanceId']))
        return False

    # Wait for restored volume(s) to be available
    if not volume_waiter(target, client):
        print('ERROR: Failed waiting on volumes for system {}, skipping...'.format(system))
        return False

    # Detach root
    print('INFO: Detaching {} from system {} ({})'.format(
        vol_id, system, target['instanceId']))
    client.detach_volume(VolumeId=vol_id)
    sleep(10)

    # Delete old root
    print('INFO: Deleting {}'.format(vol_id))
    client.delete_volume(VolumeId=i['BlockDeviceMappings'][0]['Ebs']['VolumeId'])

    # Attach restored volumes
    for k,v in target['volumes'].items():
        print('INFO: Attaching restored {} volume ({}) to {} ({})'.format(
            k, v, system, target['instanceId']))

        try:
            client.attach_volume(Device='/dev/' + k,
                InstanceId=target['instanceId'], VolumeId=v)
        except ClientError as e:
            print('ERROR: Failed to attach volume {} to {}.'.format(v, target['instanceId']), e)
            pass

    return True


def process_instances(targets, client, args):
    """Create instances and replace the root volume."""
    systems = targets.keys()

    # Create all instances
    for s in systems:
        i = create_instance(s, targets[s], client, args)
        targets[s]['instanceId'] = i

    ids = set([targets[s]['instanceId'] for s in systems])

    print('INFO: Waiting 60 seconds for instances to boot...')
    sleep(60)

    # Stop all instances
    # TODO: send calls in bacth
    print('INFO: Stopping all instances')
    client.stop_instances(InstanceIds=list(ids))

    # Replace root vol
    for s in systems:
        if replace_root(s, targets[s], client):
            targets[s]['status'] = 'completed'
        else:
            targets[s]['status'] = 'failed'
            ids.remove(targets[s]['instanceId'])

    # Start
    # TODO: send calls in bacth
    print('INFO: Starting all instances')
    client.start_instances(InstanceIds=list(ids))


def main():
    args = load_args()
    targets = load_targets(args.input)
    validate_targets(targets)

    # Register state
    for t in targets.keys():
        targets[t]['status'] = 'pending'

    try:
        ec2 = boto3.client('ec2', region_name=args.region)
        az_maps = get_az_mappings(args.subnet_id, ec2)
        process_volumes(targets, ec2, args, az_maps)
        process_instances(targets, ec2, args)

    except:
        raise

    finally:
        save_targets(args.output, targets)


if __name__ == "__main__":
    main()
