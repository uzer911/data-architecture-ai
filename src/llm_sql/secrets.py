"""Helpers to retrieve secrets from AWS Secrets Manager."""
from __future__ import annotations

import json
import base64
from typing import Dict, Any, Optional

import boto3
from botocore.exceptions import ClientError


def get_secret_dict(secret_name: str, region: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve and parse a secret from AWS Secrets Manager.

    The secret is expected to be a JSON string. Returns an empty dict
    if the secret cannot be retrieved.
    """
    client = boto3.client('secretsmanager', region_name=region)
    try:
        resp = client.get_secret_value(SecretId=secret_name)
    except ClientError:
        raise

    if 'SecretString' in resp and resp['SecretString']:
        try:
            return json.loads(resp['SecretString'])
        except json.JSONDecodeError:
            return {'value': resp['SecretString']}
    if 'SecretBinary' in resp and resp['SecretBinary']:
        decoded = base64.b64decode(resp['SecretBinary'])
        try:
            return json.loads(decoded)
        except json.JSONDecodeError:
            return {'value': decoded}
    return {}
