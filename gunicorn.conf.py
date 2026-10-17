import os

bind = '0.0.0.0:' + os.environ.get('PORT', '10000')
workers = 1
threads = 2
timeout = 120
max_requests = 100
max_requests_jitter = 20
accesslog = None
errorlog = '-'
