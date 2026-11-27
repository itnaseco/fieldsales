import frappe
from frappe.sessions import get_csrf_token

from fieldsales import __version__
from fieldsales.field_sales import capture, customers
from fieldsales.field_sales.access import require_officer


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
	assignment = require_officer()
	return {
		"api_version": "v1",
		"user": frappe.session.user,
		"company": assignment.company,
		"territory": assignment.territory,
		"capture_types": list(capture.KINDS),
		"csrf_token": get_csrf_token(),
	}


@frappe.whitelist(methods=["GET"])
def search_customers(term: str):
	return customers.search(require_officer().territory, term)


@frappe.whitelist(methods=["GET"])
def list_outlets(customer: str):
	return customers.outlets(require_officer().territory, customer)


@frappe.whitelist(methods=["POST"])
def submit_capture(kind: str, external_id: str, mutation_id: str, company: str, territory: str, payload: dict):
	assignment = require_officer()
	if assignment.company != company or assignment.territory != territory:
		frappe.throw(frappe._("Your assignment changed. Contact your Field Sales administrator."), frappe.PermissionError)
	return capture.save(assignment, kind, external_id, mutation_id, payload)


@frappe.whitelist(methods=["POST"])
def capture_statuses(references: list):
	return capture.statuses(require_officer(), references)
