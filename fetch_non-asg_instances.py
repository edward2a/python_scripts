#!/usr/bin/env python3

import boto3


ec2 = boto3.client('ec2')
asg = boto3.client('autoscaling')


def get_as_groups(client):
    """Get all groups and return a dict with group:[instances]."""
    as_groups = {}
    asg_describe_p = client.get_paginator('describe_auto_scaling_groups')

    for page in asg_describe_p.paginate():
        as_groups.update(
            {g['AutoScalingGroupName']: [
                i['InstanceId'] for i in g['Instances']
            ] for g in page['AutoScalingGroups']})

    return as_groups
