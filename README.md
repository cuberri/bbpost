Description
===========

bbpost (Bitbucket POST) is a simple python server which waits for Bitbucket 
notifications about project updates and launch some configured hooks.

This is actually a backend for the 
[Bitbucket POST service](https://confluence.atlassian.com/display/BITBUCKET/POST+Service+Management).

It is built on top of the [Python Bottle Web Framework](http://bottlepy.org/docs/dev/index.html).

Requirements
============

* Python 2.6+

Security Considerations
=======================

* Bitbucket supports HTTP Basic authentication for its POST service. However, 
bbpost server does support it yet. In the meantime, I strongly encourage users 
to restrict the service access to the Bitbucket IP address 
(see [Bitbucket documentation](https://confluence.atlassian.com/display/BITBUCKET/POST+Service+Management)).

* bbpost executes the configured hooks as the user which it has been run with.
Be sure to apply the restrictions you may consider suitable for your system.

Usage
=====

## server

    $ git clone https://github.com/cuberri/bbpost.git
    Cloning into 'bbpost'...
    [clipped...]

    $ cd bbpost && ./bbpost start
    Starting application...
    pid saved in /home/chris/workspace/bbpost/bbpost.pid : 3423

## testing client request

The following curl request mimic the Bitbucket behavior with the payload got from 
the Bitbucket documentation. Because I do care for the health of you eyes, I 
clipped the request payload, you'll find the complete example in the file named 
`sample.txt` of this repo.

    $ curl -X POST "http://localhost:8055/bbpost/bbpush" -d "payload=[...clipped...]"
    > POST /bbpost/bbpush HTTP/1.1
    > User-Agent: curl/7.27.0
    > Host: localhost:8055
    > Accept: */*
    > Content-Length: 1122
    > Content-Type: application/x-www-form-urlencoded
    > Expect: 100-continue
    >

    < HTTP/1.0 202 Accepted
    < Date: Mon, 20 May 2013 12:24:12 GMT
    < Server: WSGIServer/0.1 Python/2.7.3
    < Content-Length: 0
    < Content-Type: text/html; charset=UTF-8
    <

**Note :**

This request creates a job that will launch the preconfigured demo project 
`project-x` (see the cmdsrv.cfg config file).

## bbpost behind Apache2

You may consider usging an Apache2 web server backed by bbpost. Here is an 
example of a vhost configuration in that purpose :

```xml
<VirtualHost *:80>
    ProxyPass /bbpost http://localhost:8055/bbpost
    ProxyPassReverse /bbpost http://localhost:8055/bbpost
    ProxyRequests Off
    ProxyPreserveHost On

    # 131.103.20.165 131.103.20.166 : Bitbucket
    # your_host_name : local machine
    <Proxy http://localhost:8055/bbpost*>
        Order deny,allow
        Allow from 131.103.20.165
        Allow from 131.103.20.165
        Allow from 127.0.0.1
        Allow from localhost
        Allow from <your_host_name>
        Deny from all 
    </Proxy>
</VirtualHost>
```

Jobs Configuration
==================

The bbpost configuration is quite simple and is all grouped in the `cmdsrv.cfg`
file. The format of this file is a simple python-style (similar to th Windows 
INI files).

Please, refer to the comments inside the `cmdsrv.cfg` file for details.

Watchdog function
=================

A watchdog function exists in the `bbpost.sh` bash script. Its purpose is to
keep the application running and mail a user if the application has been
restarted or is in an unknown state.

The function uses a `headers` file to set up the email configuration stuff
(subject, sender and recipient).

One could cron this function every minute to be sure the server is always
running, as in the following example :

    * * * * * /bin/bash /opt/local/bbpost/bbpost.sh watchdog

I know, there is plainty of other methods to monitor an application, but this
one is quite simple :)

Development and Notes
=====================

A major drawback of the way jobs are set up is that you can only 
configure **one job per project**. That means you cannot configure one job for 
a project `X` on a branch `A`, and another job for the same project `X` on a 
branch `B`.


It is important to note that this piece of software has initially been used as a
continuous delivery server for small projects on small boxes.


The [Python Bottle Web Framework](http://bottlepy.org/docs/dev/index.html)
is used 'as is'. For example, it runs on the built-in [wsgiref WSGIServer](http://docs.python.org/2/library/wsgiref.html#module-wsgiref.simple_server)
by default. Considering that, according to the [bottle documentation](http://bottlepy.org/docs/dev/tutorial.html#deployment) :

> This non-threading HTTP server is perfectly fine for development and early 
> production, but may become a performance bottleneck when server load 
> increases.

Have a look at the [bottle documentation](http://bottlepy.org/docs/dev/tutorial.html#deployment)
for further details on running an other (and multithreaded :)) server.

Feel free to improve/propose if more advanced usages are needed :)

License and Author
==================

* Author: Christophe Uberri (<cuberri@gmail.com>)

Copyright: 2013, Christophe Uberri

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
