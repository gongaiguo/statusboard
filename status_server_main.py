#!/usr/bin/env python
#encoding=utf-8
from status_server import StatusServer
import plugins
from plugins import *
import time
from base.gflags import *
import daemon
from daemon import pidfile
import sys
import os.path
from hope.utils.customlog import *

#TODO: add logger
#TODO: add json output
#TODO: support multi memcached, the feature of plugin

logger = None

def run():
    """init status server, and run in a dead loop """

    global logger
    logger.info("inter run")

    statusserver = StatusServer(logger = logger, **FLAGS.FlagValuesDict())

    if(FLAGS.plugin_module \
        and FLAGS.plugin_class \
        and FLAGS.plugin_handlers):
        plugin_module = getattr(plugins, FLAGS.plugin_module) 
        plugin_class = getattr(plugin_module, FLAGS.plugin_class)
        plugin_inst = plugin_class(*FLAGS.plugin_params)
        for handler in FLAGS.plugin_handlers:
            stats_perf = getattr(plugin_inst, handler)
            statusserver.AddMonitor(handler, stats_perf)
    else:
        print "not enough params"
        sys.exit(1)

    try:
        statusserver.setDaemon(True)
        statusserver.start()
        plugin_inst.setDaemon(True)
        plugin_inst.start()
    except Exception:
        statusserver.Dismiss()
        sys.exit()
    while True:
        try:
            time.sleep(1)
        except Exception, ex:
            print ex
            statusserver.Dismiss()
            sys.exit()

def main():
    "init system args"
    DEFINE_bool('daemon', False, 'daemonizer flag')
    DEFINE_integer('port', 9000, 'port of this server')
    DEFINE_integer('replica_id', None, 'replica id')
    DEFINE_integer('shard_id', None, 'shard id')
    DEFINE_string('plugin_module', None, 'module of plugin to use')
    DEFINE_string('plugin_class', None, 'class of plugin to use')
    DEFINE_string('name', 'StatusServer', 'name of this server')
    DEFINE_string('logfile',
                   os.path.join(
                        os.path.dirname(os.path.abspath(sys.argv[0])),
                        str("%s.log" % os.path.basename(sys.argv[0]))
                        ),
                   'log file dir path')
    DEFINE_string('pidfile', "/tmp/status_server.pid", 'pid file dir path')
    DEFINE_string('yrns_path', None, 'yrns path')
    DEFINE_list('plugin_params', None, 'params of the plugin init')
    DEFINE_list('plugin_handlers', None, 'handlers to load of the plugin init')
    DEFINE_bool('register_yrns_monitor', False, 'if register yrns monitor path')

    #DEFINE_bool('register_rpc', False,'if register rpc yrns_path for client')

    try:
        argv = FLAGS(sys.argv)
    except FlagsError, ex:
        print "%s\\nusage: %s ARGS\\n %s" % (ex, sys.argv[-1], FLAGS)

    _pidfile = pidfile.TimeoutPIDLockFile(FLAGS.pidfile, 10)

    sys.stdout = open(FLAGS.logfile, 'a+')
    sys.stderr = open(str("%s.error" % FLAGS.logfile), 'a+')
    #_stdout = open('/dev/stdout', 'a+')
    #_stderr = open('/dev/stderr', 'a+')
    global logger
    logger = GloLog()

    if(FLAGS.daemon):
        print 'inter daemon'
        try:
            daemon_ = daemon.DaemonContext()
            daemon_.stdout = sys.stdout
            daemon_.stderr = sys.stderr
            daemon_.pidfile = _pidfile
            daemon_.open()
            run()
        except Exception, ex:
            print ex
    else:
        run()

if __name__ == '__main__':
    main()

