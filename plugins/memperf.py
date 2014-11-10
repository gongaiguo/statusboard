#!/usr/bin/env python

import time
import memcache
import threading

Stats_Meta = {
        'bytes':0,
        'limit_maxbytes':0,
        'cmd_get':0,
        'get_hits':0,
        'get_misses':0,
        'cmd_set':0,
        'curr_connections':0,
        'curr_items':0,
        'delete_hits':0,
        'delete_misses':0,
        'evictions':0,
        'stat_resp_time':0,
        'uptime':0,
        'time':0,
        'bytes_read':0,
        'bytes_written':0,
        'reclaimed':0,
        }

Stats_Metric = {
        '*space_usage':0.0,
        '*get_hit_rate':0.0,
        '*get_miss_rate':0.0,
        '*del_hit_rate':0.0,
        '*net_read_rate':0.0,
        '*net_written_rate':0.0,
        'evictions':0,
        'curr_items':0,
        'curr_connections':0,
        'stat_resp_time':0,
        'reclaimed':0,
        }

class HistoryCache(list):
    def __init__(self, size):
        self.size = size
        super(HistoryCache, self).__init__()

    def append(self, item):
        list.append(self, item)
        if(len(self)>self.size):
            del self[0]

class MemcachePerf(threading.Thread):

    def __init__(self, servers, check_interval=15, logger = None):
        print "servers",servers
        super(MemcachePerf, self).__init__()
        if(not isinstance(servers, list)):
            self.servers = servers.split(',')
        else:
            self.servers = servers
        self.statshistory = HistoryCache(2)
        self.perfhistory = HistoryCache(1)
        self.slabshistory = HistoryCache(1)
        self.itemshistory = HistoryCache(1)
        self.check_interval = int(check_interval)
        self.client = memcache.Client(self.servers)

    def setCheckInterval(self, interval):
        self.check_interval = interval

    def __mydivision(self, a, b):
        try:
            return a/b
        except ZeroDivisionError:
            return 0

    def __get_stats(self):
        stats_meta = dict(Stats_Meta)
        stats_metric = dict(Stats_Metric)
        try:
            stats_ = self.client.get_stats()
        except Exception , ex:
            self.perfhistory.append(ex)
            return

        if(len(stats_) <= 0):
            self.perfhistory.append(None)
            return

        stats_ = stats_[0][1]

        for k in stats_meta.keys():
            v = stats_.get(k)
            stats_meta[k] = int(v) if v.isdigit() else v
        self.statshistory.append(stats_meta)
        if(len(self.statshistory)>1):
            last_stats = self.statshistory[-2]
            curr_stats = self.statshistory[-1]
            interval = curr_stats['uptime'] - last_stats['uptime']
            for k in stats_metric.keys():
                stats_metric[k] = curr_stats.get(k)
            stats_metric['*space_usage'] = self.__mydivision( \
                    float(curr_stats['bytes']*100), \
                    float(curr_stats['limit_maxbytes'])
                    )
            stats_metric['*get_hit_rate'] = self.__mydivision( \
                    float(curr_stats['get_hits']-last_stats['get_hits'])*100, \
                    float(curr_stats['cmd_get']-last_stats['cmd_get'])
                    )
            stats_metric['*get_miss_rate'] = self.__mydivision( \
                    float(curr_stats['get_misses']-last_stats['get_misses'])*100, \
                    float(curr_stats['cmd_get']-last_stats['cmd_get'])
                    )
            stats_metric['*del_hit_rate'] = self.__mydivision( \
                    float(curr_stats['delete_hits']-last_stats['delete_hits'])*100, \
                    float(curr_stats['delete_hits']+curr_stats['delete_misses'] \
                    -last_stats['delete_hits']-last_stats['delete_misses'])
                    )
            stats_metric['*net_read_rate'] = self.__mydivision( \
                    float(curr_stats['bytes_read']-last_stats['bytes_read']), \
                    (interval*1024*1024)
                    )
            stats_metric['*net_written_rate'] = self.__mydivision( \
                    float(curr_stats['bytes_written']-last_stats['bytes_written']), \
                    (interval*1024*1024)
                    )
            self.perfhistory.append(stats_metric)
        return 

    def __get_slabs(self):
        try:
            slab_stats_ = self.client.get_slabs()
        except Exception, ex:
            self.slabshistory.append(ex)
            return
        if(len(slab_stats_) <= 0):
            self.slabshistory.append(None)
            return
        self.slabshistory.append(slab_stats_[0][1])
        return

    def __get_items(self):
        try:
            item_stats_ = self.client.get_items()
        except Exception, ex:
            self.itemshistory.append(ex)
            return
        if(len(item_stats_) <= 0):
            self.itemshistory.append(None)
            return
        self.itemshistory.append(item_stats_[0][1])

    def __get_perf(self):
        self.__get_stats()
        self.__get_slabs()
        self.__get_items()


    def run(self):
        while True:
            self.__get_perf()
            time.sleep(self.check_interval)

    def memcached_stats_perf(self):
        return self.perfhistory

    def memcached_stats_slabs(self):
        return self.slabshistory

    def memcached_stats_items(self):
        return self.itemshistory

if __name__ == '__main__':
    m = MemcachePerf(['node079.tsearch.yf.sinanode.com:11211'])
    m.setDaemon(True)
    m.start()
    while True:
        a = m()
        for k, v in a.items():
            print k
            print v
            print '='*100

        time.sleep(3)
