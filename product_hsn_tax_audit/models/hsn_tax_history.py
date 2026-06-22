from odoo import models, fields, api

class ProductHsnTaxHistory(models.Model):
    _name = 'product.hsn.tax.history'
    _description = 'HSN and Tax History'
    _order = 'date desc, id desc'

    product_id = fields.Many2one('product.template', string='Product', ondelete='cascade', required=True)
    date = fields.Date(string='Date', required=True)
    hsn_code = fields.Char(string='HSN Code')
    sales_taxes_id = fields.Many2many('account.tax', 'hsn_sale_tax_rel', string='Sales Taxes')
    purchase_taxes_id = fields.Many2many('account.tax', 'hsn_purchase_tax_rel', string='Purchase Taxes')
    user_id = fields.Many2one('res.users', string='Updated By', default=lambda self: self.env.user)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec._sync_to_product()
        return records

    def write(self, vals):
        res = super().write(vals)
        # Check if we should sync (if any of these fields changed)
        if any(field in vals for field in ['hsn_code', 'sales_taxes_id', 'purchase_taxes_id', 'product_id']):
            for rec in self:
                rec._sync_to_product()
        return res

    def _sync_to_product(self):
        """Helper to push values to the product template"""
        self.ensure_one()
        # We only sync if this is the most recent (or latest dated) entry
        # to ensure the product always reflects the latest state.
        latest_history = self.env['product.hsn.tax.history'].search([
            ('product_id', '=', self.product_id.id)
        ], order='date desc, id desc', limit=1)

        if self == latest_history:
            self.product_id.write({
                'l10n_in_hsn_code': self.hsn_code,
                'taxes_id': [(6, 0, self.sales_taxes_id.ids)],
                'supplier_taxes_id': [(6, 0, self.purchase_taxes_id.ids)],
            })