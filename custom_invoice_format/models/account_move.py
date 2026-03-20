from odoo import models, fields

class AccountMove(models.Model):
    _inherit = 'account.move'

    dispatch_doc_no = fields.Char(string='Dispatch Doc No.')
    dispatch_through = fields.Char(string='Dispatched Through')
    destination = fields.Char(string='Destination')
    terms_of_delivery = fields.Text(string='Terms of Delivery')
    
    supplier_reference = fields.Char(string='Supplier Reference')
    other_reference = fields.Char(string='Other Reference')
    
    delivery_note = fields.Char(string='Delivery Note')
    delivery_note_date = fields.Date(string='Delivery Note Date')
    
    mode_of_payment = fields.Char(string='Mode/Terms of Payment')
    
    buyers_order_no = fields.Char(string="Buyer's Order No.")
    buyers_order_date = fields.Date(string="Buyer's Order Date")
