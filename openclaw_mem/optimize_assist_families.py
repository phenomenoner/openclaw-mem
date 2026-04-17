from __future__ import annotations

from typing import Any, Mapping

FAMILY_NAMES = (
    "stale_candidate",
    "importance_downshift",
    "score_label_alignment",
)


def action_family_from_action_patch(action: Any, patch: Any) -> str:
    action_name = str(action or "").strip()
    patch_obj = patch if isinstance(patch, Mapping) else {}
    if action_name == "set_stale_candidate":
        return "stale_candidate"
    if action_name == "adjust_importance_score":
        importance_patch = patch_obj.get("importance") if isinstance(patch_obj.get("importance"), Mapping) else {}
        reason_code = str(importance_patch.get("reason_code") or "").strip()
        if reason_code == "label_alignment":
            return "score_label_alignment"
        return "importance_downshift"
    return "unknown"


def candidate_family_from_item(item: Any) -> str:
    item_obj = item if isinstance(item, Mapping) else {}
    action = item_obj.get("recommended_action") or item_obj.get("action")
    patch = item_obj.get("patch") if isinstance(item_obj.get("patch"), Mapping) else {}
    return action_family_from_action_patch(action, patch)
