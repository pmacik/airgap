#!/usr/bin/python
# Provision OpenShift disconnected Cluster

# For this script to work, set the appropriate configuration in config.json file.

# To provision a jenkins job
# to provision disconnected cluster with the version set
# use the above environment variables
# ./ocp-disconnected.py provision

# To clean up the cluster created by a given jenkins job
# (using a given build number)
# ./ocp-disconnected.py cleanup -b 3180


from __future__ import print_function
from jenkinsapi.jenkins import Jenkins
from jenkinsapi.artifact import Artifact
import datetime
import urllib3
from random import randint
import argparse
import json

urllib3.disable_warnings()


with open('config.json') as f:
    config = json.load(f)

ocp_release = config["ocp_release"]
cluster_type_template = config["cluster_type_template"]
jenkins_agent_label = config["jenkins_agent_label"]
jenkins_user = config["user"]["name"]
jenkins_password = config["user"]["api_token"]

if ocp_release is not None:
    launcher_vars = f"installer_payload_image: {ocp_release}"
else:
    launcher_vars = ""

jenkins_url = "https://mastern-jenkins-csb-openshift-qe.cloud.paas.psi.redhat.com"
job_name = "ocp-common/Flexy-install"
kubeconfig_artifact = 'kubeconfig'
kubeadmin_password_artifact = 'kubeadmin-password'
mirror_registry_artifact = 'cluster_info.json'
artifacts_url = "{}/job/{}/{}/artifact//workdir/install-dir/auth/{}"
remove_job_name = "Remove VMs"
templates_repo = 'https://gitlab.cee.redhat.com/aosqe/flexy-templates.git'

jenkins = Jenkins(
    jenkins_url,
    username=jenkins_user,
    password=jenkins_password,
    ssl_verify=False,
    timeout=60
)


def provision_openshift_cluster():
    prefix = (jenkins_user[:6] if len(jenkins_user) >= 6 else jenkins_user)
    now = datetime.datetime.now().strftime('%m%d%H%M')
    instance_name = f'{prefix}{now}'
    print(f'Using Cluster type template - {cluster_type_template}')
    print(f'OCP Release - {ocp_release}')
    params = {'VARIABLES_LOCATION': cluster_type_template,
              'LAUNCHER_VARS': launcher_vars,
              'INSTANCE_NAME_PREFIX': instance_name,
              'JENKINS_AGENT_LABEL': jenkins_agent_label}

    # This will start the job and will return a QueueItem object which
    # can be used to get build results
    job = jenkins[job_name]
    qi = job.invoke(
        build_params=params,
    )

    print(f"Waiting for a build of {job_name} to start...")
    if qi.is_queued():
        qi.block_until_building()

    build = qi.get_build()
    build_number = build.get_number()

    print(
        f"Build #{build_number} of {job_name} is running. Waiting up to 50m for the build to complete.")

    if build.is_running():
        build.block_until_complete(delay=50)

    print(f"Build {build} finished with {build.get_status()}.")

    get_artifacts(
        build_number, build, artifact=kubeconfig_artifact,
        url=artifacts_url)

    get_artifacts(build_number, build,
                  artifact=kubeadmin_password_artifact,
                  url=artifacts_url)

    artifact_obj = get_artifacts(build_number, build,
                                 artifact=mirror_registry_artifact,
                                 url="{}/job/{}/{}/artifact//workdir/install-dir/{}")

    artifact_data = artifact_obj.get_data()
    json_data = json.loads(artifact_data)
    return build_number, json_data['MIRROR_REGISTRY']


def delete_cluster(build_number):
    params = {'BUILD_NUMBER': build_number,
              'TEMPLATES_REPO': templates_repo, 'TEMPLATES_BRANCH': 'master'}
    job = jenkins[remove_job_name]
    qi = job.invoke(
        build_params=params)
    if qi.is_queued() or qi.is_running():
        qi.block_until_complete()


def get_artifacts(build_number, build, dir='.',
                  artifact=None, url=None):
    artifact_obj = Artifact(artifact, url.
                            format(jenkins_url, job_name,
                                   build_number, artifact), build)
    print("Downloading {} to {}".format(artifact, dir+artifact))
    artifact_obj.save("./"+artifact)
    return artifact_obj


parser = argparse.ArgumentParser(
    description="Provision OpenShift Disconnected Cluster")

provision_parser = argparse.ArgumentParser(add_help=False)

delete_parser = argparse.ArgumentParser(add_help=False)
delete_parser.add_argument("-b", "--build-number", dest="build_number", type=int,
                           help="Jenkins job build number", required=True)

sp = parser.add_subparsers(dest="action")
sp.add_parser("provision", parents=[
    provision_parser], help="Provision provisioning of a new OpenShift Disconnected Cluster of a given version, return a # of a Jenkins Build")
sp.add_parser("cleanup", parents=[
    delete_parser], help="Wait for a given Jenkins Build to do the cleanup")

args = parser.parse_args()

if args.action == "provision":
    build_number, mirror_registry = provision_openshift_cluster()
    print('export build_number="{}"'.format(build_number))
    print('export mirror_registry="{}"'.format(mirror_registry))
elif args.action == "cleanup":
    delete_cluster(args.build_number)
else:
    parser.print_help()
