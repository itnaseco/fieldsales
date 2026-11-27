import frappe

from fieldsales.field_sales.access import OFFICER, REVIEWER, _pilot_scope, get_assignment


REVIEW_TYPES = {
	REVIEWER: {"Event Participation", "Demo Farm", "Demo Observation"},
	"Accounts Manager": {"Bank Payment Evidence", "Collection"},
	"Stock Manager": {"Stock Handover", "Stock Count", "Delivery Proof", "Return or Discrepancy"},
	"Delivery Manager": {"Delivery Proof", "Return or Discrepancy"},
}


def report_permission(doc, user=None, ptype=None):
	user = user or frappe.session.user
	roles = set(frappe.get_roles(user))
	if "System Manager" in roles:
		return True
	if ptype in (None, "read", "select", "create") and doc.owner == user:
		scope = _officer_scope(user, roles)
		if scope and doc.company == scope.company and doc.territory == scope.territory:
			return True
	if ptype not in (None, "read", "select", "write"):
		return False
	types = _review_types(roles)
	scope = get_assignment(user) if types else None
	return bool(scope and doc.company == scope.company and doc.territory == scope.territory
		and doc.report_type in types)


def report_query(user=None):
	user = user or frappe.session.user
	roles = set(frappe.get_roles(user))
	if "System Manager" in roles:
		return ""
	table = "`tabField Sales Report`"
	escape = frappe.db.escape
	clauses = []
	scope = _officer_scope(user, roles)
	if scope:
		clauses.append(f"({_scope_filter(scope)} AND {table}.owner = {escape(user)})")
	types = _review_types(roles)
	review_scope = get_assignment(user) if types else None
	if review_scope:
		values = ", ".join(escape(value) for value in sorted(types))
		clauses.append(f"({_scope_filter(review_scope)} AND {table}.report_type IN ({values}))")
	return f"({' OR '.join(clauses)})" if clauses else "1 = 0"


def _officer_scope(user, roles):
	if OFFICER not in roles or not frappe.db.get_value("User", user, "enabled"):
		return None
	if frappe.conf.get("fieldsales_pilot_scope") is not None:
		return _pilot_scope()
	return get_assignment(user)


def _review_types(roles):
	return {report for role in roles for report in REVIEW_TYPES.get(role, ())}


def _scope_filter(scope):
	table = "`tabField Sales Report`"
	escape = frappe.db.escape
	return f"{table}.company = {escape(scope.company)} AND {table}.territory = {escape(scope.territory)}"
