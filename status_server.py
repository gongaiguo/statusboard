#!/usr/bin/env python
#
# Copyright 2011 Yunrang Inc. All Rights Reserved.


import sys
import os
import time
import datetime
import threading
import traceback
import socket
import BaseHTTPServer
import psutil
from SocketServer import ThreadingMixIn
import logging
import plugins
from plugins import *
from hope.utils.zk.yrns import YRNSManager
from hope.utils.customlog import *

def ConvertBytes(n):
    K, M, G, T = 1 << 10, 1 << 20, 1 << 30, 1 << 40
    if n >= T:
        return '%.2fT' % (float(n) / T)
    elif n >= G:
        return '%.2fG' % (float(n) / G)
    elif n >= M:
        return '%.2fM' % (float(n) / M)
    elif n >= K:
        return '%.2fK' % (float(n) / K)
    else:
        return '%d' % n


class MachineStatus(object):
    def __call__(self):
        status = []
        status.append(('num cpus', psutil.NUM_CPUS))
        status.append(('cpu used', '%.2f%%' % psutil.cpu_percent()))
        total_phy = psutil.TOTAL_PHYMEM
        used_phy = psutil.used_phymem()
        status.append(('total phy mem', ConvertBytes(total_phy)))
        status.append(('used phy mem', ConvertBytes(used_phy)))
        status.append(('free phy mem', ConvertBytes(total_phy - used_phy)))
        try:
            status.append(('buffers', ConvertBytes(psutil.phymem_buffers())))
            status.append(('cached', ConvertBytes(psutil.cached_phymem())))
        except:
            pass
        total_virt = psutil.total_virtmem()
        used_virt = psutil.used_virtmem()
        status.append(('total virt mem', ConvertBytes(total_virt)))
        status.append(('used virt mem', ConvertBytes(used_virt)))
        status.append(('free virt mem', ConvertBytes(total_virt - used_virt)))
        return status

class ProcessStatus(object):
    def __init__(self, pid=None):
        if pid is None:
            pid = os.getpid()
        self.p = psutil.Process(pid)
    def __call__(self):
        status = []
        status.append(('pid', self.p.pid))
        status.append(('name', self.p.name))
        try:
            status.append(('user', self.p.username))
        except:
            pass
        status.append(('start', self.__CreateTime()))
        status.append(('running time', self.__RunningTime()))
        status.append(('cpu_percent', '%.2f%%' % self.p.get_cpu_percent()))
        status.append(('cpu_time', self.p.get_cpu_times()))
        status.append(('mem_percent', '%.2f%%' % self.p.get_memory_percent()))
        mem_info = self.p.get_memory_info() 
        status.append(('res_mem', ConvertBytes(mem_info[0])))
        status.append(('virt_mem', ConvertBytes(mem_info[1])))
        status.append(('cmd', ' '.join(self.p.cmdline)))
        try:
            status.append(('fd', len(self.p.get_connections())+len(self.p.get_open_files())))
            status.append(('path', os.path.dirname(self.p.exe)))
        except:
            pass
        return status

    def __RunningTime(self):
        d = datetime.datetime.now() - datetime.datetime.fromtimestamp(self.p.create_time)
        return str(d)
    
    def __CreateTime(self):
        return str(datetime.datetime.fromtimestamp(self.p.create_time))


WHITESPACE = '&nbsp;'
NEWLINE = '<br>'

