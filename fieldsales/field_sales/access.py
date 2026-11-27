import frappe
from frappe import _


OFFICER = "Field Sales Officer"
REVIEWER = "Field Sales Reviewer"
QUALITY_REVIEWER = "Field Sales Quality Reviewer"
ASSIGNED = "assigned"
PILOT = "pilot"
REVIEW_ROLES = {
	"Field Sales Customer Intake": REVIEWER,
	"Field Sales Visit": REVIEWER,
	"Field Sales Complaint": QUALITY_REVIEWER,
}


def get_assignment(user):
	if not frappe.db.get_value("User", user, "enabled"):
		return None
	global_scope = {"Company": set(), "Territory": set()}
	field_scope = {"Company": set(), "Territory": set()}
	rows = frappe.get_all(
		"User Permission", filters={"user": user, "allow": ["in", list(global_scope)]},
		fields=["allow", "for_value", "applicable_for", "apply_to_all_doctypes"],
	)
	for row in rows:
		if row.apply_to_all_doctypes or not row.applicable_for:
			global_scope[row.allow].add(row.for_value)
		elif row.applicable_for == "Field Sales Customer Intake":
			field_scope[row.allow].add(row.for_value)

	if any(field_scope.values()):
		scope = field_scope
		if any(global_scope[key] and not values <= global_scope[key] for key, values in scope.items()):
			return None
	else:
		scope = global_scope

	if any(scope.values()):
		if any(len(values) != 1 for values in scope.values()):
			return None
		return frappe._dict(company=next(iter(scope["Company"])), territory=next(iter(scope["Territory"])))

	if frappe.conf.get("fieldsales_allow_legacy_assignment"):
		return frappe.db.get_value(
			"Field Sales Assignment", {"user": user, "enabled": 1},
			["company", "territory"], as_dict=True,
		)
	return None


def has_app_access():
	user = frappe.session.user
	roles = set(frappe.get_roles(user))
	return "System Manager" in roles or (
		bool(roles & {OFFICER, REVIEWER, QUALITY_REVIEWER}) and bool(get_assignment(user))
	)


def require_officer():
	user = frappe.session.user
	if OFFICER not in frappe.get_roles(user):
		frappe.throw(_("Field Sales Officer access is required."), frappe.PermissionError)
	config = frappe.conf.get("fieldsales_pilot_scope")
	if config is not None:
		scope = _pilot_scope()
		if not scope:
			frappe.throw(_("Field Sales pilot scope is invalid."), frappe.PermissionError)
		if not frappe.db.get_value("User", user, "enabled"):
			frappe.throw(_("Field Sales Officer access is required."), frappe.PermissionError)
		return scope, PILOT
	assignment = get_assignment(user)
	if not assignment:
		frappe.throw(_("Ask your administrator for one Field Sales Company and Territory User Permission."), frappe.PermissionError)
	return assignment, ASSIGNED


def review_customer_territory(doc):
	pilot_scope = _pilot_scope()
	return None if pilot_scope and _in_scope(doc, pilot_scope) else doc.territory


def _pilot_scope():
	config = frappe.conf.get("fieldsales_pilot_scope")
	if not isinstance(config, dict):
		return None
	company, territory = config.get("company"), config.get("territory")
	if not all(isinstance(value, str) and value.strip() for value in (company, territory)):
		return None
	if frappe.db.exists("Company", company) and frappe.db.exists("Territory", territory):
		return frappe._dict(company=company, territory=territory)
	return None


def record_permission(doc, user=None, ptype=None):
	user = user or frappe.session.user
	roles = frappe.get_roles(user)
	if "System Manager" in roles:
		return True
	assignment = get_assignment(user)
	if not assignment or not _in_scope(doc, assignment):
		return False
	if REVIEW_ROLES[doc.doctype] in roles:
		return True
	return ptype in (None, "read", "select") and doc.owner == user and OFFICER in roles


def intake_query(user=None):
	return _query("Field Sales Customer Intake", user)


def visit_query(user=None):
	return _query("Field Sales Visit", user)


def complaint_query(user=None):
	return _query("Field Sales Complaint", user)


def _query(doctype, user):
	user = user or frappe.session.user
	roles = frappe.get_roles(user)
	if "System Manager" in roles:
		return ""
	assignment = get_assignment(user)
	if not assignment:
		return "1 = 0"
	table = f"`tab{doctype}`"
	escape = frappe.db.escape
	scope = f"{table}.company = {escape(assignment.company)} and {table}.territory = {escape(assignment.territory)}"
	if REVIEW_ROLES[doctype] in roles:
		return scope
	return f"{scope} and {table}.owner = {escape(user)}" if OFFICER in roles else "1 = 0"


def _in_scope(doc, assignment):
	return doc.company == assignment.company and doc.territory == assignment.territory
