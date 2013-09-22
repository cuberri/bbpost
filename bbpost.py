#!/usr/bin/env python

#
# Author:: Christophe Uberri <cuberri@gmail.com>
#
# Copyright 2013, Christophe Uberri <cuberri@gmail.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

# ------------------------------------------------------------------------------
# Baby Bitbucket Post is a python server which waits for Bitbucket notifications
# and launch hooks configured in its config file
# ------------------------------------------------------------------------------

import time
import Queue
import os
import sys
import subprocess
import threading
import shlex
import ConfigParser
import logging
import json
import urlparse
import abc
from bottle import route, get, post, request, run, abort, error, HTTPResponse, HTTP_CODES

# ------------------------------------------------------------------------------
# GLOBAL
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# API
# ------------------------------------------------------------------------------

@get(path='/bbpost/status')
def callstatus():
    """Simple health check. Can be used for smoke tests for ex.
    """
    return "online"

@get(path='/bbpost/job/status')
def calljobstatus():
    """Check the job queue status
    """
    return job_queue.qsize()

@get(path='/bbpost/version')
def callversion():
    """Simple health check. Can be used for smoke tests for ex.
    """
    return 'version: {0} changeSet:{1} changeSetDate: {2}'.format(version, changeset, changesetdate)

@post(path='/bbpost/bbpush')
def callcmd():
    """Receive a bitbucket push notification

      - Parse the request body as json

    Example :
    ---------

    - Request :

    $ curl -XPOST "http://localhost:5555/bbpush" -d "payload={...}"
    With payload (must url encode !) :
        {
            "canon_url": "https://bitbucket.org",
            "commits": [
                {
                    "author": "marcus",
                    "branch": "featureA",
                    "files": [
                        {
                            "file": "somefile.py",
                            "type": "modified"
                        }
                    ],
                    "message": "Added some featureA things",
                    "node": "d14d26a93fd2",
                    "parents": [
                        "1b458191f31a"
                    ],
                    "raw_author": "Marcus Bertrand <marcus@somedomain.com>",
                    "raw_node": "d14d26a93fd28d3166fa81c0cd3b6f339bb95bfe",
                    "revision": 3,
                    "size": -1,
                    "timestamp": "2012-05-30 06:07:03",
                    "utctimestamp": "2012-05-30 04:07:03+00:00"
                }
            ],
            "repository": {
                "absolute_url": "/marcus/project-x/",
                "fork": false,
                "is_private": true,
                "name": "Project X",
                "owner": "marcus",
                "scm": "hg",
                "slug": "project-x",
                "website": ""
            },
            "user": "marcus"
        }
    """
    # get request data
    reqpayload = request.params["payload"]
    logging.debug('Got payload from request : %s', reqpayload)
    if not reqpayload:
        return errorhttpresponse(400, 'No payload in the request params')

    entity = json.loads(reqpayload)
    logging.info('Got update from Bitbucket for project [%s]', entity["repository"]["slug"])

    # create job
    logging.info('Creating and submitting a Job for project [%s]', entity["repository"]["slug"])
    job_executor.submit_job(Job(entity, config))

    return HTTPResponse(status=203)

# ------------------------------------------------------------------------------
# ERRORS
# ------------------------------------------------------------------------------

@error(401)
def error401(error):
    return doerror(error)

@error(404)
def error404(error):
    return doerror(error)

@error(405)
def error405(error):
    return doerror(error)

@error(415)
def error415(error):
    return doerror(error)

@error(500)
def error500(error):
    return doerror(error)

@error(504)
def error504(error):
    return doerror(error)

def errorhttpresponse(status, msg):
    return HTTPResponse(json.dumps({'error': {'status': status, 'statusstr': HTTP_CODES[status], 'msg': msg}}, sort_keys=True, indent=4, separators=(',', ': ')), status, headers={"Content-Type":"application/json"})

def doerror(error):
    return errorhttpresponse(int(error.status[:3]), error.body)

