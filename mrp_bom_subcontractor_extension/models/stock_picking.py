from odoo import models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _action_done(self):
        res = super(StockPicking, self)._action_done()

        for picking in self:
            if picking.purchase_id:
                # Check if this receipt is returning to our production location
                if picking.picking_type_code == 'incoming':

                    # Find ANY open MO tied to this Purchase Order
                    open_mos = self.env['mrp.production'].search([
                        ('subcontractor_po_id', '=', picking.purchase_id.id),
                        ('state', 'not in', ('done', 'cancel')),
                        ('production_location_id', '=', picking.location_dest_id.id)
                    ])

                    for mo in open_mos:
                        mo.subcontractor_receipt_done = True

        return res