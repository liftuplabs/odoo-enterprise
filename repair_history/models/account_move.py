from odoo import models, fields

class AccountMove(models.Model):
    _inherit = 'account.move'

    dispatch_doc_no = fields.Char(string="Dispatch Doc No.")
    dispatched_through = fields.Char(string="Dispatched Through")
    destination = fields.Char(string="Destination")
    terms_of_delivery = fields.Text(string="Terms of Delivery")
    remark = fields.Text(string="Remark")
    reference_no = fields.Char(string="Reference No.")
    other_references = fields.Char(string="Other Ref's")
    reference_date = fields.Date(string="Reference Date")