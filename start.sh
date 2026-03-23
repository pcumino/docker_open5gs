#!/bin/bash
#===========================================================#
#File Name:      start.sh
#Author:         Pedro Cumino
#Email:          pedrolm@cpqd.com.br
#Creation Date:  ter 17 mar 2026
#Description:    Unified node starter
#Usage:          ./start.sh [core|gnb|split|ue|ue-split]
#===========================================================#

UE_SPLIT=false

case "$1" in
    core)     NODE_NAME=sa-deploy         ;;
    gnb)      NODE_NAME=srsgnb_zmq        ;;
    split)    NODE_NAME=srsgnb_split_zmq  ;;
    ue)       NODE_NAME=srsue_5g_zmq      ;;
    ue-split) NODE_NAME=srsue_5g_zmq; UE_SPLIT=true ;;
    *)
        echo "Usage: $0 [core|gnb|split|ue|ue-split]"
        exit 1
        ;;
esac

# For split-mode UE, override the ZMQ DU endpoint so srsUE connects to
# the DU container instead of the monolithic gNB.
if [ "$UE_SPLIT" = "true" ]; then
    source .env
    export SRS_ZMQ_DU_IP=$SRS_DU_IP
fi

echo "Stopping $NODE_NAME..."
docker compose -f ${NODE_NAME}.yaml down

echo "Starting $NODE_NAME..."
docker compose -f ${NODE_NAME}.yaml up -d

if [ "$NODE_NAME" == "srsue_5g_zmq" ]; then
    echo "Installing iperf3 on $NODE_NAME..."
    docker exec $NODE_NAME apt-get install iperf3 -y
fi

if [ "$NODE_NAME" == "srsgnb_split_zmq" ]; then
    read -p "Attach to which container? [cu|du] (default: du) " attach_target
    attach_target=${attach_target:-du}
    if [[ "$attach_target" == "cu" ]]; then
        docker container attach srscu_zmq
    else
        docker container attach srsdu_zmq
    fi
else
    read -p "Attach node? [Y|n] " attach_node
    if [[ ! "$attach_node" =~ ^[Nn]$ ]]; then
        docker container attach $NODE_NAME
    fi
fi
