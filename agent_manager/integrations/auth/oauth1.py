import base64
import hashlib
import hmac
import time
import urllib.parse
import uuid

from .base import BaseAuthHandler


class OAuth1Handler(BaseAuthHandler):
    def inject(self, creds: dict, headers: dict, params: dict, method: str, url: str) -> tuple[dict, dict]:
        headers["Authorization"] = self._build_oauth1_header(creds, method, url, params)
        self._inject_extra_headers(creds, headers)
        return headers, params
        
    def _build_oauth1_header(self, creds: dict, method: str, url: str, params: dict) -> str:
        """Build an OAuth 1.0a Authorization header (HMAC-SHA1)."""
        consumer_key = creds.get(self.scheme.get("consumer_key_field", "api_key"), "")
        consumer_secret = creds.get(self.scheme.get("consumer_secret_field", "api_secret"), "")
        token = creds.get(self.scheme.get("token_field", "access_token"), "")
        token_secret = creds.get(self.scheme.get("token_secret_field", "access_secret"), "")

        # Generate nonce and timestamp
        nonce = uuid.uuid4().hex
        timestamp = str(int(time.time()))

        oauth_params = {
            "oauth_consumer_key": consumer_key,
            "oauth_nonce": nonce,
            "oauth_signature_method": "HMAC-SHA1",
            "oauth_timestamp": timestamp,
            "oauth_token": token,
            "oauth_version": "1.0",
        }

        # Combine oauth params + query params for the signature base
        all_params = {**oauth_params, **(params or {})}
        sorted_params = "&".join(
            f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}"
            for k, v in sorted(all_params.items())
        )

        # Strip query string from URL for the base string
        base_url = url.split("?")[0]
        signature_base = (
            f"{method.upper()}"
            f"&{urllib.parse.quote(base_url, safe='')}"
            f"&{urllib.parse.quote(sorted_params, safe='')}"
        )

        signing_key = (
            f"{urllib.parse.quote(consumer_secret, safe='')}"
            f"&{urllib.parse.quote(token_secret, safe='')}"
        )

        signature = base64.b64encode(
            hmac.new(signing_key.encode(), signature_base.encode(), hashlib.sha1).digest()
        ).decode()

        oauth_params["oauth_signature"] = signature

        # Build header value
        header_parts = ", ".join(
            f'{k}="{urllib.parse.quote(str(v), safe="")}"'
            for k, v in sorted(oauth_params.items())
        )
        return f"OAuth {header_parts}"
