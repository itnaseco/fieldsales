import frappe
from frappe import _
from frappe.model.document import Document

from fieldsales.field_sales.access import review_customer_territory
from fieldsales.field_sales.customers import check_customer, check_outlet


class CaptureRecord(Document):
	def validate(self):
		previous = self.get_doc_before_save()
		if not previous:
			return
		for field in self.meta.fields:
			if not field.permlevel and self.get(field.fieldname) != previous.get(field.fieldname):
				frappe.throw(_("The original field capture is read-only."))
		if self.review_status != "Pending Review" and not (self.review_notes or "").strip():
			frappe.throw(_("Enter review notes before changing the review status."))
		if self.doctype == "Field Sales Customer Intake" and self.review_status == "Linked":
			if not self.linked_customer or not self.linked_address:
				frappe.throw(_("Select both the existing Customer and its outlet Address."))
			check_customer(review_customer_territory(self), self.linked_customer)
			check_outlet(self.linked_customer, self.linked_address)
		if self.doctype == "Field Sales Complaint" and self.support_issue != previous.support_issue:
			self._check_support_issue()

	def _check_support_issue(self):
		if not self.support_issue:
			return
		issue = frappe.get_doc("Issue", self.support_issue)
		issue.check_permission("read")
		if issue.company != self.company or (self.customer and issue.customer != self.customer):
			frappe.throw(_("Choose a Support Issue for this company and customer."), frappe.PermissionError)
		if issue.customer:
			check_customer(review_customer_territory(self), issue.customer)
