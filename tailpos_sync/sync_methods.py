import frappe

import datetime
import json

from .utils import get_items_with_price_list_query


def get_tables_for_sync():
    return ['Item', 'Customer', 'Categories', 'Discounts', 'Attendants']


def get_item_query():
    use_price_list = frappe.db.get_single_value('Tail Settings', 'use_price_list')

    columns = [
        'tabItem.id',
        'tabItem.sku',
        'tabItem.name',
        'tabItem.color',
        'tabItem.shape',
        'tabItem.image',
        'tabItem.barcode',
        'tabItem.category',
        'tabItem.favorite',
        'tabItem.stock_uom',
        'tabItem.item_name',
        'tabItem.color_or_image',
    ]

    standard_rate = 'standard_rate'

    if use_price_list:
        standard_rate = '`tabItem Price`.price_list_rate as standard_rate'

    columns.append(standard_rate)

    return get_items_with_price_list_query(columns)


def get_table_select_query(table, force_sync=True, pos_profile=None):

    query = "SELECT * FROM `tab{0}`".format(table)

    if table == 'Item':
        query = get_item_query()

    if not force_sync:
        connector = " AND " if "WHERE" in query else " WHERE "
        query = query + connector + "`modified` > `date_updated`"

    return query


def insert_data(data, frappe_table, receipt_total):
    sync_object = data['syncObject']
    db_name = data['dbName']

    for key, value in sync_object.iteritems():
        field_name = str(key).lower()

        if field_name == "taxes":
            value = ""

        if field_name == "soldby":
            field_name = "stock_uom"

        if field_name == "colorandshape":
            color = json.loads(value)[0]['color'].capitalize()
            color_fix = {
                'Darkmagenta': 'Dark Magenta',
                'Darkorange': 'Dark Orange',
                'Firebrick': 'Fire Brick'
            }
            if color in color_fix.keys():
                color = color_fix[color]
            frappe_table.db_set("color", color)
            frappe_table.db_set("shape", json.loads(value)[0]['shape'].capitalize())

        if field_name == "colororimage":
            field_name = "color_or_image"

        if field_name == "imagepath":
            field_name = "image"

        if field_name == "price":
            field_name = "standard_rate"

        if db_name != "Customer":
            if field_name == "name":
                field_name = "description"

        elif db_name == "Customer":
            if field_name == "name":
                field_name = "customer_name"

        if field_name == "category":
            category_value = get_category(value)
            value = category_value

        if value == "No Category":
            value = ""

        if value == "fixDiscount":
            frappe_table.db_set("type", "Fix Discount")

        if value == "percentage":
            frappe_table.db_set("type", "Percentage")

        if field_name == "date":
            if value:
                if db_name != "Receipts":
                    value = datetime.datetime.fromtimestamp(value / 1000.0).date()
                else:
                    value = datetime.datetime.fromtimestamp(value / 1000.0).date()
        elif field_name == "shift_beginning" or field_name == "shift_end":
            if value:
                value = datetime.datetime.fromtimestamp(value / 1000.0)
        elif field_name == "lines":
            value = json.dumps(value)
        try:
            frappe_table.db_set(field_name, value)
        except:
            None
    try:
        if db_name == "Receipts":
            try:
                frappe_table.db_set("total_amount", receipt_total)
            except Exception:
                print(frappe.get_traceback())
    except Exception:
        print(frappe.get_traceback())


def deleted_documents():
    tables = get_tables_for_sync()
    tableNames = ["Items", "Categories", "Discounts", "Attendants", "Customer"]
    returnArray = []

    for i in range(0, len(tables)):

        data = frappe.db.sql(""" SELECT data FROM `tabDeleted Document` WHERE deleted_doctype=%s""", (tables[i]),
                             as_dict=True)

        for x in data:
            try:
                if json.loads(x.data)['id'] != None and x.sync_status == None:
                    returnArray.append({
                        'tableNames': tableNames[i],
                        '_id': json.loads(x.data)['id']
                    })
            except Exception:
                print(frappe.get_traceback())
            try:
                frappe.db.sql(""" UPDATE `tabDeleted Document` SET sync_status=%s WHERE data=%s""", ('true', x.data),
                              as_dict=True)
            except Exception:
                print(frappe.get_traceback())

    return returnArray


def sync_from_erpnext(device=None, force_sync=True):
    data = []
    tables = get_tables_for_sync()

    if device:
        pos_profile = frappe.db.get_value('Device', device, 'pos_profile')

    for table in tables:
        query = get_table_select_query(table, force_sync, pos_profile=pos_profile)
        query_data = frappe.db.sql(query, as_dict=True)
        sync_data = update_sync_data(query_data, table)

        if sync_data:
            data.extend(sync_data)

    return data


# DEPRECATED
def force_sync_from_erpnext_to_tailpos(device=None):
    """
    Fetches all data in ERPNext.

    :param device:
    :return data:
    """
    data = []
    tables = get_tables_for_sync()

    if device:
        pos_profile = frappe.db.get_value('Device', device, 'pos_profile')

    try:
        for table in tables:
            query = get_table_select_query(table, pos_profile=pos_profile)
            query_data = frappe.db.sql(query, as_dict=True)
            sync_data = update_sync_data(query_data, table)
            data.extend(sync_data)
    except Exception:
        print(frappe.get_traceback())

    return data


