from odoo import api, Command, fields, models, modules, tools, _
from odoo.exceptions import UserError, ValidationError


class CustomerPendingProduct(models.Model):
    _name = 'customer.pending.product'
    _description = 'Pending Products from Original Quotation'

    partner_id = fields.Many2one('res.partner', string='Owner (Customer)', required=True, index=True)
    product_id = fields.Many2one('product.product', string='Product', required=True)
    product_uom_qty = fields.Float('Remaining Quantity', required=True)
    price_unit = fields.Float('Original Unit Price')
    original_order_id = fields.Many2one('sale.order', string='Original Quotation', readonly=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('added', 'Added to SO')
    ], string='Status', default='pending', copy=False)
    is_repair_parts = fields.Boolean('Is Repair Part', default=False)

    def action_add_to_so(self):
        """ Adds the pending product to the active Sale Order and marks it as added. """
        sale_order_id = self.env.context.get('parent_sale_order_id')

        if not sale_order_id:
            return

        sale_order = self.env['sale.order'].browse(sale_order_id)

        for record in self:
            if record.state == 'pending':

                # Look for an existing line with the same product AND the same repair flag
                existing_line = sale_order.order_line.filtered(
                    lambda
                        line: line.product_id.id == record.product_id.id and line.is_repair_parts == record.is_repair_parts
                )

                if existing_line:
                    # If it exists, just add the quantity to the first matching line
                    existing_line[0].product_uom_qty += record.product_uom_qty
                else:
                    # If it doesn't exist, create a new line
                    self.env['sale.order.line'].create({
                        'order_id': sale_order.id,
                        'product_id': record.product_id.id,
                        'product_uom_qty': record.product_uom_qty,
                        'price_unit': record.price_unit,
                        'is_repair_parts': record.is_repair_parts,
                    })

                record.state = 'added'

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }