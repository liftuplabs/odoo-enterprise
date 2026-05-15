from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    digital_signature = fields.Binary(string="Digital Signature", help="Upload the authorized signatory signature image here.")
    invoice_layout_boxed = fields.Boolean(string="Use Boxed Invoice Layout", default=True, help="If checked, Company, Consignee, and Buyer details will be stacked inside the main table box.")
    
    # Custom Invoice Design Fields
    custom_invoice_title = fields.Char(string="Invoice Title", default="TAX INVOICE")
    custom_invoice_font_family = fields.Selection([
        ('Arial', 'Arial'),
        ('Helvetica', 'Helvetica'),
        ('Times New Roman', 'Times New Roman'),
        ('Courier New', 'Courier New'),
        ('Verdana', 'Verdana'),
        ('Georgia', 'Georgia')
    ], string="Font Family", default='Arial')
    custom_invoice_border_color = fields.Char(string="Border Color", default="#000000")
    custom_invoice_border_thickness = fields.Integer(string="Border Thickness (px)", default=1)
    custom_invoice_header_bg_color = fields.Char(string="Table Header Background", default="#f0f0f0")
    custom_invoice_header_text_color = fields.Char(string="Table Header Text Color", default="#000000")
    show_bank_detail = fields.Boolean("Show Bank Details", help="Enable this to show company back detail on invoice")
