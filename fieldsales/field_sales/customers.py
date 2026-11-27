import frappe
from frappe import _


def search(territory, term):
	if not frappe.has_permission("Customer", "read"):
		return []
	term = term.strip()[:80]
	if len(term) < 2:
		return []
	return frappe.get_list(
		"Customer", filters={"territory": territory, "disabled": 0},
		or_filters={"name": ["like", f"%{term}%"], "customer_name": ["like", f"%{term}%"]},
		fields=["name", "customer_name"], order_by="customer_name asc, name asc", limit=25,
	)


def outlets(territory, customer):
	check_customer(territory, customer)
	if not frappe.has_permission("Address", "read"):
		return []
	return frappe.get_list(
		"Address", filters=[
			["Address", "disabled", "=", 0],
			["Dynamic Link", "parenttype", "=", "Address"],
			["Dynamic Link", "link_doctype", "=", "Customer"],
			["Dynamic Link", "link_name", "=", customer],
		],
		fields=["name", "address_title", "address_line1", "city"],
		order_by="address_title asc, name asc", limit=100,
	)


def check_customer(territory, customer):
	if not frappe.has_permission("Customer", "read") or not frappe.get_list(
		"Customer", filters={"name": customer, "territory": territory, "disabled": 0},
		pluck="name", limit=1,
	):
		frappe.throw(_("This customer is unavailable in your Field Sales scope."), frappe.PermissionError)


def check_outlet(customer, address):
	linked = frappe.db.exists("Dynamic Link", {
		"parent": address, "parenttype": "Address", "parentfield": "links",
		"link_doctype": "Customer", "link_name": customer,
	})
	if not linked or not frappe.has_permission("Address", "read") or not frappe.get_list(
		"Address", filters={"name": address, "disabled": 0}, pluck="name", limit=1,
	):
		frappe.throw(_("This outlet is unavailable for the selected customer."), frappe.PermissionError)
