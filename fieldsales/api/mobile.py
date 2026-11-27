import frappe
from frappe import _

from fieldsales.field_sales.access import require_officer
from fieldsales.field_sales.mobile_fields import describe_form, lookup
from fieldsales.field_sales.mobile_records import create_record as save_record
from fieldsales.field_sales.mobile_records import list_records as get_records
from fieldsales.field_sales.mobile_scope import can_create, record_type


@frappe.whitelist(methods=["GET"])
def list_records(kind: str, start: int = 0):
	scope, policy = require_officer()
	return get_records(kind, record_type(kind), scope, policy, start)


@frappe.whitelist(methods=["GET"])
def form(kind: str):
	scope, policy = require_officer()
	record = record_type(kind)
	_require_create(record, scope)
	return describe_form(record, scope, policy)


@frappe.whitelist(methods=["POST"])
def link_options(kind: str, field: str, term: str = "", context: dict | None = None, line: bool = False):
	scope, policy = require_officer()
	record = record_type(kind)
	_require_create(record, scope)
	return lookup(record, field, line, scope, policy, context or {}, term)


@frappe.whitelist(methods=["POST"])
def create_record(
	kind: str, company: str, territory: str, access_policy: str, mutation_id: str, payload: dict,
):
	scope, policy = require_officer()
	if (company, territory, access_policy) != (scope.company, scope.territory, policy):
		frappe.throw(_("Your Field Sales access changed. Reopen this form and try again."), frappe.PermissionError)
	return save_record(kind, record_type(kind), scope, policy, mutation_id, payload)


def _require_create(record, scope):
	if not can_create(record, scope):
		frappe.throw(_("Your account does not have permission to create this record."), frappe.PermissionError)
