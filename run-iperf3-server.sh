#!/bin/bash
#===========================================================#
#File Name:			run-iperf3-server.sh
#Author:			Pedro Cumino
#Email:				pedrolm@cpqd.com.br
#Creation Date:		ter 17 mar 2026 09:57:43
#Last Modified:		ter 17 mar 2026 09:57:53
#Description:
#Args:
#Usage:
#===========================================================#

docker exec -d upf iperf3 -s -B 192.168.100.1 -p 5201

