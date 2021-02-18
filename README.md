# kubernetes-metrics-aggregator

Small multiprocessing-capable server that scrapes metrics inside clusters for you to view outside the cluster (ie. when setup as a service)

## FAQ

### wtf

This thing will:
1. Find pods that have labels setup for scraping
2. Scrape them using a number of workers
3. Aggregate the metrics
4. Give them to you   

### Why not just host Prometheus and federate?

Federation in prometheus needs to be configured and scrapes on its own interval (defined in scrape config). I need something that scrapes only when I tell it to.   

### Is this stable enough for production?

Dunno. Will find out soon enough and update the readme.   

## How to use

If for some reason you want to try it, setup pod labels first. For example:

    metrics-aggregator.apawel.me/endpoint=metrics
    metrics-aggregator.apawel.me/port=9150
    metrics-aggregator.apawel.me/scrape-timeout-seconds=5
    metrics-aggregator.apawel.me/job-name=memcached
    
Metrics aggregator will scrape **all** pods with this label and give you their metrics. Instance is set to pod name and two additional labels are added: pod-namespace, pod-ip   

```
curl 'localhost:80/metrics?job=memcached'
...
memcached_slab_lru_hits_total{lru="warm",slab="1",instance="memcached-session-69b5fdf649-zx8lg",job="memcached",pod-namespace="asdf",pod-ip="10.244.134.119"} 0
memcached_slab_mem_requested_bytes{slab="1",instance="memcached-session-69b5fdf649-zx8lg",job="memcached",pod-namespace="asdf",pod-ip="10.244.134.119"} 546
memcached_slab_warm_age_seconds{slab="1",instance="memcached-session-69b5fdf649-zx8lg",job="memcached",pod-namespace="asdf",pod-ip="10.244.134.119"} 0
memcached_slab_warm_items{slab="1",instance="memcached-session-69b5fdf649-zx8lg",job="memcached",pod-namespace="asdf",pod-ip="10.244.134.119"} 0
memcached_time_seconds{instance="memcached-session-69b5fdf649-zx8lg",job="memcached",pod-namespace="asdf",pod-ip="10.244.134.119"} 1.613644563e+09
memcached_up{instance="memcached-session-69b5fdf649-zx8lg",job="memcached",pod-namespace="asdf",pod-ip="10.244.134.119"} 1
memcached_uptime_seconds{instance="memcached-session-69b5fdf649-zx8lg",job="memcached",pod-namespace="asdf",pod-ip="10.244.134.119"} 180590
memcached_version{version="1.6.9",instance="memcached-session-69b5fdf649-zx8lg",job="memcached",pod-namespace="asdf",pod-ip="10.244.134.119"} 1
memcached_written_bytes_total{instance="memcached-session-69b5fdf649-zx8lg",job="memcached",pod-namespace="asdf",pod-ip="10.244.134.119"} 66260
...
```
