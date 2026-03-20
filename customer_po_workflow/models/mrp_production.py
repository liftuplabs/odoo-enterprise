from odoo import models, fields, api

class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    customer_po_id = fields.Many2one('customer.po', string='Customer PO')

    def _post_inventory(self, cancel_backorder=False):
        """Override to attach customer from Customer PO"""
        res = super()._post_inventory(cancel_backorder=cancel_backorder)

        for mo in self:
            # find linked Customer PO from origin

            if mo.customer_po_id and mo.customer_po_id.partner_id:
                # find related quants
                quants = self.env['stock.quant'].search([
                    ('lot_id', 'in', mo.move_finished_ids.mapped('lot_ids').ids),
                    ('inventory_quantity_auto_apply', '=', 1),
                    ('location_id.usage', '=', 'internal')
                ])
                if not quants:
                    # fallback: use location and product
                    quants = self.env['stock.quant'].search([
                        ('product_id', 'in', mo.move_finished_ids.mapped('product_id').ids),
                        ('location_id', '=', mo.location_dest_id.id)
                    ])

                # ✅ Update partner_id in all related quants
                quants.write({'partner_id': mo.customer_po_id.partner_id.id,
                              'customer_po': mo.customer_po_id.name})
        return res
