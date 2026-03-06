from .base import BaseAuthHandler


class BearerAuthHandler(BaseAuthHandler):
    def inject(self, creds: dict, headers: dict, params: dict, method: str, url: str) -> tuple[dict, dict]:
        token = creds.get(self.scheme.get("token_field", "access_token"))
        if token:
            headers["Authorization"] = f"Bearer {token}"
            
        self._inject_extra_headers(creds, headers)
        return headers, params
