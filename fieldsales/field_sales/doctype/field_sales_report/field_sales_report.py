import frappe
from frappe import _
from frappe.model.document import Document

from fieldsales.field_sales.access import require_officer
from fieldsales.field_sales.mobile_schema import REPORTS


class FieldSalesReport(Document):
	def before_insert(self):
		if not self.flags.fieldsales_mobile_report:
			frappe.throw(_("Use the Field Sales mobile form to create this report."), frappe.PermissionError)
		scope, _policy = require_officer()
		if self.company != scope.company or self.territory != scope.territory or self.report_type not in REPORTS:
			frappe.throw(_("This report is outside your Field Sales scope."), frappe.PermissionError)

	def validate(self):
		previous = self.get_doc_before_save()
		if not previous:
			return
		for field in self.meta.fields:
			if not field.permlevel and self.get(field.fieldname) != previous.get(field.fieldname):
				frappe.throw(_("The original field report is read-only."))
		if self.review_status != "Pending Review" and not (self.review_notes or "").strip():
			frappe.throw(_("Add review notes before changing the review status."))
