from odoo import models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _action_done(self):
        res = super(StockPicking, self)._action_done()

        for picking in self:
            # Check if this picking belongs to our custom Subcontractor PO
            if picking.purchase_id and picking.purchase_id.mrp_production_id:
                mo = picking.purchase_id.mrp_production_id

                # Check if this specific picking is the Receipt returning to SMT01/PROD
                if picking.location_dest_id == mo.production_location_id:
                    mo.subcontractor_receipt_done = True

        return res