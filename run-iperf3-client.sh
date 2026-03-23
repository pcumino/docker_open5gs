#!/bin/bash
#===========================================================#
#File Name:			run-iperf3-client.sh
#Author:			Pedro Cumino
#Email:				pedrolm@cpqd.com.br
#Creation Date:		ter 17 mar 2026 09:58:19
#Last Modified:		seg 23 mar 2026 18:58:37
#Description:
#Args:
#Usage:
#===========================================================#

#docker exec srsue_5g_zmq iperf3 -c 192.168.100.1 -p 5201
docker exec srsue_5g_zmq iperf3 -c 192.168.100.1 -p 5201 -u -b 6M -t 60 -i 1
