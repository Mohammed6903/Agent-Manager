from .base import BaseAuthHandler


class ApiKeyHeaderHandler(BaseAuthHandler):
    def inject(self, creds: dict, headers: dict, params: dict, method: str, url: str) -> tuple[dict, dict]:
        token = creds.get(self.scheme.get("token_field"))
        header_name = self.scheme.get("header_name", "X-Api-Key")
        if token:
            headers[header_name] = token
            
        self._inject_extra_headers(creds, headers)
        return headers, params


class ApiKeyQueryHandler(BaseAuthHandler):
    def inject(self, creds: dict, headers: dict, params: dict, method: str, url: str) -> tuple[dict, dict]:
        token = creds.get(self.scheme.get("token_field"))
        param_name = self.scheme.get("param_name", "api_key")
        if token:
            params = dict(params or {})
            params[param_name] = token
            
        self._inject_extra_headers(creds, headers)
        return headers, params
