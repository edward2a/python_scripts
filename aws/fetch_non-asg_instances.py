#!/usr/bin/env python3
"""
Get list of ASG and NON-ASG instances in AWS.

TODO: config file
"""

import argparse
import boto3


DEFAULT_REGION = 'eu-west-1'  # I like Ireland.


def load_args():
    """Load and return configuration parameters."""
    p = argparse.ArgumentParser()

    p.add_argument(
        '-r', '--region', default=DEFAULT_REGION,
        type=lambda s: s.split(','), help='AWS region')

    p.add_argument(
        '-c', '--config', help='Configuration file to use')

    p.add_argument(
        '--no-print-autoscaling', action='store_false', default=True,
        dest='print_asg', help='Do not print AutoScaling instances')

    p.add_argument(
        '--no-print-static', action='store_false', default=True,
        dest='print_static', help='Do not print static instances')

    p.add_argument(
        '--print-ami', action='store_true', default=False,
        dest='print_ami', help='Print the list of AMIs in use.')

    return p.parse_args()


def get_as_groups(client):
    """Get all groups and return {group:[instances], ...}, set([instances])."""
    as_groups = {}
    as_instances = set()

    asg_describe_p = client.get_paginator('describe_auto_scaling_groups')

    for page in asg_describe_p.paginate():
        as_groups.update(
            {g['AutoScalingGroupName']: [
                i['InstanceId'] for i in g['Instances']
            ] for g in page['AutoScalingGroups']})

    for v in as_groups.values():
        as_instances.update(v)

    return as_groups, as_instances


def get_ec2_non_asg_instances(client, as_instances):
    """Get all EC2 instances by batch, return not in as_instances and AMIs."""
    non_asg_i = []
    amis = set()

    ec2_describe_p = client.get_paginator('describe_instances')

    # fetch all instances? (left as reference for list comprehension)
    # instances = [i['InstanceId']
    #     for i_res in ec2_describe_p.paginate()
    #     for i_s in i_res['Reservations']
    #     for i in i_s['Instances']]

    for page in ec2_describe_p.paginate():
        for reservation in page['Reservations']:
            for instance in reservation['Instances']:

                amis.update([instance['ImageId']])
        
                if instance['InstanceId'] not in as_instances:
                    non_asg_i.append(instance['InstanceId'])

    return non_asg_i, amis


def process_region(region, args):
    """Execute main function, region scope."""
    asg = boto3.client('autoscaling', region_name=region)
    ec2 = boto3.client('ec2', region_name=region)

    as_groups, as_instances = get_as_groups(asg)
    non_asg_i, amis = get_ec2_non_asg_instances(ec2, as_instances)

    if args.print_asg:
        print('\n\t==== AutoScaling Instances - %s ====\n' % region)
        for i in as_instances:
            print(i)

    if args.print_static:
        print('\n\t==== Static Instances  - %s ====\n' % region)
        for i in non_asg_i:
            print(i)

    if args.print_ami:
        print('\n\t==== AMIs in use - %s ====\n' % region)
        for a in amis:
            print(a)


if __name__ == '__main__':

    args = load_args()

    if args.config is None:
        for r in args.region:
            process_region(r, args)

