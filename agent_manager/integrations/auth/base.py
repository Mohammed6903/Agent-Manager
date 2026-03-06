from abc import ABC, abstractmethod


class BaseAuthHandler(ABC):
    """Abstract base class for all integration authentication handlers."""

    def __init__(self, scheme: dict):
        self.scheme = scheme

    @abstractmethod
    def inject(self, creds: dict, headers: dict, params: dict, method: str, url: str) -> tuple[dict, dict]:
        """
        Inject credentials into the headers or params dictionaries.
        Returns the modified (headers, params).
        """
        pass

    def requires_refresh(self, creds: dict) -> bool:
        """
        Check if the current credentials need to be refreshed before use.
        Defaults to False.
        """
        return False

    async def refresh(self, creds: dict, db) -> dict:
        """
        Perform the required refresh operation.
        Must return the updated credentials dictionary.
        Raises NotImplementedError if not overridden but requires_refresh is True.
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not implement refresh().")

    def _inject_extra_headers(self, creds: dict, headers: dict) -> None:
        """Helper to inject any `{field}` mapped extra headers."""
        for header_name, template in self.scheme.get("extra_headers", {}).items():
            value = template
            for key, val in creds.items():
                if isinstance(val, str):
                    value = value.replace(f"{{{key}}}", val)
            if "{" not in value:
                headers[header_name] = value