class StatusServer(threading.Thread):
    def __init__(self, \
            logger = None, \
            **kwargs):
        super(StatusServer, self).__init__()
        self.setDaemon(True)
        thttpserver = self
        class RequestHander(BaseHTTPServer.BaseHTTPRequestHandler):
            def do_GET(self):
                try:
                    start = time.time()
                    content = thttpserver.Handle(self.path)
                except:
                    content = sys.exc_info()[:2]
                    thttpserver.logger.error(traceback.format_exc())
                finally:
                    thttpserver.logger.debug("Babysitter cost %d secs to handle %s" % (time.time()-start, self.path))
                    self.send_response(200)
                    self.send_header("content-type", "text/html")
                    self.end_headers()
                    self.wfile.write(content)
                    thttpserver.logger.debug("Babysitter cost %d secs total" % (time.time()-start))
        class ThreadingHttpServer(ThreadingMixIn, BaseHTTPServer.HTTPServer):
            pass

        self.logger = kwargs.get('logger', GloLog())
        self.register_yrns_for_child = kwargs.get('register_yrns_for_child', False)
        self.server_name = kwargs.get('server_name', "status_server")
        self.port = kwargs.get('port', 0)
        self.server_address = (socket.getfqdn(socket.gethostname()), self.port)
        self.httpd = ThreadingHttpServer(('0.0.0.0', self.port), RequestHander)
        self.server_address = (self.server_address[0], self.httpd.server_address[1])
        self.logger.info('Monitor Server %s' % str(self.server_address))
        self.monitors = {}
        self.__RegisterDefault()

        self.yrns_manager = None
        self.yrns_path = kwargs.get('yrns_path', None) 
        self.replica_id = kwargs.get('replica_id', None) 
        self.shard_id = kwargs.get('shard_id', None) 
        self.register_yrns_monitor = kwargs.get('register_yrns_monitor', False)

        self.logger.info("init StatusServer done")

    def AddMonitor(self, name, callback):
        self.logger.info("AddMonitor %s %s" % (name, callback))
        self.monitors[name.upper()] = callback

    def run(self):
        self.logger.info('starting run httpd server')
        if(self.register_yrns_monitor \
            and self.replica_id is not None \
            and self.shard_id is not None):
            self.logger.info('start register yrns thread')
            thread_register_yrns = threading.Thread(target = self.__RegisterYRNS)
            thread_register_yrns.setDaemon(True)
            thread_register_yrns.start()
        self.httpd.serve_forever()

    def Dismiss(self):
        self.httpd.shutdown()

    def Handle(self, req_cmd):
        header = '<head><title>%s</title></head>' % self.server_name
        content = '<body>'
        self.logger.debug('req_cmd: [%s]' % req_cmd)
        req_cmd = req_cmd.strip('/').upper()
        if not req_cmd:
            content += "<h1>%s</h1>" % self.server_name
            for name, callback in self.monitors.iteritems():
                content += '<h2>%s</h2>' % name
                result = callback()
                content += self.__ResultToHtml(result)
        else:
            if req_cmd  in self.monitors:
                callback = self.monitors[req_cmd]
                result = callback()
                content += self.__ResultToHtml(result)
            else:
                content += 'No such cmd'
        content += '</body>'
        return header + content

    def __RegisterDefault(self):
        self.monitors['PROCESS'] = ProcessStatus()
        self.monitors['MACHINE'] = MachineStatus()

    #no subtitle: list with tuples
    #with subtitle: dict
    def __ResultToHtml(self, r):
        html = ''
        format_ = '<key>%s</key>%s:%s<value>%s</value><br>'
        exception_format_ = '<exception>Exception</exception>%s:%s<desc>%s</desc><br>'
        if(len(r) > 1):
            for k, v in r:
                html += format_ % (str(k), WHITESPACE, WHITESPACE, str(v))
        else:
            for stat in r:
                if(stat is not None):
                    if(isinstance(stat, dict) or isinstance(stat, tuple)):
                        if(isinstance(stat, dict)):
                            stat_tmp = [(k, stat[k]) for k in sorted(stat.keys())]
                            stat = stat_tmp
                        for k, v in stat:
                            html += format_ % (str(k), WHITESPACE, WHITESPACE, str(v))
                    else:
                        html += exception_format_ % (WHITESPACE, WHITESPACE, stat)
                else:
                    html += exception_format_ % (WHITESPACE, WHITESPACE, stat)
        html += NEWLINE
        return html

    def __RegisterYRNS(self):
        self.logger.info('start register yrns path')
        try:
            self.yrns_full_path = os.path.join(self.yrns_path, str(self.shard_id))
            self.logger.info(self.yrns_full_path)

            if(self.yrns_manager is None):
                self.yrns_manager = YRNSManager()
            self.yrns_manager.Register(
                    self.yrns_full_path,
                    self.replica_id,
                    self.yrns_manager.SERVICE_MONITOR,
                    self.port,
                    auto_delete = True
                    )
        except Exception,ex:
            self.logger.error(ex)


