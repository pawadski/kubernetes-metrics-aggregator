#!/usr/bin/env python3 

import multiprocessing, requests, os, time 
from datetime import datetime 
from kubernetes import client, config

from http.server import HTTPServer
from http.server import BaseHTTPRequestHandler

# Configs can be set in Configuration class directly or using helper utility
config.load_incluster_config()

manager = multiprocessing.Manager()

pod_job_cache = manager.dict( { 'cache': None } )
# pod_job_cache = { '_bare': True }

default_pod_labels = {
    'endpoint': 'metrics',
    'port': '80',
    'scrape-timeout-seconds': '5',
    'job-name': None
}

log_levels = {
    'debug': 4,
    'info': 3,
    'warning': 2,
    'error': 1
}

settings = {
    'log-level': log_levels[ os.getenv('LOG_LEVEL', 'info') ],
    'cache-update-interval': int(os.getenv('CACHE_UPDATE_INTERVAL', '10')),
    'server-workers': int(os.getenv('SERVER_WORKERS', '2')),
    'client-workers': int(os.getenv('CLIENT_WORKERS', '2'))
}

# logging function
def log(level, message):
    if log_levels[level] <= settings['log-level']:
        if type(message) is list:
            for item in message:
                print (f'{datetime.now():%Y-%m-%d %H:%M:%S%z} {level}:', item)
        else:
            print (f'{datetime.now():%Y-%m-%d %H:%M:%S%z} {level}:', message)

def parse_labels(metadata):
    parsed_labels = dict(default_pod_labels)

    if metadata.labels is None:
        return None 

    if 'metrics-aggregator.apawel.me/job-name' not in metadata.labels.keys():
        return None 

    for k, v in metadata.labels.items():
        if not k.startswith( 'metrics-aggregator.apawel.me' ):
            continue 

        _, label_name = k.split('/', 1)

        parsed_labels[ label_name ] = v 

    return parsed_labels

def update_cache():
    v1 = client.CoreV1Api()

    new_cache = {}

    log('debug', 'start cache update')

    ret = v1.list_pod_for_all_namespaces(watch=False)
    for i in ret.items:
        labels = parse_labels(i.metadata)

        if labels is None:
            continue 

        pod_blob = {
            'name': i.metadata.name,
            'ip': i.status.pod_ip,
            'namespace': i.metadata.namespace,
            'labels': labels 
        }

        log('debug', f'adding pod blob: {pod_blob}')

        try:
            new_cache[ pod_blob['labels']['job-name'] ].append( pod_blob )
        except KeyError:
            new_cache[ pod_blob['labels']['job-name'] ] = []
            new_cache[ pod_blob['labels']['job-name'] ].append( pod_blob )

    new_cache['_cache-last-update'] = int(time.time())

    log('debug', 'cache updated')

    return new_cache

class RequestHandler(BaseHTTPRequestHandler):   
    def __init__(self, *args, **kwargs):
        # we steal these values from the server
        self.pod_job_cache = args[2].pod_job_cache
        self.default_pod_labels = args[2].default_pod_labels
        self.settings = args[2].settings
        self.error_message_format = """%(code)d %(message)s: %(explain)s"""

        super(RequestHandler, self).__init__(*args, **kwargs)

    def respond(self, response_code, response_message, response_body):
        self.send_response(response_code, response_message)
        self.end_headers()
        self.wfile.write(response_body.encode('utf-8'))

    def do_GET(self):
        response_code = 200
        response_message = 'OK'
        response_body = ''

        try:
            location, params = self.path.split('?', 1)
            param_name, param_value = params.split('=', 1)
        except:
            self.respond(400, 'Bad Request', 'Target job name not specified')
            return 

        if param_name != 'job':
            self.respond(400, 'Bad Request', f"Unknown parameter '{param_value}'")
            return

        job_name = param_value

        if job_name not in self.pod_job_cache['cache'].keys():
            self.respond(400, 'Bad Request', 'Target job name not found in cache')
            return 

        # dont bother spawning a pool if num client workers is 1
        if self.settings['client-workers'] < 2:
            results = []
            for pod in self.pod_job_cache['cache'][job_name]:
                results.extend( request_metrics(pod) )
        else:
            process_pool = multiprocessing.Pool(processes=self.settings['client-workers'])
            results = process_pool.map(request_metrics, self.pod_job_cache['cache'][job_name])
            results = [ item for sublist in results for item in sublist ]
            process_pool.close()

        aggregated = "\n".join(aggregate_metrics(results) + ["\n"])

        self.respond(200, 'OK', aggregated)


