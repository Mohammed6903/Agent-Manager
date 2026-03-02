"""Integration request/response field transformers for API normalization.

Allows integrations to define mapping rules that convert between the agent's
expected format and what the upstream API requires — handling format differences,
field renames, nested restructuring, etc.

Rule format:
    {
        "type": "map",  # or "add", "extract", "rename", "nest", "flatten"
        "source": "old_field_path",
        "target": "new_field_path",
        "transform": null or "string" function
    }

Example — flatten visibility:
    {
        "type": "map",
        "source": "visibility.com.linkedin.ugc.MemberNetworkVisibility",
        "target": "visibility",
        "transform": null
    }

Example — add missing field with default:
    {
        "type": "add",
        "target": "distribution",
        "value": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": []
        }
    }
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agent_manager.services.transformer")


def _get_nested(obj: Dict, path: str) -> Any:
    """Retrieve a nested value using dot notation: 'a.b.c' -> obj['a']['b']['c']."""
    keys = path.split(".")
    val = obj
    for key in keys:
        if isinstance(val, dict) and key in val:
            val = val[key]
        else:
            return None
    return val


def _set_nested(obj: Dict, path: str, value: Any) -> None:
    """Set a nested value using dot notation, creating intermediate dicts as needed."""
    keys = path.split(".")
    current = obj
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


def _delete_nested(obj: Dict, path: str) -> None:
    """Delete a nested value using dot notation."""
    keys = path.split(".")
    current = obj
    for key in keys[:-1]:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return
    if isinstance(current, dict) and keys[-1] in current:
        del current[keys[-1]]


class IntegrationTransformer:
    """Applies field mapping rules to normalize requests/responses."""

    @staticmethod
    def transform(
        body: Dict[str, Any],
        rules: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Apply transformation rules to a body dict.

        Returns a new dict with transformations applied.
        """
        if not rules:
            return body

        result = dict(body)  # shallow copy to avoid mutating original

        for rule in rules:
            rule_type = rule.get("type", "map")

            try:
                if rule_type == "map":
                    IntegrationTransformer._apply_map(result, rule)
                elif rule_type == "add":
                    IntegrationTransformer._apply_add(result, rule)
                elif rule_type == "extract":
                    IntegrationTransformer._apply_extract(result, rule)
                elif rule_type == "rename":
                    IntegrationTransformer._apply_rename(result, rule)
                elif rule_type == "delete":
                    IntegrationTransformer._apply_delete(result, rule)
                else:
                    logger.warning(f"Unknown transformer rule type: {rule_type}")
            except Exception as e:
                logger.error(f"Error applying transformer rule {rule}: {e}")

        return result

    @staticmethod
    def _apply_map(obj: Dict, rule: Dict) -> None:
        """Move a field from source to target (possibly extracting from nested structure)."""
        source = rule.get("source")
        target = rule.get("target")
        if not source or not target:
            return

        val = _get_nested(obj, source)
        if val is not None:
            # Apply optional transform function
            transform_fn = rule.get("transform")
            if transform_fn == "stringify":
                val = str(val)
            elif transform_fn == "parse_json":
                import json
                val = json.loads(val) if isinstance(val, str) else val

            _set_nested(obj, target, val)
            # Delete the source if it differs from target
            if source != target:
                _delete_nested(obj, source)

    @staticmethod
    def _apply_add(obj: Dict, rule: Dict) -> None:
        """Add a field with a default value if it doesn't exist."""
        target = rule.get("target")
        value = rule.get("value")
        if not target:
            return

        if _get_nested(obj, target) is None:
            _set_nested(obj, target, value)

    @staticmethod
    def _apply_extract(obj: Dict, rule: Dict) -> None:
        """Extract a nested value and move it to the top level (or specified target)."""
        source = rule.get("source")
        target = rule.get("target", source.split(".")[-1] if source else None)
        if not source or not target:
            return

        val = _get_nested(obj, source)
        if val is not None:
            _set_nested(obj, target, val)

    @staticmethod
    def _apply_rename(obj: Dict, rule: Dict) -> None:
        """Rename a field at the top level."""
        old_name = rule.get("old_name")
        new_name = rule.get("new_name")
        if not old_name or not new_name:
            return

        if old_name in obj:
            obj[new_name] = obj.pop(old_name)

    @staticmethod
    def _apply_delete(obj: Dict, rule: Dict) -> None:
        """Delete a field by path."""
        target = rule.get("target")
        if target:
            _delete_nested(obj, target)
