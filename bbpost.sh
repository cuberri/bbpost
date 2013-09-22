#!/bin/bash

#-------------------------------------------------------------------------------
# bbpost control script
# 
# Christophe Uberri <cuberri@gmail.com>
#-------------------------------------------------------------------------------

BB_BASE_DIR=$(cd -P $(dirname $BASH_SOURCE) && pwd)
PY_BIN=python
BB_APP_SCRIPT="${BB_BASE_DIR}/bbpost.py"
BB_PID_FILE="${BB_BASE_DIR}/bbpost.pid"

BB_WATCHDOG_LOG="${BB_BASE_DIR}/watchdog.log"
BB_MAIL_HEADERS_FILE="${BB_BASE_DIR}/headers"

BB_LOG_FILE="${BB_BASE_DIR}/bbpost.log"

BB_OPT_VERBOSE="off"

BB_STATUS_RUNNING=0
BB_STATUS_STOPPED=1
BB_STATUS_UNKNOWN=2

usage(){
    echo "Usage: $0 [options] {start|stop|stopclean|status|restart|healthcheckstatus|watchdog}"
    echo ""
    echo "options :"
    echo "  -h : Print usage"
    echo "  -v : Verbose mode"
    echo ""
    echo "Example : $0 status"
}

print_env(){
    echo "=="
    echo "== BB_BASE_DIR    : ${BB_BASE_DIR}"
    echo "== BB_APP_SCRIPT  : ${BB_APP_SCRIPT}"
    echo "== BB_PID_FILE    : ${BB_PID_FILE}"
    echo "== BB_LOG_FILE    : ${BB_LOG_FILE}"
    echo "=="
    echo ""
}

start(){
    status > /dev/null 2>&1
    
    if [[ $BB_STATUS_RUNNING == $ret ]]; then
        echo "Cannot start application : already running : $(cat ${BB_PID_FILE})"
        echo "If you know the application is not currently running, please delete de pid file ${BB_PID_FILE}"
        return 1
    fi

    if [[ $BB_STATUS_UNKNOWN == $ret ]]; then
        echo "Cannot start application : unknown status..."
        return 2
    fi

    if [[ $BB_STATUS_STOPPED == $ret ]]; then
        echo "Starting application..."
        cd ${BB_BASE_DIR}
        # TODO : deal with stdout / stderr
        ${PY_BIN} ${BB_APP_SCRIPT} >> ${BB_LOG_FILE} 2>&1 &
        echo $! > ${BB_PID_FILE}
        echo "pid saved in ${BB_PID_FILE} : $(cat ${BB_PID_FILE})"
        return 0
    fi

    echo "Could not start application"
    return 3
}

stop(){
    status > /dev/null 2>&1

    if [[ $BB_STATUS_RUNNING == $ret ]]; then
        local pid_pidfile=$(cat ${BB_PID_FILE})
        echo "Sending TERM signal to application with pid : ${pid_pidfile}"
        kill -15 ${pid_pidfile}
        if [[ ! 0 -eq $? ]]; then
            echo "Warning : the kill command failed !"
        fi
        rm ${BB_PID_FILE}
        return 0
    fi

    if [[ $BB_STATUS_STOPPED == $ret ]]; then
        echo "Application seems to be already stopped."
        echo "If you know the application is currently running, please kill it manually."
        return 1
    fi

    if [[ $BB_STATUS_UNKNOWN == $ret ]]; then
        echo "Application is in an unknown status. Please check its status by running this script with the 'status' operation"
        return 1
    fi

    return 1
}

status(){
    local pid_pgrep=$(pgrep -fo ${BB_APP_SCRIPT})

    # STOPPED = no pid file and empty pgrep
    if [[ ! -f ${BB_PID_FILE} && -z "${pid_pgrep}" ]]; then
        echo "[STATUS][STOPPED] No pid file ${BB_PID_FILE} and pgrep return no running process"
        ret=$BB_STATUS_STOPPED
        return
    fi

    # START = pid file and pgrep are consistent
    if [[ -f ${BB_PID_FILE} && ! -z "${pid_pgrep}" && $(cat ${BB_PID_FILE}) == ${pid_pgrep} ]]; then
        echo "[STATUS][RUNNING] pid file and pgrep are consistent"
        ret=$BB_STATUS_RUNNING
        return
    fi

    # UNKNOWN = pidfile and pgrep are not consistent
    echo "[STATUS][UNKNOWN] Could not determine application status (pgrep and pidfile are not consistent)"
    ret=$BB_STATUS_UNKNOWN
}

