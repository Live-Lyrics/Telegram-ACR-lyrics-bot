import os
import base64
import hmac
import hashlib
import time

import requests

access_key = os.environ.get('ACCESS_KEY')
access_secret = bytes(os.environ.get('ACCESS_SECRET'), 'utf-8')
requrl = "http://{}/v1/identify".format(os.environ.get('HOST'))

http_method = "POST"
http_uri = "/v1/identify"
data_type = "audio"
signature_version = "1"


def fetch_metadata(file_path):
    timestamp = time.time()
    string_to_sign = '\n'.join([http_method, http_uri, access_key, data_type, signature_version, str(timestamp)])

    sign = base64.b64encode(hmac.new(access_secret, string_to_sign.encode('utf-8'), digestmod=hashlib.sha1).digest())

    f = open(file_path, "rb")
    sample_bytes = os.path.getsize(file_path)

    files = {'sample': f}
    data = {'access_key': access_key,
            'sample_bytes': sample_bytes,
            'timestamp': str(timestamp),
            'signature': sign,
            'data_type': data_type,
            "signature_version": signature_version}

    r = requests.post(requrl, files=files, data=data)
    return r.json()