# ------------------------------------------------------------------------------
# Job Management
# ------------------------------------------------------------------------------
class Job(object):
    """Job data and common behavior"""

    def __init__(self, bbdict, config):
        """Build a Job based on the dictionary entity sent by BitBucket
            - bbdict : the dictionay based entity describing the project
            - config : the config from which we extract the needed data for scm etc.
        """
        self.project=bbdict['repository']['slug']
        self.workspace=config.get(self.project, 'workspace')
        self.branch=config.get(self.project, 'branch')
        self.update=config.getboolean(self.project, 'update')

        # check workspace dir
        if not os.path.exists(self.workspace):
            logging.debug("project[%s] The workspace path does not exist : create it", self.project)
            os.makedirs(self.workspace)

        # get a repo instance based on the scm used for this project
        self.repository=Repository.new(
            bbdict['repository']['scm'],
            config.get(bbdict['repository']['scm'], 'bin'),
            urlparse.urljoin(bbdict['canon_url'], bbdict['repository']['absolute_url']),
            os.path.normpath(os.path.join(self.workspace, self.project)))

        # only store the commits on the configured branch of the project
        self.commits=filter(lambda commit: commit['branch']==self.branch, bbdict['commits'])
        self.hook=config.get(self.project, 'hook')

    def launch(self):
        if self._should_launch():
            if self.update:
                logging.debug("project[%s] Update is enabled in config", self.project)
                self._clone_or_pull()
            elif not os.path.exists(self._project_dir()):
                logging.debug("project[%s] Update is disabled in config but we need the local project workspace => create it", self.project)
                os.makedirs(self._project_dir())
            #self._pre_hook()
            self._launch_hook()
            #self._post_hook()
            logging.info("project[%s] Hook executed", self.project)
        else:
            logging.info('project[%s] No need to launch the hook process', self.project)

    def _clone_or_pull(self):
        logging.debug('project[%s] Updating Job', self.project)
        if not os.path.exists(self._project_dir()):
            logging.debug('%s does not exist => cloning the repository', self._project_dir())
            # clone at the specified revision/branch
            self.repository.clone(self.branch)
        else:
            logging.debug('%s exists => pulling the repository', self._project_dir())
            # pull and update at the specified revision/branch
            self.repository.pull(self.branch)
        
        self.repository.update(self.branch)

    def _launch_hook(self):
        try:
            logging.info('project[%s] Launching hook : %s', self.project, self.hook)
	    # TODO : need to spawn
            ret = subprocess.Popen(shlex.split(self.hook), cwd=self.repository.local_target).wait()
            logging.debug('Command [%s] exited with return code [%s]' % (self.hook, ret))
            return ret
        except OSError as e:
            logging.error('Could not execute command process : OSError({0}): {1} !'.format(e.errno, e.strerror))
        except ValueError as e:
            logging.error('Could not execute command process : ValueError({0}) !'.format(str(e)))

    def _should_launch(self):
        logging.debug('project[%s] Checking whether to launch the hook', self.project)
        # launch the job hook only if we detect a commit on the configured branch for the project
        return len(self.commits) > 0

    def _project_dir(self):
        return os.path.join(self.workspace, self.project)

class JobExecutor(threading.Thread):
    """todo doc"""
    def __init__(self, q):
        threading.Thread.__init__(self)
        self.__queue = q

    def run(self):
        while True:
            logging.debug("Waiting for %s secs before checking queue...", CONSUME_JOB_INTERVAL)
            time.sleep(CONSUME_JOB_INTERVAL)
            self._consume()

    def submit_job(self, job):
        logging.debug("Submitting job for project : [%s]", job.project)
        try:
            self.__queue.put(job, block=True, timeout=SUBMIT_JOB_TIMEOUT)
            logging.info("Job for project : [%s] submitted. There are now [%s] jobs in queue", job.project, self.__queue.qsize())
        except Queue.Full:
            logger.error("Damn it ! The job queue is full, come back later please !")

    def _consume(self):
        try:
            job = self.__queue.get_nowait()
            logging.debug("Got a job from queue  for project [%s], launch it !", job.project)
            job.launch()
        except Queue.Empty:
            logging.debug("No job in queue... Maybe next time !")

