import frappe
from frappe import _

from fieldsales.field_sales.access import PILOT
from fieldsales.field_sales.customers import check_customer, outlets
from fieldsales.field_sales.mobile_schema import RECORDS, REPORT


CAPTURES = {"Field Sales Customer Intake", "Field Sales Visit", "Field Sales Complaint"}
CUSTOMERS = {"Customer", "Address", "Contact"}


def record_type(kind):
	if kind not in RECORDS:
		frappe.throw(_("Unknown Field Sales record type."))
	return RECORDS[kind]


def own_employee(scope):
	employees = frappe.get_all(
		"Employee", filters={"user_id": frappe.session.user, "company": scope.company, "status": "Active"},
		fields=["name", "leave_approver", "expense_approver", "department"], limit=2,
	)
	return employees[0] if len(employees) == 1 else None


def permitted_warehouses(scope):
	rows = frappe.get_all(
		"User Permission", filters={"user": frappe.session.user, "allow": "Warehouse"},
		fields=["for_value", "apply_to_all_doctypes", "applicable_for"],
	)
	names = [
		row.for_value for row in rows
		if row.apply_to_all_doctypes or row.applicable_for in ("Warehouse", "Bin")
	]
	return frappe.get_list(
		"Warehouse", filters={"name": ["in", names], "company": scope.company, "is_group": 0},
		pluck="name",
	) if names and frappe.has_permission("Warehouse", "read") else []


def read_scope(record, scope, policy):
	doctype = record.doctype
	if not frappe.has_permission(doctype, "read"):
		return None, _("Your account does not have permission to view these records.")
	if record.employee:
		employee = own_employee(scope)
		if not employee:
			return None, _("Link your account to one active Employee in this company to use this section.")
		filters = {"employee": employee.name, "company": scope.company, "docstatus": ["!=", 2]}
		if doctype == "Employee Incentive":
			component = frappe.conf.get("fieldsales_commission_salary_component")
			if not component:
				return None, _("No Field Sales commission component has been configured.")
			filters["salary_component"] = component
		return filters, None
	if doctype == "Customer":
		return customer_filters(scope, policy), None
	if doctype in ("Contact", "Address"):
		return None, None
	if doctype == "Bin":
		names = permitted_warehouses(scope)
		if not names:
			return None, _("No stock warehouse has been granted to your account.")
		return {"warehouse": ["in", names]}, None
	if doctype in CAPTURES or doctype == REPORT:
		filters = dict(scope, owner=frappe.session.user)
		if record.report_type:
			filters["report_type"] = record.report_type
		return filters, None
	filters = {"company": scope.company, "owner": frappe.session.user, "docstatus": ["!=", 2]}
	if policy != PILOT:
		filters["territory"] = scope.territory
	return filters, None


def customer_filters(scope, policy):
	filters = {"disabled": 0}
	if policy != PILOT:
		filters["territory"] = scope.territory
	return filters


def can_create(record, scope):
	return (bool(record.fields or record.lines)
		and frappe.has_permission(record.doctype, "create")
		and (not record.employee or bool(own_employee(scope))))


def link_filters(target, key, scope, policy, context):
	if target == "Customer":
		return customer_filters(scope, policy)
	if target == "Address":
		if not context.get("customer"):
			return {"name": ["in", []]}
		territory = None if policy == PILOT else scope.territory
		addresses = [row.name for row in outlets(territory, context["customer"])]
		return {"name": ["in", addresses]}
	if target == "Territory":
		return {"name": scope.territory} if policy != PILOT else {"is_group": 0}
	if target in ("Sales Order", "Delivery Note"):
		if not context.get("customer"):
			return {"name": ["in", []]}
		check_customer(None if policy == PILOT else scope.territory, context["customer"])
		filters = {"company": scope.company, "customer": context["customer"]}
		filters["docstatus"] = ["!=", 2] if target == "Sales Order" else 1
		if policy != PILOT:
			filters["territory"] = scope.territory
		return filters
	if target == "Warehouse":
		return {"company": scope.company, "is_group": 0, "disabled": 0}
	if target == "Item":
		return {"disabled": 0, **({"is_sales_item": 1} if key == "item_code" else {})}
	if target == "Batch":
		return {"disabled": 0, "item": context.get("item") or ""}
	if target == REPORT:
		return dict(scope, owner=frappe.session.user, report_type="Demo Farm",
			review_status=["!=", "Rejected"])
	if target in ("Leave Type", "Expense Claim Type", "Country", "UOM", "Currency", "Customer Group"):
		return {}
	frappe.throw(_("This field is not available in Field Sales."), frappe.PermissionError)
