import base64
import binascii
import hashlib
import json
from io import BytesIO

import frappe
from frappe import _
from frappe.utils import nowdate
from PIL import Image

from fieldsales.field_sales import capture
from fieldsales.field_sales.mobile_fields import prepare_values
from fieldsales.field_sales.mobile_native import build_document
from fieldsales.field_sales.mobile_schema import ATTACHMENT, REPORT
from fieldsales.field_sales.mobile_scope import CAPTURES, can_create, read_scope


PAGE = 30


def list_records(kind, record, scope, policy, start):
	if not 0 <= start <= 10000:
		frappe.throw(_("Invalid record page."))
	doctype = record.doctype
	creatable = can_create(record, scope)
	filters, notice = read_scope(record, scope, policy)
	if notice:
		return {"rows": [], "can_create": creatable, "notice": notice}
	fields = ["name", "modified", record.title]
	if record.status:
		fields.append(record.status)
	if frappe.get_meta(doctype).is_submittable:
		fields.append("docstatus")
	extras = {
		"stock": ["warehouse", "actual_qty", "stock_uom"],
		"commissions": ["incentive_amount", "currency", "salary_component"],
	}.get(kind, [])
	fields = list(dict.fromkeys(fields + extras))
	query = {"fields": fields, "order_by": "modified desc, name desc", "limit": PAGE + 1, "start": start}
	if doctype in ("Address", "Contact"):
		names = frappe.get_all(
			capture.RECEIPT, filters=dict(scope, actor=frappe.session.user, target_type=doctype),
			order_by="creation desc", start=start, limit=PAGE + 1, pluck="target_name",
		)
		query["start"] = 0
		rows = frappe.get_list(doctype, filters={"name": ["in", names[:PAGE]]}, **query) if names else []
		has_next = len(names) > PAGE
	else:
		if kind == "followups":
			filters["next_action"] = ["is", "set"]
			filters["review_status"] = ["!=", "Rejected"]
		elif kind == "daily_close":
			filters["activity_date"] = nowdate()
			filters["review_status"] = ["in", ["Pending Review", "In Review"]]
			filters["report_type"] = ["in", [
				"Bank Payment Evidence", "Collection", "Delivery Proof",
				"Return or Discrepancy", "Stock Handover", "Stock Count",
			]]
		read = frappe.get_all if doctype in CAPTURES else frappe.get_list
		rows = read(doctype, filters=filters, **query)
		has_next = len(rows) > PAGE
	return {
		"rows": [_row(record, row) for row in rows[:PAGE]], "can_create": creatable,
		"next_start": start + PAGE if has_next else None,
	}


def create_record(kind, record, scope, policy, mutation_id, payload):
	if not can_create(record, scope):
		frappe.throw(_("Your account does not have permission to create this record."), frappe.PermissionError)
	mutation_id = capture._uuid(mutation_id)
	try:
		encoded = json.dumps([kind, policy, payload], sort_keys=True, allow_nan=False)
	except (ValueError, TypeError):
		frappe.throw(_("This record contains invalid data."))
	if len(encoded) > 5_650_000:
		frappe.throw(_("The form is too large. Choose a smaller photo."))
	fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
	actor = frappe.session.user
	frappe.db.savepoint("field_sales_document")
	try:
		frappe.get_doc({
			"doctype": capture.RECEIPT, "mutation_id": mutation_id, "actor": actor,
			"fingerprint": fingerprint, "target_type": record.doctype,
			"target_name": mutation_id, **scope,
		}).insert(ignore_permissions=True)
	except frappe.DuplicateEntryError:
		frappe.db.rollback(save_point="field_sales_document")
		receipt = frappe.db.get_value(
			capture.RECEIPT, mutation_id,
			["actor", "company", "territory", "fingerprint", "target_type", "target_name"],
			as_dict=True, for_update=True,
		)
		return _replay(receipt, record, scope, actor, fingerprint)

	values = prepare_values(record, payload, scope, policy)
	photo = _decode_photo(values.pop(ATTACHMENT)) if ATTACHMENT in values else None
	if record.doctype == REPORT:
		_validate_report(kind, values)
		doc = frappe.get_doc({
			"doctype": REPORT, "external_id": mutation_id, **scope, "report_type": record.report_type, **values,
		})
		doc.flags.fieldsales_mobile_report = True
	else:
		doc = build_document(record, values, scope)
	doc.insert()
	if photo:
		content, extension = photo
		file = frappe.get_doc({
			"doctype": "File", "file_name": f"{doc.name}-evidence.{extension}",
			"content": content, "attached_to_doctype": doc.doctype,
			"attached_to_name": doc.name, "attached_to_field": ATTACHMENT, "is_private": 1,
		}).insert(ignore_permissions=True)
		doc.db_set(ATTACHMENT, file.file_url, update_modified=False)
	frappe.db.set_value(capture.RECEIPT, mutation_id, "target_name", doc.name, update_modified=False)
	return _row(record, doc)