# ------------------------------------------------------------------------------
# Repository management
# ------------------------------------------------------------------------------
class Repository(object):
    """Abstract base class for repository management"""
    __metaclass__ = abc.ABCMeta

    def __init__(self, bin, remote_url, local_target):
        self.bin=bin
        self.remote_url=remote_url
        self.local_target=local_target

    @staticmethod
    def new(type, bin, remote_url, local_target):
        """static factory method"""
        if type=='hg' or type=='mercurial':
            return MercurialRepository(bin, remote_url, local_target)

    @abc.abstractmethod
    def clone(self, rev):
        """clone the specified revision from remote_url to local_target"""
        proc = process
        return

    @abc.abstractmethod
    def pull(self, rev):
        """pull for changes from remote_url to local_target at the specified revision"""
        return

    @abc.abstractmethod
    def update(self, rev):
        """update the local repo to the specified revision"""
        return

    def _callcmd(self, cmd, cwd=None):
        try:
            #ret = subprocess.Popen(shlex.split(cmd), cwd=cwd).wait()
            ret = subprocess.Popen(cmd, shell=True, cwd=cwd).wait()
            logging.debug('Command [%s] exited with return code [%s]' % (cmd, ret))
            return ret
        except OSError as e:
            logging.error('Could not execute command process : OSError({0}): {1} !'.format(e.errno, e.strerror))
        except ValueError as e:
            logging.error('Could not execute command process : {0} !'.format(str(e)))


class MercurialRepository(Repository):
    """Mercurial based repository"""
    def clone(self, rev):
        cmd = '{0} clone --rev {1} --noupdate {2} {3}'.format(self.bin, rev, self.remote_url, self.local_target)
        logging.info("Cloning repository with : %s", cmd)
        self._callcmd(cmd)

    def pull(self, rev):
        cmd = '{0} pull --rev {1}'.format(self.bin, rev)
        logging.info("Pulling repository with : %s", cmd)
        self._callcmd(cmd, cwd=self.local_target)

    def update(self, rev):
        cmd = '{0} update --clean --rev {1}'.format(self.bin, rev)
        logging.info("Updating repository with : %s", cmd)
        self._callcmd(cmd, cwd=self.local_target)

# ------------------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------------------
if __name__ == '__main__':
    #
    # Init config and http
    #
    config = ConfigParser.RawConfigParser()
    config.read('bbpost.cfg')

    version = config.get('bbpost', 'version')
    changeset = config.get('bbpost', 'changeSet')
    changesetdate = config.get('bbpost', 'changeSetDate')

    CONSUME_JOB_INTERVAL = config.getint('bbpost', 'consume_job_interval')
    SUBMIT_JOB_TIMEOUT = config.getint('bbpost', 'submit_job_timeout')

    logging.basicConfig(
        level=getattr(logging, config.get('logging', 'level').upper(), None),
        format=config.get('logging', 'format')
    )

    bindaddress = config.get('bottle', 'bindaddress')
    bindport = config.getint('bottle', 'bindport')

    #
    # Init job queue and a JobExecutor
    #
    job_queue = Queue.Queue()

    # TODO : Use a ThreadPool or find a way to spawn processes with a shared queue
    logging.info("=\n= Starting Job Executor\n=")
    job_executor = JobExecutor(job_queue)
    job_executor.daemon = True
    job_executor.start()

    #
    # Start the http server
    #
    logging.info("=\n= Starting bottle bbpost on %s:%s\n=", bindaddress, bindport)
    run(host=bindaddress, port=bindport, reloader=config.getboolean('bottle', 'reloader'), debug=config.getboolean('bottle', 'debug'))
