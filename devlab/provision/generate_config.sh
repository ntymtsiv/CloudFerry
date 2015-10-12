#!/bin/bash

SCRIPT=$(basename $0)

error_exit() {
    local message=$1

    if [[ -n $message ]]; then
        echo $message &>2
        echo &>2
    fi

    echo "Usage: ${SCRIPT} --cloudferry-path <path> [--destination <path>] [--src-ip <src-ip>] [--dst-ip <dst-ip>]"

    exit 1
}

while [[ $# -ge 2 ]]; do
    case $1 in
        --cloudferry-path) shift; CF_PATH=$1; shift;;
        --destination) shift; S_PATH=$1; shift;;
        --src-ip) shift; SRC_IP=$1; shift;;
        --dst-ip) shift; DST_IP=$1; shift;;
        *) error_exit "Invalid arg $1";;
    esac
done

[[ -z $CF_PATH ]] && error_exit "Missing --cloudferry-path option"

if [ -z $S_PATH ]; then
    S_PATH=$CF_PATH
fi

result_config=${S_PATH}/configuration.ini

echo "Preparing configuration for CloudFerry"
cp ${CF_PATH}/devlab/config.template ${result_config}

ip_regexp="\b([0-9]{1,3}\.){3}[0-9]{1,3}\b"

#Use icehouse ip if dst ip is not defined
if [ -z $DST_IP ]; then
   DST_IP=$(cat ${CF_PATH}/devlab/config.ini | grep icehouse_ip|\
            grep -oE ${ip_regexp})
fi
#Use grizzly ip if src ip is not defined
if [ -z $SRC_IP ]; then
   SRC_IP=$(cat ${CF_PATH}/devlab/config.ini | grep grizzly_ip|\
            grep -oE ${ip_regexp})
fi

config=${CF_PATH}/devlab/config.ini
if grep -q '^src_ip' $config ; then
    sed -i "s/^src_ip.*/src_ip = ${SRC_IP}/" $config
else
    echo "src_ip = ${SRC_IP}" >> $config
fi
if grep -q '^dst_ip' $config ; then
    sed -i "s/^dst_ip.*/dst_ip = ${DST_IP}/" $config
else
    echo "dst_ip = ${DST_IP}" >> $config
fi

while read key value
do
    value=($value)
    value=${value[1]}
    sed -i "s|<${key}>|${value}|g" ${result_config}
done < ${CF_PATH}/devlab/config.ini

echo "CloudFerry config is saved in ${result_config}"
