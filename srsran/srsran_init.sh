#!/bin/bash

# BSD 2-Clause License

# Copyright (c) 2020-2025, Supreeth Herle
# All rights reserved.

# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:

# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.

# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.

# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

export IP_ADDR=$(awk 'END{print $1}' /etc/hosts)

mkdir -p /etc/srsran

deploy_binary=""
deploy_config=""

if [[ -z "$COMPONENT_NAME" ]]; then
	echo "Error: COMPONENT_NAME environment variable not set"; exit 1;
elif [[ "$COMPONENT_NAME" =~ ^(gnb[[:digit:]]*$) ]]; then
	echo "Configuring component: '$COMPONENT_NAME'"
	cp /mnt/srsran/${COMPONENT_NAME}.yml /etc/srsran/gnb.yml
        deploy_binary="gnb"
        deploy_config="/etc/srsran/gnb.yml"
elif [[ "$COMPONENT_NAME" =~ ^(gnb_zmq[[:digit:]]*$) ]]; then
	echo "Configuring component: '$COMPONENT_NAME'"
	cp /mnt/srsran/${COMPONENT_NAME}.yml /etc/srsran/gnb.yml
        deploy_binary="gnb"
        deploy_config="/etc/srsran/gnb.yml"
elif [[ "$COMPONENT_NAME" =~ ^(cu_zmq[[:digit:]]*$) ]]; then
	echo "Configuring component: '$COMPONENT_NAME'"
	cp /mnt/srsran/cu_zmq.yml /etc/srsran/cu.yml
        deploy_binary="srscu"
        deploy_config="/etc/srsran/cu.yml"
elif [[ "$COMPONENT_NAME" =~ ^(du_zmq[[:digit:]]*$) ]]; then
	echo "Configuring component: '$COMPONENT_NAME'"
	cp /mnt/srsran/du_zmq.yml /etc/srsran/du.yml
        deploy_binary="srsdu"
        deploy_config="/etc/srsran/du.yml"
else
	echo "Error: Invalid component name: '$COMPONENT_NAME'"
fi

cp /mnt/srsran/qos.yml /etc/srsran/qos.yml

sed -i 's|PLMN|'$MCC''$MNC'|g' ${deploy_config}
sed -i 's|AMF_IP|'$AMF_IP'|g' ${deploy_config}
sed -i 's|SRS_GNB_IP|'$SRS_GNB_IP'|g' ${deploy_config}
sed -i 's|SRS_CU_IP|'${SRS_CU_IP:-$SRS_GNB_IP}'|g' ${deploy_config}
sed -i 's|SRS_DU_IP|'${SRS_DU_IP:-$SRS_GNB_IP}'|g' ${deploy_config}
sed -i 's|SRS_UE_IP|'$SRS_UE_IP'|g' ${deploy_config}
sed -i 's|TAC|'$TAC'|g' ${deploy_config}

# For dbus not started issue when host machine is running Ubuntu 22.04
service dbus start && service avahi-daemon start

cd /mnt/srsran
if [[ "$deploy_binary" == "gnb" ]]; then
	exec gnb -c ${deploy_config} -c /etc/srsran/qos.yml $@
elif [[ "$deploy_binary" == "srscu" ]]; then
	if ! command -v srscu >/dev/null 2>&1; then
		echo "Error: srscu binary not found in container image"; exit 1;
	fi
	exec srscu -c ${deploy_config} $@
elif [[ "$deploy_binary" == "srsdu" ]]; then
	if ! command -v srsdu >/dev/null 2>&1; then
		echo "Error: srsdu binary not found in container image"; exit 1;
	fi
	exec srsdu -c ${deploy_config} $@
else
	echo "Error: Unsupported deployment binary '$deploy_binary'"; exit 1;
fi

# Sync docker time
#ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
