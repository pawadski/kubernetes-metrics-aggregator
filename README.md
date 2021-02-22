# kubernetes-metrics-aggregator

Small multiprocessing-capable server that scrapes metrics inside clusters for you to view outside the cluster (ie. when setup as a service)

## FAQ

### wtf

This thing will:
1. Find pods that have labels setup for scraping (through a service account, using the Kubernetes API)
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
    metrics-aggregator.apawel.me/tls-enabled=false
    metrics-aggregator.apawel.me/tls-verify=true
    
Metrics aggregator will scrape **all** pods with this label and give you their metrics. Instance is set to pod name and two additional labels are added: pod-namespace, pod-ip   

```
curl 'localhost:80/metrics?job=memcached'
...
# HELP promhttp_metric_handler_requests_total Total number of scrapes by HTTP status code.
# TYPE promhttp_metric_handler_requests_total counter
promhttp_metric_handler_requests_total{code="200",instance="memcached-db-54c6dc7658-9zlwq",job="memcached",pod-namespace="somenamespace",pod-ip="10.244.137.60"} 23
promhttp_metric_handler_requests_total{code="200",instance="memcached-db-7788765cbb-clrqg",job="memcached",pod-namespace="someothernamespace",pod-ip="10.244.142.192"} 18
promhttp_metric_handler_requests_total{code="200",instance="memcached-session-69b5fdf649-zx8lg",job="memcached",pod-namespace="someothernamespace",pod-ip="10.244.134.119"} 18
promhttp_metric_handler_requests_total{code="500",instance="memcached-db-54c6dc7658-9zlwq",job="memcached",pod-namespace="somenamespace",pod-ip="10.244.137.60"} 0
promhttp_metric_handler_requests_total{code="500",instance="memcached-db-7788765cbb-clrqg",job="memcached",pod-namespace="someothernamespace",pod-ip="10.244.142.192"} 0
promhttp_metric_handler_requests_total{code="500",instance="memcached-session-69b5fdf649-zx8lg",job="memcached",pod-namespace="someothernamespace",pod-ip="10.244.134.119"} 0
...
```

Then in Prometheus config:   

```
...
  - job_name: 'k8s-metrics-aggregator-memcached'
    honor_labels: true
    metrics_path: "/metrics?job=memcached"
    static_configs:
    - targets:
      - 'localhost:80'
...
```

You get the idea.  

### Environment

- LOG_LEVEL: log level, default info
- CACHE_UPDATE_INTERVAL: how often to poll kubernetes API for pods, default 10 seconds
- SERVER_WORKERS: number of worker processes supporting the webserver (ie. to answer requests), default 2
- CLIENT_WORKERS: number of worker processes spawned by the server to fetch metrics, default 2
