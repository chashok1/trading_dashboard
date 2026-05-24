"""Rule group evaluation — recursive composition of composite rules and groups."""

from sqlalchemy import text
from typing import Dict, List, Tuple, Optional
import logging

log = logging.getLogger(__name__)


def eval_rule_group(
    session,
    group_code: str,
    composite_results: Dict[str, bool],
    all_group_results: Dict[str, Tuple[bool, str, int]] = None
) -> Tuple[bool, Optional[str], Optional[int]]:
    """
    Recursively evaluate a rule group.

    Args:
        session: DB session
        group_code: code of the group to evaluate
        composite_results: dict of {composite_rule_code: bool (triggered)}
        all_group_results: cache of already-evaluated groups

    Returns:
        (triggered: bool, action_label: str or None, priority: int or None)
    """
    if all_group_results is None:
        all_group_results = {}

    # Return cached result if already evaluated
    if group_code in all_group_results:
        return all_group_results[group_code]

    # Fetch group definition
    group_row = session.execute(text("""
        SELECT rule_group_code, group_type, action_label, priority
        FROM ref_trig_rule_group
        WHERE rule_group_code = :code AND deprecated_at IS NULL
    """), {"code": group_code}).mappings().first()

    if not group_row:
        log.warning(f"Rule group {group_code} not found or deprecated")
        result = (False, None, None)
        all_group_results[group_code] = result
        return result

    # Fetch members in order
    members = session.execute(text("""
        SELECT member_code, member_type, logic_operator
        FROM ref_trig_group_member
        WHERE rule_group_code = :code
        ORDER BY sequence
    """), {"code": group_code}).mappings().all()

    if not members:
        log.warning(f"Rule group {group_code} has no members")
        result = (False, None, None)
        all_group_results[group_code] = result
        return result

    # Evaluate each member
    member_results = []
    for member in members:
        if member["member_type"] == "composite":
            # Get composite result from pre-computed dict
            member_triggered = composite_results.get(member["member_code"], False)
        else:  # group
            # Recursively evaluate nested group
            member_triggered, _, _ = eval_rule_group(
                session, member["member_code"], composite_results, all_group_results
            )

        member_results.append(member_triggered)

        # Short-circuit AND: if any AND member fails, group fails
        if member["logic_operator"] == "AND" and not member_triggered:
            result = (False, None, None)
            all_group_results[group_code] = result
            return result

    # Evaluate final logic (handle mixed AND/OR by checking operators)
    # If all operators are AND, we already short-circuited above, so all are True
    # If there are OR operators, any True is enough
    operators = [m["logic_operator"] for m in members]

    if "OR" in operators:
        triggered = any(member_results)
    else:  # all AND
        triggered = all(member_results)

    if triggered:
        priority = group_row["priority"]
        action = group_row["action_label"]
        result = (True, action, priority)
    else:
        result = (False, None, None)

    all_group_results[group_code] = result
    return result


def resolve_final_action(triggered_groups: List[Dict]) -> Optional[Dict]:
    """
    When multiple groups trigger with different actions, pick the highest-priority one.
    Lower priority number = higher priority (Sell All = 1, Hold = 5).

    Args:
        triggered_groups: List of {"rule_group_code": str, "action": str, "priority": int}

    Returns:
        The highest-priority triggered group, or None if none triggered
    """
    if not triggered_groups:
        return None

    return min(triggered_groups, key=lambda g: g["priority"])


def get_all_rule_groups(session) -> List[Dict]:
    """Fetch all non-deprecated rule groups."""
    rows = session.execute(text("""
        SELECT rule_group_code, group_type, action_label, priority, category, intent_text
        FROM ref_trig_rule_group
        WHERE deprecated_at IS NULL
        ORDER BY priority, rule_group_code
    """)).mappings().all()
    return [dict(r) for r in rows]


def get_rule_group_with_members(session, group_code: str) -> Dict:
    """Fetch a rule group with its members and recursively nested groups."""
    group = session.execute(text("""
        SELECT rule_group_code, group_type, action_label, priority, category, intent_text, deprecated_at
        FROM ref_trig_rule_group
        WHERE rule_group_code = :code
    """), {"code": group_code}).mappings().first()

    if not group:
        return None

    members = session.execute(text("""
        SELECT member_code, member_type, logic_operator, sequence
        FROM ref_trig_group_member
        WHERE rule_group_code = :code
        ORDER BY sequence
    """), {"code": group_code}).mappings().all()

    return {
        **dict(group),
        "members": [dict(m) for m in members]
    }


def create_rule_group(session, group_code: str, group_type: str, action_label: Optional[str],
                     priority: Optional[int], category: Optional[str], intent_text: Optional[str]) -> bool:
    """Create a new rule group. Returns True on success."""
    try:
        session.execute(text("""
            INSERT INTO ref_trig_rule_group (rule_group_code, group_type, action_label, priority, category, intent_text)
            VALUES (:code, :type, :action, :priority, :category, :intent)
        """), {
            "code": group_code,
            "type": group_type,
            "action": action_label,
            "priority": priority,
            "category": category,
            "intent": intent_text
        })
        return True
    except Exception as e:
        log.error(f"Error creating rule group {group_code}: {e}")
        return False


def add_group_member(session, group_code: str, member_code: str, member_type: str,
                    logic_operator: str, sequence: int) -> bool:
    """Add a member to a rule group."""
    try:
        session.execute(text("""
            INSERT INTO ref_trig_group_member (rule_group_code, member_code, member_type, logic_operator, sequence)
            VALUES (:group, :member, :type, :op, :seq)
        """), {
            "group": group_code,
            "member": member_code,
            "type": member_type,
            "op": logic_operator,
            "seq": sequence
        })
        return True
    except Exception as e:
        log.error(f"Error adding member {member_code} to group {group_code}: {e}")
        return False


def deprecate_rule_group(session, group_code: str) -> bool:
    """Soft-delete a rule group."""
    try:
        session.execute(text("""
            UPDATE ref_trig_rule_group
            SET deprecated_at = now()
            WHERE rule_group_code = :code AND deprecated_at IS NULL
        """), {"code": group_code})
        return True
    except Exception as e:
        log.error(f"Error deprecating rule group {group_code}: {e}")
        return False
