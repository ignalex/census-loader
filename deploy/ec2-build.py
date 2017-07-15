
import boto3
import logging
import os
import paramiko
import time

logging.getLogger("paramiko").setLevel(logging.INFO)

AWS_FOLDER = "/Users/hugh.saalmans/.aws"
BLUEPRINT = "ubuntu_16_04_1"
BUILDID = "nano_1_2"
# KEY_PAIR_NAME = "Default"
AVAILABILITY_ZONE = "ap-southeast-2a"  # Sydney, AU

PEM_FILE = AWS_FOLDER + "/LightsailDefaultPrivateKey-ap-southeast-2.pem"

INSTANCE_NAME = "census_loader_instance"

def main():

    # get AWS credentials (required to copy pg_dump files from S3)
    aws_access_key_id = ""
    aws_secret_access_key = ""
    cred_array = open(AWS_FOLDER + "/credentials", 'r').read().split("\n")

    for line in cred_array:
        bits = line.split("=")
        if bits[0].lower() == "aws_access_key_id":
            aws_access_key_id = bits[1]
        if bits[0].lower() == "aws_secret_access_key":
            aws_secret_access_key = bits[1]

    # load bash script
    bash_file = os.path.abspath(__file__).replace(".py", ".sh")
    bash_script = open(bash_file, 'r').read().format(aws_access_key_id, aws_secret_access_key)

    lightsail_client = boto3.client('lightsail')

    # blueprints = lightsail_client.get_blueprints()
    # for bp in blueprints['blueprints']:
    #     if bp['isActive']:
    #         print('{} : {}'.format(bp['blueprintId'], bp['description']))

    # bundles = lightsail_client.get_bundles(includeInactive=False)
    # for bundle in bundles['bundles']:
    #     for k, v in bundle.items():
    #         print('{} : {}'.format(k, v))

    response_dict = lightsail_client.create_instances(
        instanceNames=[INSTANCE_NAME],
        availabilityZone=AVAILABILITY_ZONE,
        blueprintId=BLUEPRINT,
        bundleId=BUILDID,
        userData=bash_script
    )
    logger.info(response_dict)

    # wait until instance is running
    instance_dict = get_lightsail_instance(lightsail_client, INSTANCE_NAME)

    while instance_dict["state"]["name"] != 'running':
        logger.info('Waiting 10 seconds ... instance is %s' % instance_dict["state"]["name"])
        time.sleep(10)
        instance_dict = get_lightsail_instance(lightsail_client, INSTANCE_NAME)

    logger.info('Waiting 1 minute... instance is booting')
    time.sleep(120)

    instance_ip = instance_dict["publicIpAddress"]

    key = paramiko.RSAKey.from_private_key_file(PEM_FILE)
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # Here 'ubuntu' is user name and 'instance_ip' is public IP of EC2
    ssh_client.connect(hostname=instance_ip, username="ubuntu", pkey=key)

    # set AWS keys for SSH
    cmd = "export AWS_ACCESS_KEY_ID={0}".format(aws_access_key_id)
    run_ssh_command(ssh_client, cmd)

    cmd = "export AWS_SECRET_ACCESS_KEY={0}".format(aws_secret_access_key)
    run_ssh_command(ssh_client, cmd)

    # update and upgrade instance
    if not run_ssh_command(ssh_client, "sudo apt-get -y upgrade"):
        return False
    if not run_ssh_command(ssh_client, "sudo apt-get -y update"):
        return False

    return True


def get_lightsail_instance(lightsail_client, name):
    response = lightsail_client.get_instance(instanceName=name)

    return response["instance"]


def run_ssh_command(ssh_client, cmd):
    logger.info(cmd)

    stdin, stdout, stderr = ssh_client.exec_command(cmd)

    # for line in stdin.read().splitlines():
    #     logger.info(line)
    stdin.close()

    for line in stdout.read().splitlines():
        logger.info(str(line))
    stdout.close()

    for line in stderr.read().splitlines():
        if line:
            logger.fatal(str(line))
            stderr.close()
            return False
        else:
            stderr.close()

    return True


if __name__ == '__main__':
    logger = logging.getLogger()

    # set logger
    log_file = os.path.abspath(__file__).replace(".py", ".log")
    logging.basicConfig(filename=log_file, level=logging.DEBUG, format="%(asctime)s %(message)s",
                        datefmt="%m/%d/%Y %I:%M:%S %p")

    # setup logger to write to screen as well as writing to log file
    # define a Handler which writes INFO messages or higher to the sys.stderr
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    # set a format which is simpler for console use
    formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
    # tell the handler to use this format
    console.setFormatter(formatter)
    # add the handler to the root logger
    logging.getLogger('').addHandler(console)

    logger.info("")
    logger.info("Start ec2-build")

    if main():
        logger.info("Finished successfully!")
    else:
        logger.fatal("Something bad happened!")

    logger.info("")
    logger.info("-------------------------------------------------------------------------------")
