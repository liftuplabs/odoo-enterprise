from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Related fields to res.company for persistent storage
    custom_invoice_title = fields.Char(related='company_id.custom_invoice_title', readonly=False)
    custom_invoice_font_family = fields.Selection(related='company_id.custom_invoice_font_family', readonly=False)
    custom_invoice_border_color = fields.Char(related='company_id.custom_invoice_border_color', readonly=False)
    custom_invoice_border_thickness = fields.Integer(related='company_id.custom_invoice_border_thickness', readonly=False)
    custom_invoice_header_bg_color = fields.Char(related='company_id.custom_invoice_header_bg_color', readonly=False)
    custom_invoice_header_text_color = fields.Char(related='company_id.custom_invoice_header_text_color', readonly=False)
    invoice_layout_boxed = fields.Boolean(related='company_id.invoice_layout_boxed', readonly=False)
