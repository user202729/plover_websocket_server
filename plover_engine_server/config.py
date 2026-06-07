"""Server configuration."""

import json


DEFAULT_HOST: str = 'localhost'
DEFAULT_PORT: int = 8086

DEFAULT_CONFIG = {
    "host": DEFAULT_HOST,
    "port": DEFAULT_PORT,
    "secretkey": "",
    "ssl": {
        "cert_path": "",
        "key_path": ""
    }
}


class ServerConfig():

    host: str
    port: int

    def __init__(self, file_path: str):
        try:
            with open(file_path, 'r', encoding='utf-8') as config_file:
                data: dict = json.load(config_file)
        except FileNotFoundError:
            data = dict(DEFAULT_CONFIG)
            with open(file_path, 'w', encoding='utf-8') as config_file:
                json.dump(data, config_file, indent=2)

        self.host = data.get('host', DEFAULT_HOST)
        self.port = data.get('port', DEFAULT_PORT)
        self.secretkey = data.get('secretkey', '') or ''
        ssl = data.get('ssl', {}) or {}
        if isinstance(ssl, dict) and ssl.get('cert_path') and ssl.get('key_path'):
            self.ssl = ssl
        else:
            self.ssl = None