def aggregate_metrics(raw_metrics):
    aggregated_metrics = {}

    for metric in raw_metrics:
        if metric[0:1] == '#':
            _, comment_type, metric_name, text = metric.split(' ', 3)

            if metric_name not in aggregated_metrics.keys():
                aggregated_metrics[metric_name] = { 'data': [] }

            aggregated_metrics[metric_name][comment_type] = text
            continue 
        
        metric_name, _, metric_value = metric.rpartition(' ')
        metric_name, _ = metric_name.split('{', 1)

        if metric_name not in aggregated_metrics.keys():
            aggregated_metrics[metric_name] = { 'data': [] }

        aggregated_metrics[metric_name]['data'].append(metric)

    output = []

    for metric_name in aggregated_metrics.keys():
        try:
            output.append( f"# HELP {metric_name} {aggregated_metrics[ metric_name ][ 'HELP' ]}" )
            output.append( f"# TYPE {metric_name} {aggregated_metrics[ metric_name ][ 'TYPE' ]}" )
        except:
            pass 

        try:
            prev = None 
            aggregated_metrics[ metric_name ]['data'].sort()
            for line in aggregated_metrics[ metric_name ]['data']:
                if line == prev:
                    log("warning", f"ignoring duplicate metric: {metric}")
                    continue 

                prev = line 
                output.append(line)
        except:
            pass 

    return output 

def request_metrics(pod):
    metrics_output = []
    log('debug', f"checking metrics for namespace {pod['namespace']} pod {pod['name']} job-name {pod['labels']['job-name']}")
    uplabels = f"job='{pod['labels']['job-name']}',instance='{pod['name']}',pod_namespace='{pod['namespace']}',pod_ip='{pod['ip']}'"

    try:
        data = requests.get( f"http://{pod['ip']}:{pod['labels']['port']}/{pod['labels']['endpoint']}", timeout=int(pod['labels']['scrape-timeout-seconds']))
    except requests.exceptions.Timeout:
        log("warning", f"namespace {pod['namespace']} pod {pod['name']}: timed out getting metrics")
        metrics_output.append( f"up{{{uplabels}}} 0" )
        return metrics_output
    except requests.exceptions.RequestException as e:
        log("warning", f"namespace {pod['namespace']} pod {pod['name']}: request failed with exception: {e}")
        metrics_output.append( f"up{{{uplabels}}} 0" )
        return metrics_output

    metrics_input = data.text.splitlines()

    for metric in metrics_input:
        if metric[0:1] == '#':
            metrics_output.append(metric)
            continue 

        try:
            metric_name, _, metric_value = metric.rpartition(' ')
        except Exception as e:
            log("error", f"Failed parsing metric '{metric}': {e}")
            raise SystemExit 
        
        temp = {}

        try:
            metric_name, labels = metric_name.split('{', 1)

            labels = labels[:-1].split(',')
            quote_char = labels[0][-1]

            for label in labels:
                key, value = label.split('=')
                temp[key] = value
        except ValueError:
            # no labels
            quote_char = '"'

        temp[ "instance" ] = f"{quote_char}{pod['name']}{quote_char}"
        temp[ "job" ] = f"{quote_char}{pod['labels']['job-name']}{quote_char}"
        temp[ "pod-namespace" ] = f"{quote_char}{pod['namespace']}{quote_char}"
        temp[ "pod-ip" ] = f"{quote_char}{pod['ip']}{quote_char}"

        labels = []

        for k,v in temp.items():
            labels.append( f"{k}={v}" )
            
        metrics_output.append(f"{metric_name}{{{','.join(labels)}}} {metric_value}")

    uplabels = f"job={quote_char}{pod['labels']['job-name']}{quote_char},instance={quote_char}{pod['name']}{quote_char},pod_namespace={quote_char}{pod['namespace']}{quote_char},pod_ip={quote_char}{pod['ip']}{quote_char}"
    metrics_output.append( f"up{{{uplabels}}} 1" )

    return metrics_output

class ExporterServer(HTTPServer):
    pass 
 
def serve_forever(server):
    log('debug', 'starting worker')

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass 

def runpool(address, pod_job_cache, default_pod_labels, settings):
    # create a single server object -- children will each inherit a copy
    server = ExporterServer(address, RequestHandler)
    server.pod_job_cache = pod_job_cache
    server.default_pod_labels = default_pod_labels
    server.settings = settings

    # create child processes to act as workers
    for i in range(settings['server-workers']):
        multiprocessing.Process(target=serve_forever, args=(server,)).start()

    # cache updates
    log('debug', 'starting cache update worker')

    while True:
        pod_job_cache['cache'] = update_cache()
        time.sleep(int(settings['cache-update-interval']))

if __name__ == '__main__':
    DIR = os.path.join(os.path.dirname(__file__), '..')
    os.chdir(DIR)

    pod_job_cache['cache'] = update_cache()
    
    runpool(
        address = ( '0.0.0.0', 80 ), 
        pod_job_cache = pod_job_cache,
        default_pod_labels = default_pod_labels,
        settings = settings
    )
