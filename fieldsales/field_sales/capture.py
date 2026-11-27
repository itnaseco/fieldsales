import hashlib
import json
import math
from datetime import UTC, datetime
from uuid import UUID

import frappe
from frappe import _

from fieldsales.field_sales.customers import check_customer, check_outlet


INTAKE = "Field Sales Customer Intake"
VISIT = "Field Sales Visit"
COMPLAINT = "Field Sales Complaint"
RECEIPT = "Field Sales Sync Receipt"
KINDS = {"customer_intake": INTAKE, "visit": VISIT, "complaint": COMPLAINT}
TEXT_FIELDS = {
	INTAKE: {"customer_name": 140, "outlet_name": 140, "contact_name": 140, "phone": 80, "landmark": 2000, "location_reason": 500},
	VISIT: {"outcome": 2000, "next_action": 2000, "location_reason": 500},
	COMPLAINT: {"reporter_name": 140, "reporter_phone": 80, "dealer_reference": 140, "batch_reference": 140, "description": 4000},
}
LINK_FIELDS = {"customer", "outlet", "customer_intake"}


def save(assignment, kind, external_id, mutation_id, payload):
	doctype = _doctype(kind)
	external_id = _uuid(external_id)
	mutation_id = _uuid(mutation_id)
	user = frappe.session.user
	if not isinstance(payload, dict):
		frappe.throw(_("The capture payload must be an object."))
	try:
		encoded = json.dumps([kind, external_id, payload], sort_keys=True, allow_nan=False)
	except (TypeError, ValueError):
		frappe.throw(_("Invalid capture data."))
	if len(encoded) > 32000:
		frappe.throw(_("The capture is too large."))
	fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
	data = _validate(doctype, payload)
	frappe.db.savepoint("field_sales_capture")
	try:
		frappe.get_doc({
			"doctype": RECEIPT, "mutation_id": mutation_id, "fingerprint": fingerprint,
			"actor": user, "target_type": doctype, "target_name": external_id, **assignment,
		}).insert(ignore_permissions=True)
	except frappe.DuplicateEntryError:
		frappe.db.rollback(save_point="field_sales_capture")
		return _replay(assignment, mutation_id, fingerprint)

	try:
		if doctype in (VISIT, COMPLAINT):
			_check_source(assignment, doctype, data)
		frappe.get_doc({
			"doctype": doctype, "external_id": external_id, **assignment, **data,
		}).insert(ignore_permissions=True)
	except frappe.DuplicateEntryError:
		frappe.db.rollback(save_point="field_sales_capture")
		frappe.throw(_("This capture ID is already in use."))
	return {"name": external_id, "review_status": "Pending Review"}


def statuses(assignment, references):
	if not isinstance(references, list) or len(references) > 50:
		frappe.throw(_("Send up to 50 capture references."))
	results = []
	for reference in references:
		if not isinstance(reference, dict):
			frappe.throw(_("Invalid capture reference."))
		doctype = _doctype(reference.get("kind"))
		name = _uuid(reference.get("name"))
		status = frappe.db.get_value(doctype, {
			"name": name, "owner": frappe.session.user, **assignment,
		}, "review_status")
		results.append({"name": name, "review_status": status or "Unavailable"})
	return results


def _replay(assignment, mutation_id, fingerprint):
	receipt = frappe.db.get_value(
		RECEIPT, mutation_id,
		["actor", "company", "territory", "fingerprint", "target_type", "target_name"],
		as_dict=True, for_update=True,
	)
	if not receipt or receipt.actor != frappe.session.user or any(receipt[key] != value for key, value in assignment.items()):
		frappe.throw(_("This capture is outside your current assignment."), frappe.PermissionError)
	if receipt.fingerprint != fingerprint:
		frappe.throw(_("This submission ID has already been used with different data."))
	status = frappe.db.get_value(receipt.target_type, receipt.target_name, "review_status", for_update=True)
	return {"name": receipt.target_name, "review_status": status or "Unavailable"}


def _validate(doctype, payload):
	text_fields = TEXT_FIELDS[doctype]
	values = {key: _text(payload, key, length) for key, length in text_fields.items()}
	values["captured_at_utc"] = _timestamp(payload.get("captured_at_utc"))
	for key in (LINK_FIELDS if doctype in (VISIT, COMPLAINT) else set()):
		values[key] = _text(payload, key, 140)
	select = {INTAKE: "channel", VISIT: "purpose", COMPLAINT: "category"}[doctype]
	values[select] = _select(doctype, payload, select)
	if doctype != COMPLAINT:
		values.update(_location(doctype, payload))
	if set(payload) - set(values):
		frappe.throw(_("The capture contains unsupported fields."))
	for key, value in values.items():
		field = frappe.get_meta(doctype).get_field(key)
		if field.reqd and value in (None, ""):
			frappe.throw(_("{0} is required.").format(_(field.label)))
	return values


def _check_source(assignment, doctype, values):
	customer, outlet, intake = (values[key] for key in ("customer", "outlet", "customer_intake"))
	if intake:
		if customer or outlet:
			frappe.throw(_("Choose a customer or an intake reference."))
		status = frappe.db.get_value(INTAKE, {"name": intake, "owner": frappe.session.user, **assignment}, "review_status")
		if not status or status == "Rejected":
			frappe.throw(_("This intake is outside your assignment."), frappe.PermissionError)
	elif customer:
		check_customer(assignment.territory, customer)
		if outlet:
			check_outlet(customer, outlet)
		elif doctype == VISIT:
			frappe.throw(_("Choose an outlet for this visit."))
	elif outlet or doctype == VISIT:
		frappe.throw(_("Choose a customer outlet or an intake reference."))


def _location(doctype, payload):
	location = _select(doctype, payload, "location_status")
	limits = {"latitude": (-90, 90), "longitude": (-180, 180), "accuracy_m": (0, 100000)}
	values = {"location_status": location}
	for key, (low, high) in limits.items():
		value = payload.get(key)
		if location == "GPS":
			if type(value) not in (float, int) or not low <= value <= high or not math.isfinite(value):
				frappe.throw(_("Invalid GPS coordinates or accuracy."))
		elif value is not None:
			frappe.throw(_("Remove coordinates when GPS is unavailable."))
		values[key] = value
	if location == "Unavailable" and not _text(payload, "location_reason", 500):
		frappe.throw(_("Explain why GPS was unavailable."))
	return values


def _text(payload, key, limit):
	value = payload.get(key, "")
	if not isinstance(value, str) or len(value.strip()) > limit:
		frappe.throw(_("A capture field contains invalid text."))
	return value.strip()


def _select(doctype, payload, key):
	value = payload.get(key)
	if value not in frappe.get_meta(doctype).get_field(key).options.splitlines():
		frappe.throw(_("Choose a valid option."))
	return value


def _doctype(kind):
	if not isinstance(kind, str) or kind not in KINDS:
		frappe.throw(_("Unknown field capture type."))
	return KINDS[kind]


def _uuid(value):
	try:
		parsed = UUID(value)
		if parsed.version == 4 and str(parsed) == value:
			return value
	except (TypeError, AttributeError, ValueError):
		pass
	frappe.throw(_("Invalid capture identifier."))


def _timestamp(value):
	try:
		timestamp = datetime.fromisoformat(value)
		if timestamp.tzinfo is not None and 2000 <= timestamp.year <= 2100:
			return timestamp.astimezone(UTC).replace(tzinfo=None)
	except (TypeError, ValueError):
		pass
	frappe.throw(_("The capture time must include its time zone."))
