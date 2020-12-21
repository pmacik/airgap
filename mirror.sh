#!/bin/bash -xe

#MIRROR_REGISTRY

CATALOG_IMAGE_REGISTRY=${CATALOG_IMAGE_REGISTRY:-quay.io}
CATALOG_IMAGE_ORG=${CATALOG_IMAGE_ORG:-$QUAY_USERNAME}
CATALOG_IMAGE_NAME=${CATALOG_IMAGE_NAME:-servicebinding-operator}
CATALOG_IMAGE_TAG=${CATALOG_IMAGE_TAG:-index}
PRODUCT_NAME=${PRODUCT_NAME:-binding}

CATALOG_INDEX_IMAGE=$CATALOG_IMAGE_REGISTRY/$CATALOG_IMAGE_ORG/$CATALOG_IMAGE_NAME:$CATALOG_IMAGE_TAG
MIRROR_REPO=$MIRROR_REGISTRY/$CATALOG_IMAGE_ORG/$CATALOG_IMAGE_NAME
MIRROR_INDEX_IMAGE=$MIRROR_REPO:$CATALOG_IMAGE_TAG

REGISTRY_USER="${REGISTRY_USER:-dummy}"
REGISTRY_PASSWORD="${REGISTRY_PASSWORD:-dummy}"

function mirror_images() {
  oc image mirror $1 --insecure --keep-manifest-list  
}

function check_if_nodes_ready() {
  while [ $(oc get nodes | grep -E '\sReady\s' | wc -l) != 5 ]; do
    echo 'waiting for nodes to restart with status Ready'
    sleep 5
  done
}


# Run the below command in case of any clean resources are required in a cluster
oc patch OperatorHub cluster --type json -p '[{"op": "add", "path": "/spec/disableAllDefaultSources", "value": true}]'
echo "oc patch to operatorhub is completed"

oc registry login --registry $MIRROR_REGISTRY --auth-basic=$REGISTRY_USER:$REGISTRY_USER --insecure=true
echo "oc logged into registry"

# mirroring the index image
podman pull $CATALOG_INDEX_IMAGE
CATALOG_IMAGE_DIGEST=$(podman inspect $CATALOG_INDEX_IMAGE | jq -cr ".[0].RepoDigests | to_entries[] | select(.value | contains(\"${CATALOG_IMAGE_REGISTRY}/${CATALOG_IMAGE_ORG}\")).value")
manifests_result="$(oc image mirror $CATALOG_IMAGE_DIGEST $MIRROR_REPO --insecure)"

oc adm catalog mirror $CATALOG_IMAGE_DIGEST $MIRROR_INDEX_IMAGE --to-manifests=$CATALOG_IMAGE_NAME-manifests --filter-by-os="linux/amd64" --insecure

oc apply -f $CATALOG_IMAGE_NAME-manifests/imageContentSourcePolicy.yaml

grep $PRODUCT_NAME $CATALOG_IMAGE_NAME-manifests/mapping.txt > $CATALOG_IMAGE_NAME-manifests/$PRODUCT_NAME.txt

sed -i -e 's/\(.*\)\(:.*$\)/\1/' $CATALOG_IMAGE_NAME-manifests/$PRODUCT_NAME.txt

while read mapping; do
  for images in $mapping; do
    FROM_IMAGE=$(cut -d'=' -f1 <<< $images)
    TO_IMAGE=$(cut -d'=' -f2 <<< $images)
    #mirror_images $FROM_IMAGE $TO_IMAGE 
    mirror_images $images
  done
done < $CATALOG_IMAGE_NAME-manifests/$PRODUCT_NAME.txt

AUTHFILE=$(readlink -m .authfile)
podman login --authfile $AUTHFILE --username $REGISTRY_USER --password $REGISTRY_PASSWORD $MIRROR_REGISTRY --tls-verify=false

#sleep 15
check_if_nodes_ready

echo "Use install.sh from SBO repo to install SBO from a given catalog index image:"
echo 
echo "curl -s https://raw.githubusercontent.com/redhat-developer/service-binding-operator/master/install.sh | OPERATOR_INDEX_IMAGE=$CATALOG_IMAGE_DIGEST CATSRC_NAME=$CATALOG_IMAGE_NAME CATSRC_NAMESPACE=openshift-marketplace DOCKER_CFG=$AUTHFILE /bin/bash -s"