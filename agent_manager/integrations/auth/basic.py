import base64
from .base import BaseAuthHandler


class BasicAuthHandler(BaseAuthHandler):
    def inject(self, creds: dict, headers: dict, params: dict, method: str, url: str) -> tuple[dict, dict]:
        username = creds.get(self.scheme.get("username_field", "username"))
        password = creds.get(self.scheme.get("password_field", "password"))
        
        if username and password:
            encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {encoded}"
            
        self._inject_extra_headers(creds, headers)
        return headers, params
