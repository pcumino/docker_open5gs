#!/bin/bash
#===========================================================#
#File Name:			stop.sh
#Author:			Pedro Cumino
#Email:				pedrolm@cpqd.com.br
#Creation Date:		ter 17 mar 2026 10:13:11
#Last Modified:		ter 17 mar 2026 10:13:12
#Description:
#Args:
#Usage:
#===========================================================#

case "$1" in
    core)     NODE_NAME=sa-deploy         ;;
    gnb)      NODE_NAME=srsgnb_zmq        ;;
    split)    NODE_NAME=srsgnb_split_zmq  ;;
    ue)       NODE_NAME=srsue_5g_zmq      ;;
    ue-split) NODE_NAME=srsue_5g_zmq      ;;
    *)
        echo "Usage: $0 [core|gnb|split|ue|ue-split]"
        exit 1
        ;;
esac

echo "Stopping $NODE_NAME..."
docker compose -f ${NODE_NAME}.yaml down