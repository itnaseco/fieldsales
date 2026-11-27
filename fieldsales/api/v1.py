import frappe
from frappe.sessions import get_csrf_token

from fieldsales import __version__
from fieldsales.field_sales import capture, customers
from fieldsales.field_sales.access import ASSIGNED, PILOT, require_officer


@frappe.whitelist(allow_guest=True, methods=["GET"])
def health() -> dict[str, str]:
	"""Return the minimal public contract needed for client connectivity checks."""
	return {
		"app": "fieldsales",
		"app_version": __version__,
		"api_version": "v1",
		"status": "ok",
	}


@frappe.whitelist(methods=["GET"])
def bootstrap():
	assignment, policy = require_officer()
	return {
		"api_version": "v1",
		"user": frappe.session.user,
		"company": assignment.company,
		"territory": assignment.territory,
		"access_policy": policy,
		"capture_types": list(capture.KINDS),
		"csrf_token": get_csrf_token(),
	}


@frappe.whitelist(methods=["GET"])
def search_customers(term: str):
	assignment, policy = require_officer()
	return customers.search(None if policy == PILOT else assignment.territory, term)


@frappe.whitelist(methods=["GET"])
def list_outlets(customer: str):
	assignment, policy = require_officer()
	return customers.outlets(None if policy == PILOT else assignment.territory, customer)


@frappe.whitelist(methods=["POST"])
def submit_capture(
	kind: str, external_id: str, mutation_id: str, company: str, territory: str, payload: dict,
	access_policy: str = ASSIGNED,
):
	assignment, policy = require_officer()
	if (company, territory, access_policy) != (assignment.company, assignment.territory, policy):
		frappe.throw(frappe._("Your Field Sales access changed. Refresh access to continue."), frappe.PermissionError)
	return capture.save(
		assignment, kind, external_id, mutation_id, payload,
		customer_territory=None if policy == PILOT else assignment.territory,
	)


@frappe.whitelist(methods=["POST"])
def capture_statuses(references: list):
	assignment, _policy = require_officer()
	return capture.statuses(assignment, references)