# DEPRECATED
def sync_from_erpnext_to_tailpos(device=None):
    """
    Fetch added/updated data in ERPNext.

    :param device: name of the Device doctype
    :return data: sync data
    """
    data = []
    tables = get_tables_for_sync()

    if device:
        pos_profile = frappe.db.get_value('Device', device, 'pos_profile')

    for table in tables:
        query = get_table_select_query(table, False, pos_profile=pos_profile)
        query_data = frappe.db.sql(query, as_dict=True)

        # Kung naay sulod
        if len(query_data) > 0:
            sync_data = update_sync_data(query_data, table)
            data.extend(sync_data)

    return data


def delete_records(data):
    for check in data:
        check_existing_deleted_item = frappe.db.sql("SELECT * FROM" + "`tab" + check['table_name'] + "` WHERE id=%s ",
                                                    (check['trashId']))
        if len(check_existing_deleted_item) > 0:
            frappe.db.sql("DELETE FROM" + "`tab" + check['table_name'] + "` WHERE id=%s ",
                          (check['trashId']))


def deleted_records_check(id, array):
    status = True
    for i in array:
        if i['_id'] == id:
            status = False
    return status


def new_doc(data, owner='Administrator'):
    db_name = data['dbName']
    sync_object = data['syncObject']

    doc = {
        'doctype': db_name,
        'owner': owner,
        'id': sync_object['_id'],
    }

    if db_name == 'Item':
        doc.update({
            'item_group': 'All Item Groups',
            'item_name': sync_object['name'],
            'item_code': sync_object['name'],
            'sku': sync_object['sku'],
            'barcode': sync_object['barcode'],
            'standard_rate': sync_object['price']
        })

    elif db_name == 'Customer':
        doc.update({
            'customer_name': sync_object['name']
        })

    elif db_name == 'Categories':
        doc.update({
            'description': sync_object['name']
        })

    elif db_name == 'Discounts':
        doc.update({
            'description': sync_object['name'],
            'value': sync_object['value'],
            'percentagetype': sync_object['percentageType']
        })

    elif db_name == 'Attendants':
        doc.update({
            'user_name': sync_object['user_name'],
            'pin_code': sync_object['pin_code'],
            'role': sync_object['role']
        })

    elif db_name == 'Shifts':
        doc.update({
            'attendant': sync_object['attendant'],
            'beginning_cash': sync_object['beginning_cash'],
            'ending_cash': sync_object['ending_cash'],
            'actual_money': sync_object['actual_money'],
            'shift_end': get_date_fromtimestamp(sync_object['shift_end']),
            'shift_beginning': get_date_fromtimestamp(sync_object['shift_beginning'])
        })

    elif db_name == 'Payments':
        doc.update({
            'paid': sync_object['paid'],
            'type': sync_object['type'],
            'receipt': sync_object['receipt'],
            'date': get_date_fromtimestamp(sync_object['date'])
        })

    elif db_name == 'Receipts':
        doc.update({
            'status': sync_object['status'].capitalize(),
            'shift': sync_object['shift'],
            'customer': sync_object['customer'],
            'attendant': sync_object['attendant'],
            'taxesvalue': sync_object['taxesValue'],
            'discount': sync_object['discount'],
            'reason': sync_object['reason'],
            'deviceid': sync_object['deviceId'],
            'discountvalue': sync_object['discountValue'],
            'receiptnumber': sync_object['receiptNumber'],
            'discounttype': sync_object['discountType'].title(),
            'date': get_date_fromtimestamp(sync_object['date']),
            'receipt_lines': get_receipt_lines(sync_object['lines']),
        })

    return frappe.get_doc(doc)


def get_receipt_lines(lines):
    receipt_lines = []

    for line in lines:
        receipt_lines.append({
            'item': line['item'],
            'item_name': line['item_name'],
            'sold_by': line['sold_by'],
            'price': line['price'],
            'qty': line['qty']
        })

    return receipt_lines


def uom_check():
    each = frappe.db.sql(""" SELECT * FROM `tabUOM` WHERE name='Each'""")

    if len(each) == 0:
        try:
            frappe.get_doc({
                'doctype': 'UOM',
                'name': 'Each',
                'uom_name': 'Each'
            }).insert(ignore_permissions=True)
        except Exception:
            print(frappe.get_traceback())

    weight = frappe.db.sql(""" SELECT * FROM `tabUOM` WHERE name='Weight'""")
    if len(weight) == 0:
        frappe.get_doc({
            'doctype': 'UOM',
            'name': 'Weight',
            'uom_name': 'Weight'
        }).insert(ignore_permissions=True)


def get_category(id):
    print(id)
    print("CATEGORY")
    try:
        data = frappe.db.sql(""" SELECT description FROM `tabCategories` WHERE id=%s """, (id), as_dict=True)
    except Exception:
        print(frappe.get_traceback())
    data_value = ""
    print(data)
    if len(data) > 0:
        if data[0]['description']:
            data_value = data[0]['description']
    return data_value


def get_date_fromtimestamp(timestamp):
    return datetime.datetime.fromtimestamp(timestamp / 1000.0).date()


def update_sync_data(data, table):
    res = []

    for datum in data:
        res.append({
            'tableNames': table,
            'syncObject': datum
        })
        frappe.db.sql("UPDATE `tab" + table + "` SET `date_updated`=`modified` where id=%s", datum.id)

    return res
