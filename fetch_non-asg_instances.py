#!/usr/bin/env python3

import boto3


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

    non_asg_i = []

    ec2_describe_p = client.get_paginator('describe_instances')

    # fetch all instances?
    #instances = [i['InstanceId']
    #    for i_res in ec2_describe_p.paginate()
    #    for i_s in i_res['Reservations']
    #    for i in i_s['Instances']]

    for page in ec2_describe_p.paginate():
        for reservation in page['Reservations']:
            for instance in reservation['Instances']:
                if instance['InstanceId'] not in as_instances:
                    non_asg_i.append(instance['InstanceId'])

    return non_asg_i


if __name__ == '__main__':
    
    asg = boto3.client('autoscaling')
    ec2 = boto3.client('ec2')

    as_groups, as_instances = get_as_groups(asg)
    non_asg_i = get_ec2_non_asg_instances(ec2, as_instances)

    print('\n\t==== AutoScaling Instances ====\n')
    for i in as_instances:
        print(i)

    print('\n\t==== Static Instances ====\n')
    for i in non_asg_i:
        print(i)
