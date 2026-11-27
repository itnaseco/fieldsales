import frappe
from frappe import _

from fieldsales.field_sales.mobile_scope import own_employee


def build_document(record, values, scope):
	doctype = record.doctype
	doc = frappe.new_doc(doctype)
	if doctype == "Customer":
		_check_duplicate_customer(values)
	elif doctype in ("Address", "Contact"):
		doc.append("links", {"link_doctype": "Customer", "link_name": values.pop("customer")})
		if doctype == "Contact":
			_set_contact_details(doc, values)
	elif doctype == "Sales Order":
		doc.company = scope.company
	elif record.employee:
		_set_employee_defaults(doc, scope)
	doc.update(values)
	if doctype == "Sales Order":
		doc.set_missing_values()
	return doc


def _check_duplicate_customer(values):
	if frappe.has_permission("Customer", "read") and frappe.get_list(
		"Customer", filters={
			"customer_name": values["customer_name"], "territory": values["territory"], "disabled": 0,
		}, pluck="name", limit=1,
	):
		frappe.throw(_("A customer with this name already exists in the selected territory. Search for it first."))


def _set_contact_details(doc, values):
	email = values.pop("email_id", None)
	mobile = values.pop("mobile_no", None)
	if email:
		doc.append("email_ids", {"email_id": email, "is_primary": 1})
	if mobile:
		doc.append("phone_nos", {"phone": mobile, "is_primary_mobile_no": 1})


def _set_employee_defaults(doc, scope):
	employee = own_employee(scope)
	if not employee:
		frappe.throw(_("Link your account to one active Employee in this company first."), frappe.PermissionError)
	doc.employee = employee.name
	doc.company = scope.company
	if doc.doctype == "Leave Application":
		from hrms.hr.doctype.leave_application.leave_application import get_employee_leave_approver

		doc.leave_approver = get_employee_leave_approver(employee.name)
	if doc.doctype in ("Employee Advance", "Expense Claim"):
		doc.currency = frappe.db.get_value("Company", scope.company, "default_currency")
	if doc.doctype == "Expense Claim":
		from hrms.hr.doctype.expense_claim.expense_claim import get_default_payable_account

		doc.expense_approver = employee.expense_approver or frappe.db.get_value(
			"Department Approver", {
				"parent": employee.department, "parentfield": "expense_approvers", "idx": 1,
			}, "approver",
		)
		doc.department = employee.department
		doc.payable_account = get_default_payable_account(scope.company)
		doc.exchange_rate = 1
		if not doc.expense_approver or not doc.payable_account:
			frappe.throw(_("Set the Employee expense approver and the company payable account before recording claims."))