def _validate_report(kind, values):
	if kind == "deliveries":
		order = values["sales_order"]
		if not frappe.db.exists("Sales Order Item", {"parent": order, "item_code": values["item"]}):
			frappe.throw(_("This item is not on the selected sales order."))
		order_outlet = frappe.db.get_value("Sales Order", order, "customer_address")
		if order_outlet and order_outlet != values["outlet"]:
			frappe.throw(_("Choose the delivery outlet on the sales order."))
		if values["quantity"] == 0 and not values.get("notes"):
			frappe.throw(_("Explain what prevented the handover."))
		if values.get("delivery_note") and not frappe.db.exists("Delivery Note Item", {
			"parent": values["delivery_note"], "against_sales_order": order, "item_code": values["item"],
		}):
			frappe.throw(_("This delivery note does not contain the selected order item."))
	elif kind == "returns" and not frappe.db.exists("Delivery Note Item", {
		"parent": values["delivery_note"], "item_code": values["item"],
	}):
		frappe.throw(_("This item is not on the selected delivery note."))
	if kind in ("returns", "stock_handovers") and not values["quantity"]:
		frappe.throw(_("Enter a quantity greater than zero."))


def _replay(receipt, record, scope, actor, fingerprint):
	if (not receipt or receipt.actor != actor or receipt.target_type != record.doctype
		or any(receipt[key] != value for key, value in scope.items())):
		frappe.throw(_("This submission is unavailable to your account."), frappe.PermissionError)
	if receipt.fingerprint != fingerprint:
		frappe.throw(_("This submission already exists. Reopen the list to confirm the result."))
	doc = frappe.get_doc(record.doctype, receipt.target_name)
	doc.check_permission("read")
	return _row(record, doc)


def _row(record, doc):
	title = doc.get(record.title) or doc.name
	if record.doctype == "Bin":
		status = f"{doc.actual_qty:g} {doc.stock_uom or ''} · {doc.warehouse}"
	elif record.doctype == "Employee Incentive":
		state = "Submitted" if doc.docstatus == 1 else "Draft"
		status = f"{doc.currency} {doc.incentive_amount:g} · {state}"
	elif record.doctype == "Attendance Request":
		status = "Submitted" if doc.docstatus == 1 else "Draft"
	else:
		status = doc.get(record.status) if record.status else None
	return {"name": doc.name, "title": str(title), "status": status, "modified": str(doc.modified)}


def _decode_photo(value):
	try:
		content = base64.b64decode(value, validate=True)
	except (ValueError, binascii.Error):
		frappe.throw(_("Choose a readable JPEG or PNG photo."))
	if len(content) <= 4 * 1024 * 1024:
		try:
			with Image.open(BytesIO(content), formats=["JPEG", "PNG"]) as image:
				if image.width * image.height <= 20_000_000:
					extension = "jpg" if image.format == "JPEG" else "png"
					image.verify()
					return content, extension
		except (OSError, SyntaxError, Image.DecompressionBombError):
			pass
	frappe.throw(_("Choose a valid JPEG or PNG photo under 4 MB."))