restart(){
    stop && start
}

healthcheckstatus(){
    local port=$(grep bindport bbpost.cfg | cut -d'=' -f2 | tr -d '\r\n')
    cd ${BB_BASE_DIR}
    curl -XGET "http://localhost:${port}/bbpost/status"
}

watchdog(){
    must_alert=0
    status

    if [[ $BB_STATUS_RUNNING == $ret ]]; then
        echo "[$(date '+%F_%T')] watchdog : bbpost seems to be running correctly"
    elif [[ $BB_STATUS_STOPPED == $ret ]]; then
        echo "[$(date '+%F_%T')] watchdog : bbpost stopped => restart it"
        must_alert=1
        start
    elif [[ $BB_STATUS_UNKNOWN == $ret ]]; then
        echo "[$(date '+%F_%T')] watchdog : bbpost unknown status => restart it"
        must_alert=1
        stopclean
        echo "[$(date '+%F_%T')] watchdog : starting bbpost"
        start
    fi

    echo "[$(date '+%F_%T')] watchdog : finally checking status"
    status

    # alert if we could not be sure of the application status
    if [[ $BB_STATUS_RUNNING != $ret ]]; then
        echo "[$(date '+%F_%T')] watchdog : could not make sure the application is started and could not restart it => sending email to the admin guy"
        must_alert=1
    fi

    if [[ $must_alert -eq 1 ]]; then
        echo "[$(date '+%F_%T')] watchdog : alerting by email"
        tail -n 15 ${BB_WATCHDOG_LOG} > ${BB_WATCHDOG_LOG}.mail.tmp && cat ${BB_MAIL_HEADERS_FILE} ${BB_WATCHDOG_LOG}.mail.tmp | /usr/sbin/sendmail -t && rm ${BB_WATCHDOG_LOG}.mail.tmp
    fi

    return 3
} >> ${BB_WATCHDOG_LOG} 2>&1

stopclean(){
    # if pid file exists, use it to determine the pid and kill it
    if [[ -f ${BB_PID_FILE} ]]; then
        local pid_pidfile=$(cat ${BB_PID_FILE})
        echo "Sending TERM signal to application with pid : ${pid_pidfile}"
        kill -15 ${pid_pidfile}
        if [[ ! 0 -eq $? ]]; then
            echo "Warning : the kill command failed !"
        fi
        echo "removing the pid file ${BB_PID_FILE}"
        rm ${BB_PID_FILE}
    fi

    # check that the process is no longer running
    local pid_pgrep=$(pgrep -fo ${BB_APP_SCRIPT})
    if [[ -z "${pid_pgrep}" ]]; then
        echo "App seems to be killed. We're clean !"
    else
        kill -15 ${pid_pgrep}
        if [[ 0 -eq $? ]]; then
            echo "We killed the pid ${pid_pgrep}, we're clean !"
        else
            echo "Warning : the kill (pid from pgrep) command failed over process ${pid_pgrep} ! We're not clean !"
        fi
    fi
}

while getopts "hv" OPTION
do
    case $OPTION in
        h)
            usage
            exit 0
            ;;
        v)
            BB_OPT_VERBOSE="on"
            ;;
        ?)
            usage
            exit 1
        ;;
    esac
done

# we shift all the options in order to be able to read the mandatory params
shift $(($OPTIND-1))

BB_OPERATION=$1

[[ $# < 1 ]] && usage && exit 1

if [[ "on" == $BB_OPT_VERBOSE ]]; then
    print_env
fi

case $BB_OPERATION in
    healthcheckstatus)
        healthcheckstatus
        exit $?
        ;;
    status)
        status
        exit $?
        ;;
    start)
        start
        exit $?
        ;;
    stop)
        stop
        exit $?
        ;;
    stopclean)
        stopclean
        exit $?
        ;;
    restart)
        restart
        exit $?
        ;;
    watchdog)
        watchdog
        exit $?
        ;;
    ?)
        usage
        exit 1
        ;;
esac
