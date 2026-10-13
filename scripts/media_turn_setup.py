#!/usr/bin/env python3
"""Prepare a private coturn deployment and optional hub configuration; never print secrets.

Run with the repository venv. Deployment needs a Linux host, DNS, TLS certificate and Docker.
The selected container image must be pinned by digest. Generated files are excluded from Git.
"""
import argparse
import ipaddress
import os
from pathlib import Path
import re
import secrets

import yaml

ROOT = Path(__file__).resolve().parents[1]


def deployment(host, public_ip, image, secret):
    if not re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?', host):
        raise ValueError('host must be a DNS name')
    ipaddress.ip_address(public_ip)
    if not re.fullmatch(r'coturn/coturn@sha256:[a-f0-9]{64}', image):
        raise ValueError('use the verified coturn/coturn@sha256:<digest> image')
    config = '\n'.join([
        'listening-port=3478', 'tls-listening-port=5349', f'external-ip={public_ip}',
        f'realm={host}', f'server-name={host}', 'fingerprint', 'use-auth-secret',
        f'static-auth-secret={secret}', 'min-port=49160', 'max-port=49260',
        'cert=/certs/fullchain.pem', 'pkey=/certs/privkey.pem', 'no-tlsv1', 'no-tlsv1_1',
        'no-cli', 'no-multicast-peers', 'stale-nonce=600',
        'user-quota=12', 'total-quota=120', 'log-file=stdout', 'simple-log',
        'denied-peer-ip=10.0.0.0-10.255.255.255', 'denied-peer-ip=172.16.0.0-172.31.255.255',
        'denied-peer-ip=192.168.0.0-192.168.255.255', 'denied-peer-ip=169.254.0.0-169.254.255.255',
        'denied-peer-ip=::1', 'denied-peer-ip=fc00::-fdff:ffff:ffff:ffff:ffff:ffff:ffff:ffff', '',
    ])
    compose = {'services': {'turn': {'image': image, 'user': '0:0', 'network_mode': 'host', 'restart': 'unless-stopped',
        'command': ['-c', '/etc/coturn/turnserver.conf'],
        'volumes': ['./turnserver.conf:/etc/coturn/turnserver.conf:ro', './certs:/certs:ro']}}}
    ice = {'urls': [f'turn:{host}:3478?transport=udp', f'turn:{host}:3478?transport=tcp',
                    f'turns:{host}:5349?transport=tcp'],
           'credential_mode': 'ephemeral', 'secret_env': 'MEDIA_TURN_SECRET', 'ttl_s': 3600}
    return config, compose, ice


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--public-ip', required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--apply', action='store_true', help='configure this hub and .env')
    args = parser.parse_args()
    dest = ROOT / 'data/media_turn_private'
    secret_file = dest / 'secret'
    secret = secret_file.read_text().strip() if secret_file.exists() else secrets.token_hex(32)
    config, compose, ice = deployment(args.host, args.public_ip, args.image, secret)
    dest.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(dest, 0o700)
    for name, text in {'secret': secret, 'turnserver.conf': config,
                       'compose.yaml': yaml.safe_dump(compose, sort_keys=False),
                       'ice.yaml': yaml.safe_dump(ice, sort_keys=False)}.items():
        path = dest / name
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(text)
    if args.apply:
        from dotenv import set_key
        path = ROOT / 'data/media_policy.yaml'
        policy = yaml.safe_load(path.read_text())
        policy['ice_servers'] = [r for r in policy.get('ice_servers', [])
                                if all(str(u).startswith('stun:') for u in r.get('urls', [])) and r.get('urls')]
        policy['ice_servers'].append(ice)
        path.write_text(yaml.safe_dump(policy, allow_unicode=True, sort_keys=False))
        set_key(str(ROOT / '.env'), 'MEDIA_TURN_SECRET', secret)
    print(f'Prepared private deployment: {dest}')
    print('On the Linux TURN host: install certs/fullchain.pem and certs/privkey.pem, then docker compose up -d.')
    print('Allow 3478 UDP/TCP, 5349 TCP, 49160–49260 UDP; use a direct DNS record, not an HTTP tunnel.')
    print('After hub restart, verify /media/health and run relay-only browser/phone tests. Configuration is not connectivity proof.')


if __name__ == '__main__':
    main()
