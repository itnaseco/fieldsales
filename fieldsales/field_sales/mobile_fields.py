import math

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from fieldsales.field_sales.access import PILOT
from fieldsales.field_sales.mobile_schema import ATTACHMENT, REPORT
from fieldsales.field_sales.mobile_scope import link_filters


def describe_form(record, scope, policy):
	line_doctype = child_type(record)
	return {
		"fields": [describe_field(record.doctype, field, scope, policy) for field in record.fields
			if field.key != "territory" or policy == PILOT],
		"line_table": record.line_table,
		"lines": [describe_field(line_doctype, field, scope, policy) for field in record.lines],
	}


def describe_field(doctype, field, scope, policy):
	df = docfield(doctype, field)
	kind = input_kind(df, field)
	default = df.default if kind == "select" else None
	if field.key == "activity_date" or field.key == "posting_date":
		default = nowdate()
	elif field.key == "customer_type":
		default = "Company"
	elif field.key == "address_type":
		default = "Shop"
	elif field.key == "country":
		default = frappe.db.get_single_value("System Settings", "country")
	elif field.key == "currency":
		default = frappe.db.get_value("Company", scope.company, "default_currency")
	return {
		"key": field.key, "label": _(field.label or df.label), "kind": kind,
		"required": field.required, "options": choices(df) if kind == "select" else [],
		"default": default,
		"depends_on": {
			"outlet": "customer", "customer_address": "customer",
			"sales_order": "customer", "delivery_note": "customer", "batch": "item",
		}.get(field.key),
	}


def child_type(record):
	if record.line_table:
		return frappe.get_meta(record.doctype).get_field(record.line_table).options


def docfield(doctype, field):
	if field.key == "customer" and doctype in ("Address", "Contact"):
		return frappe._dict(label="Customer", fieldtype="Link", options="Customer")
	df = frappe.get_meta(doctype).get_field(field.key)
	if not df:
		frappe.throw(_("The site has no field configured for {0}.").format(field.label or field.key))
	return df


def input_kind(df, field):
	if field.kind:
		return field.kind
	return {
		"Link": "link", "Select": "select", "Date": "date", "Check": "check",
		"Float": "number", "Currency": "number", "Int": "number",
		"Small Text": "notes", "Text": "notes", "Text Editor": "notes",
	}.get(df.fieldtype, "text")


def choices(df):
	return [value for value in (df.options or "").splitlines() if value]


def lookup(record, field_key, is_line, scope, policy, context, term):
	definitions = record.lines if is_line else record.fields
	field = next((field for field in definitions if field.key == field_key), None)
	if not field:
		frappe.throw(_("This field is not available in Field Sales."), frappe.PermissionError)
	df = docfield(child_type(record) if is_line else record.doctype, field)
	if df.fieldtype != "Link":
		frappe.throw(_("This field does not use linked records."))
	target = df.options
	if not frappe.has_permission(target, "read") and not frappe.has_permission(target, "select"):
		return []
	filters = link_filters(target, field_key, scope, policy, context)
	title_field = frappe.get_meta(target).title_field or "name"
	values = ["name"] if title_field == "name" else ["name", title_field]
	term = term.strip()[:80]
	search = {key: ["like", f"%{term}%"] for key in values} if term else None
	rows = frappe.get_list(
		target, filters=filters, or_filters=search, fields=values,
		order_by="name asc", limit=30,
	)
	return [{"value": row.name, "label": row.get(title_field) or row.name} for row in rows]


def prepare_values(record, payload, scope, policy):
	fields = {field.key: field for field in record.fields}
	allowed = set(fields) | ({record.line_table} if record.line_table else set())
	if set(payload) - allowed:
		frappe.throw(_("The form contains an unsupported field."))
	values = _clean(record.doctype, fields, payload, scope, policy)
	if record.line_table:
		raw_lines = payload.get(record.line_table)
		if not isinstance(raw_lines, list) or not 1 <= len(raw_lines) <= 50:
			frappe.throw(_("Add between one and 50 lines."))
		line_fields = {field.key: field for field in record.lines}
		lines = []
		for row in raw_lines:
			if not isinstance(row, dict) or set(row) - set(line_fields):
				frappe.throw(_("An item line contains an unsupported field."))
			lines.append(_clean(child_type(record), line_fields, row, scope, policy))
		values[record.line_table] = lines
	return values


def _clean(doctype, fields, payload, scope, policy):
	values = {}
	for key, field in fields.items():
		if key == "territory" and policy != PILOT:
			if key in payload and payload[key] != scope.territory:
				frappe.throw(_("This territory is outside your Field Sales assignment."), frappe.PermissionError)
			values[key] = scope.territory
			continue
		value = payload.get(key)
		if value in (None, "") or isinstance(value, str) and not value.strip():
			if field.required:
				_missing(doctype, field)
			continue
		df = docfield(doctype, field)
		kind = input_kind(df, field)
		if kind == "number":
			zero_allowed = doctype == REPORT and key == "quantity"
			if (type(value) not in (float, int) or not math.isfinite(value)
				or value > 10**12 or value < 0 or not zero_allowed and value == 0):
				frappe.throw(_("{0} must be a valid quantity or amount.").format(_(field.label or df.label)))
		elif kind == "check":
			if type(value) is not bool:
				frappe.throw(_("A checkbox has an invalid value."))
		else:
			limit = 5_600_000 if key == ATTACHMENT else 4000 if kind == "notes" else 140
			if not isinstance(value, str) or len(value) > limit:
				frappe.throw(_("{0} has an invalid value or is too long.").format(_(field.label or df.label)))
			value = value.strip()
			if kind == "date":
				if len(value) != 10 or str(getdate(value)) != value:
					frappe.throw(_("Use a valid date in {0}.").format(_(field.label or df.label)))
			elif kind == "select" and value not in choices(df):
				frappe.throw(_("Select a valid value for {0}.").format(_(field.label or df.label)))
			elif kind == "link":
				filters = link_filters(df.options, key, scope, policy, payload)
				if "name" in filters:
					allowed = filters.pop("name")
					if (isinstance(allowed, list) and value not in allowed[1]
						or isinstance(allowed, str) and allowed != value):
						_invalid_link(field, df)
				if not frappe.has_permission(df.options, "read") and not frappe.has_permission(df.options, "select"):
					_invalid_link(field, df)
				if not frappe.get_list(df.options, filters={"name": value, **filters}, pluck="name", limit=1):
					_invalid_link(field, df)
		values[key] = value
	return values


def _missing(doctype, field):
	frappe.throw(_("{0} is required.").format(_(field.label or docfield(doctype, field).label)))


def _invalid_link(field, df):
	frappe.throw(_("{0} is unavailable for this record.").format(_(field.label or df.label)), frappe.PermissionError)
