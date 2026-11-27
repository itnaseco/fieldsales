from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
	key: str
	required: bool = False
	label: str | None = None
	kind: str | None = None


@dataclass(frozen=True)
class Record:
	doctype: str
	title: str
	fields: tuple[Field, ...] = ()
	status: str | None = None
	line_table: str | None = None
	lines: tuple[Field, ...] = ()
	report_type: str | None = None
	employee: bool = False


REPORT = "Field Sales Report"
ATTACHMENT = "attachment"
F = Field
CUSTOMER = F("customer", True)
OUTLET = F("outlet")
DATE = F("activity_date", True)
ITEM = F("item", True)
ORDER = F("sales_order", True)
WAREHOUSE = F("warehouse", True)
QTY = F("quantity", True)
NOTES = F("notes", True)
PHOTO = F(ATTACHMENT, kind="photo")
AMOUNT = (F("amount", True), F("currency", True))
DETAIL = (F("reference"), NOTES)


def report(report_type, *fields):
	return Record(
		REPORT, "subject", (F("subject", True, "Title"), DATE, *fields),
		"review_status", report_type=report_type,
	)


RECORDS = {
	"customers": Record("Customer", "customer_name", (
		F("customer_name", True), F("customer_type", True), F("customer_group", True),
		F("territory", True),
	)),
	"outlets": Record("Address", "address_title", (
		CUSTOMER, F("address_title", True, "Outlet name"), F("address_type", True),
		F("address_line1", True), F("address_line2"), F("city", True),
		F("state", label="District or state"), F("country", True), F("phone"),
	)),
	"contacts": Record("Contact", "full_name", (
		CUSTOMER, F("first_name", True), F("last_name"),
		F("email_id", label="Email"), F("mobile_no", label="Mobile number"),
	)),
	"orders": Record("Sales Order", "customer_name", (
		CUSTOMER, F("customer_address", True, "Delivery outlet"),
		F("delivery_date", True, "Requested delivery date"), F("po_no", label="Customer order reference"),
	), "status", "items", (
		F("item_code", True), F("qty", True), F("uom"),
	)),
	"bank_evidence": report(
		"Bank Payment Evidence", CUSTOMER, ORDER, *AMOUNT,
		F("reference", label="Bank reference"),
		F(ATTACHMENT, True, "Bank receipt photo", "photo"),
	),
	"collections": report(
		"Collection", CUSTOMER, F("sales_order"), *AMOUNT, F("payment_method", True),
		F("reference", True, "Receipt or collection reference"), F("notes"), PHOTO,
	),
	"deliveries": report(
		"Delivery Proof", CUSTOMER, ORDER, F("outlet", True), F("delivery_note"),
		F("fulfillment_route", True), ITEM, F("batch"),
		F("quantity", True, "Quantity accepted"), F("uom", True),
		F("contact_name", True, "Receiver"), F("notes", label="Shortage, refusal or delivery notes"), PHOTO,
	),
	"returns": report(
		"Return or Discrepancy", CUSTOMER, F("delivery_note", True), OUTLET,
		ITEM, F("batch"), QTY, F("uom", True), F("notes", True, "Reason and condition"), PHOTO,
	),
	"stock_handovers": report(
		"Stock Handover", WAREHOUSE, ITEM, F("batch"), QTY, F("uom", True),
		F("reference", True, "Transfer or hub reference"), F("contact_name", True, "Handed over by"),
		F("notes", label="Shortage or exception"), PHOTO,
	),
	"stock_counts": report(
		"Stock Count", WAREHOUSE, ITEM, F("batch"),
		F("quantity", True, "Counted quantity"), F("uom", True), F("notes"), PHOTO,
	),
	"events": report(
		"Event Participation", F("event_type", True), F("location", True, "Venue"),
		F("customer", label="Customer or dealer"), F("notes", True, "Activities and follow-up"), PHOTO,
	),
	"demo_farms": report(
		"Demo Farm", F("contact_name", True, "Host"), F("location", True, "Location or GPS pin"),
		F("plot_label", True), ITEM, F("quantity", label="Plot area (m²)"), F("notes", True, "Objective"), PHOTO,
	),
	"demo_observations": report(
		"Demo Observation", F("related_report", True, "Demo farm"),
		F("milestone", True), F("location", label="Location or GPS pin"),
		F("notes", True, "Findings and next action"), PHOTO,
	),
	"leave": Record("Leave Application", "leave_type", (
		F("leave_type", True), F("from_date", True), F("to_date", True),
		F("half_day"), F("half_day_date"), F("description", label="Reason"),
	), "status", employee=True),
	"advances": Record("Employee Advance", "purpose", (
		F("purpose", True), F("advance_amount", True), F("posting_date", True, "Request date"),
	), "status", employee=True),
	"attendance_requests": Record("Attendance Request", "from_date", (
		F("from_date", True), F("to_date", True), F("reason", True), F("explanation", True),
	), employee=True),
	"expenses": Record("Expense Claim", "name", (), "status", "expenses", (
		F("expense_date", True), F("expense_type", True), F("amount", True), F("description"),
	), employee=True),
	"attendance": Record("Attendance", "attendance_date", status="status", employee=True),
	"commissions": Record("Employee Incentive", "payroll_date", employee=True),
	"stock": Record("Bin", "item_code"),
	"daily_close": Record(REPORT, "subject", status="review_status"),
	"customer_intakes": Record("Field Sales Customer Intake", "customer_name", status="review_status"),
	"visits": Record("Field Sales Visit", "outcome", status="review_status"),
	"complaints": Record("Field Sales Complaint", "reporter_name", status="review_status"),
	"followups": Record("Field Sales Visit", "next_action", status="review_status"),
}

REPORTS = {record.report_type: record for record in RECORDS.values() if record.report_type}
