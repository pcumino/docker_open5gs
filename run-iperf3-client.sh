#!/bin/bash
#===========================================================#
#File Name:			run-iperf3-client.sh
#Author:			Pedro Cumino
#Email:				pedrolm@cpqd.com.br
#Creation Date:		ter 17 mar 2026 09:58:19
#Last Modified:		Mon 11 May 2026 02:57:54 PM -03
#Description:
#Args:
#Usage:
#===========================================================#

BITRATE=${1:-6M}
SIMTIME=${2:-60}
INTERVAL=${3:-1}

printf "BITRATE:\t$BITRATE\n"
printf "SIMTIME:\t$SIMTIME seconds\n"
printf "INTERVAL:\t$INTERVAL seconds\n"

#docker exec srsue_5g_zmq iperf3 -c 192.168.100.1 -p 5201
docker exec srsue_5g_zmq iperf3 -c 192.168.100.1 -p 5201 -u -b $BITRATE -t $SIMTIME -i $INTERVAL

