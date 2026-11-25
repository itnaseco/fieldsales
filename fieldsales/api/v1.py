import frappe

from fieldsales import __version__


@frappe.whitelist(allow_guest=True, methods=["GET"])
def health() -> dict[str, str]:
	"""Return the minimal public contract needed for client connectivity checks."""
	return {
		"app": "fieldsales",
		"app_version": __version__,
		"api_version": "v1",
		"status": "ok",
	}
