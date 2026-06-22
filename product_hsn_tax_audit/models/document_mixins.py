from odoo import models, api


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.onchange('product_id')
    def _onchange_product_id_history(self):
        if self.product_id and self.order_id.date_order:
            history = self.env['product.hsn.tax.history'].search([
                ('product_id', '=', self.product_id.product_tmpl_id.id),
                ('date', '<=', self.order_id.date_order.date())
            ], order='date desc', limit=1)

            if history:
                self.tax_id = [(6, 0, history.sales_taxes_id.ids)]


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.onchange('product_id')
    def _onchange_product_id_history(self):
        if self.product_id and self.move_id.invoice_date:
            history = self.env['product.hsn.tax.history'].search([
                ('product_id', '=', self.product_id.product_tmpl_id.id),
                ('date', '<=', self.move_id.invoice_date)
            ], order='date desc', limit=1)

            if history:
                if self.move_id.move_type in ['out_invoice', 'out_refund']:
                    self.tax_ids = [(6, 0, history.sales_taxes_id.ids)]
                elif self.move_id.move_type in ['in_invoice', 'in_refund']:
                    self.tax_ids = [(6, 0, history.purchase_taxes_id.ids)]