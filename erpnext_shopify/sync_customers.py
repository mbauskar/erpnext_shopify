import frappe
from frappe import _
from .exceptions import ShopifyError
from .shopify_requests import get_shopify_customers, post_request, put_request

def sync_customers():
	shopify_customer_list = []
	sync_shopify_customers(shopify_customer_list)
	sync_erpnext_customers()

def sync_shopify_customers(shopify_customer_list):
	for shopify_customer in get_shopify_customers():
		if not frappe.db.get_value("Customer", {"shopify_customer_id": shopify_customer.get('id')}, "name"):
			create_customer(shopify_customer, shopify_customer_list)

def create_customer(shopify_customer, shopify_customer_list):
	erp_cust = None
	
	cust_name = (shopify_customer.get("first_name") + " " + (shopify_customer.get("last_name") \
		and  shopify_customer.get("last_name") or "")) if shopify_customer.get("first_name")\
		 else shopify_customer.get("email")
	
	try:
		customer = frappe.get_doc({
			"doctype": "Customer",
			"name": shopify_customer.get("id"),
			"customer_name" : cust_name,
			"shopify_customer_id": shopify_customer.get("id"),
			"sync_with_shopify": 1,
			"customer_group": _("Commercial"),
			"territory": _("All Territories"),
			"customer_type": _("Company")
		}).insert()
	except Exception, e:
		raise e

	if customer:
		create_customer_address(customer, shopify_customer)

def create_customer_address(customer, shopify_customer):
	for i, address in enumerate(shopify_customer.get("addresses")):		
		address_title, address_type = get_address_title_and_type(customer.customer_name, i)	
		
		frappe.get_doc({
			"doctype": "Address",
			"shopify_address_id": address.get("id"),
			"address_title": address_title,
			"address_type": address_type,
			"address_line1": address.get("address1") or "Address 1",
			"address_line2": address.get("address2"),
			"city": address.get("city") or "City",
			"state": address.get("province"),
			"pincode": address.get("zip"),
			"country": address.get("country"),
			"phone": address.get("phone"),
			"email_id": shopify_customer.get("email"),
			"customer": customer.name,
			"customer_name":  customer.customer_name
		}).insert()

def get_address_title_and_type(customer_name, index):
	address_type = _("Billing")
	address_title = customer_name
	if frappe.db.get_value("Address", "{0}-{1}".format(customer_name.strip(), address_type)):
		address_title = "{0}-{1}".format(customer_name.strip(), index)
		
	return address_title, address_type 
	
def sync_erpnext_customers():
	shopify_settings = frappe.get_doc("Shopify Settings", "Shopify Settings")
	
	condition = ["sync_with_shopify = 1"]
	
	last_sync_condition = ""
	if shopify_settings.last_sync_datetime:
		last_sync_condition = "modified >= '{0}' ".format(shopify_settings.last_sync_datetime)
		condition.append(last_sync_condition)
	
	customer_query = """select name, customer_name, shopify_customer_id from tabCustomer 
		where {0}""".format(" and ".join(condition))
		
	for customer in frappe.db.sql(customer_query, as_dict=1):
		if not customer.shopify_customer_id:
			create_customer_to_shopify(customer)
		else:
			update_customer_to_shopify(customer, last_sync_condition)

def create_customer_to_shopify(customer):
	shopify_customer = {
		"first_name": customer['customer_name']
	}
	
	shopify_customer = post_request("/admin/customers.json", { "customer": shopify_customer})
	
	customer = frappe.get_doc("Customer", customer['name'])
	customer.shopify_customer_id = shopify_customer['customer'].get("id")
	customer.save()
	
	addresses = get_customer_addresses(customer.as_dict())
	for address in addresses:
		sync_customer_address(customer, address)

def sync_customer_address(customer, address):
	address_name = address.pop("name")

	shopify_address = post_request("/admin/customers/{0}/addresses.json".format(customer.shopify_customer_id),
	{"address": address})
		
	address = frappe.get_doc("Address", address_name)
	address.shopify_address_id = shopify_address['customer_address'].get("id")
	address.save()
	
def update_customer_to_shopify(customer, last_sync_condition):
	shopify_customer = {
		"first_name": customer['customer_name']
	}
	
	put_request("/admin/customers/{0}.json".format(customer.shopify_customer_id),\
	{ "customer": shopify_customer})
	
	update_address_details(customer, last_sync_condition)

def update_address_details(customer, last_sync_condition):
	customer_addresses = get_customer_addresses(customer, last_sync_condition)
	for address in customer_addresses:
		if address.shopify_address_id:
			address_name = address.pop("name")
			
			url = "/admin/customers/{0}/addresses/{1}.json".format(customer.shopify_customer_id,\
			 address.shopify_address_id)
			put_request(url, { "address": address})
			
		else:
			sync_customer_address(customer, address)
			
def get_customer_addresses(customer, last_sync_cond=None):
	conditions = ["addr.customer = '{0}' ".format(customer['name'])]
	
	if last_sync_cond:
		conditions.append(last_sync_cond)
	
	address_query = """select addr.name, addr.address_line1 as address1, addr.address_line2 as address2,
		addr.city as city, addr.state as province, addr.country as country, addr.pincode as zip, 
		addr.shopify_address_id as id from tabAddress addr 
		where {0}""".format(' and '.join(conditions)) 
			
	return frappe.db.sql(address_query, as_dict=1)