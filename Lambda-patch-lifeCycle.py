import boto3
import time

# AWS region jahan tera instances hain
REGION = "eu-central-1"

# Tag key jo instances identify karega, example: Patch=patch1
PATCH_KEY = "Patch"

# Initialize boto3 clients for EC2 and SSM
ec2 = boto3.client('ec2', region_name=REGION)
ssm = boto3.client('ssm', region_name=REGION)

def lambda_handler(event, context):
    # Lambda event me se patch_tag value uthao
    # Example: {"patch_tag": "patch1"}
    patch_value = event.get("patch_tag")
    if not patch_value:
        return {
            "status": "error",
            "message": "Missing patch_tag in input event"
        }

    print(f"Starting patch for instances with tag {PATCH_KEY}={patch_value}")

    # Get all running instances jinke tags match karte hain
    instances = get_instances_by_tag(PATCH_KEY, patch_value)
    if not instances:
        msg = f"No running instances found with tag {PATCH_KEY}={patch_value}"
        print(msg)
        return {
            "status": "no_instances",
            "message": msg
        }

    # Loop through each instance and run patch command without reboot
    for instance_id in instances:
        print(f"Patching instance: {instance_id}")

        # Run the patch command on instance
        patch_success = run_patch_command(instance_id)

        # Agar patch fail ho gaya, toh process ruk jaayega
        if not patch_success:
            print(f"Patch failed on instance {instance_id}, aborting remaining patches.")
            return {
                "status": "error",
                "message": f"Patch failed on instance {instance_id}"
            }

    # Agar sab successful hua toh success message return karo
    return {
        "status": "success",
        "patched_instances": instances
    }

def get_instances_by_tag(key, value):
    """
    Given tag key and value, returns list of running instance IDs
    matching that tag.
    """
    filters = [{
        'Name': f"tag:{key}",
        'Values': [value]
    }]

    # EC2 describe_instances call with filters
    response = ec2.describe_instances(Filters=filters)

    instance_ids = []
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            # Consider only running instances
            if instance['State']['Name'] == 'running':
                instance_ids.append(instance['InstanceId'])

    return instance_ids

def run_patch_command(instance_id):
    """
    Runs patch command (kernel update) on given instance using SSM
    without reboot.
    Returns True if success, False otherwise.
    """
    # Patch command to update kernel without reboot
    command = "yum update -y kernel"

    try:
        # Send SSM command to instance
        response = ssm.send_command(
            InstanceIds=[instance_id],
            DocumentName="AWS-RunShellScript",
            Parameters={"commands": [command]},
        )

        command_id = response['Command']['CommandId']

        # Poll command status every 10 seconds up to ~5 minutes max
        for _ in range(30):
            time.sleep(10)
            output = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)

            # Break loop if command finished (success/failure/cancel)
            if output['Status'] in ['Success', 'Failed', 'Cancelled', 'TimedOut']:
                break

        print(f"Patch command status on {instance_id}: {output['Status']}")

        # Return True only if success
        return output['Status'] == 'Success'

    except Exception as e:
        print(f"Error running patch command on {instance_id}: {e}")
        return False
