from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    taxes_id = fields.Many2many(tracking=True)
    supplier_taxes_id = fields.Many2many(tracking=True)
    l10n_in_hsn_code = fields.Char(string="HSN Code", tracking=True)

    hsn_history_ids = fields.One2many('product.hsn.tax.history', 'product_id', string='HSN & Taxes History')

