#!/usr/bin/env python3

import argparse
import boto3


DEFAULT_REGION='eu-west-1' # I like Ireland.


def load_args():
    """Load and return configuration parameters."""

    p = argparse.ArgumentParser()

    p.add_argument('-r', '--region', default=DEFAULT_REGION,
        help='AWS region')

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
    """Get all EC2 instances by batch, return ones not in as_instances."""
    non_asg_i = []

    ec2_describe_p = client.get_paginator('describe_instances')

    # fetch all instances? (left as reference for list comprehension)
    # instances = [i['InstanceId']
    #     for i_res in ec2_describe_p.paginate()
    #     for i_s in i_res['Reservations']
    #     for i in i_s['Instances']]

    for page in ec2_describe_p.paginate():
        for reservation in page['Reservations']:
            for instance in reservation['Instances']:
                if instance['InstanceId'] not in as_instances:
                    non_asg_i.append(instance['InstanceId'])

    return non_asg_i


if __name__ == '__main__':

    args = load_args()

    asg = boto3.client('autoscaling', region_name=args.region)
    ec2 = boto3.client('ec2', region_name=args.region)

    as_groups, as_instances = get_as_groups(asg)
    non_asg_i = get_ec2_non_asg_instances(ec2, as_instances)

    print('\n\t==== AutoScaling Instances ====\n')
    for i in as_instances:
        print(i)

    print('\n\t==== Static Instances ====\n')
    for i in non_asg_i:
        print(i)
