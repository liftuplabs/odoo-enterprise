from odoo import models, fields, api, _
from odoo.exceptions import UserError


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    is_external_subcontractor = fields.Boolean(
        related='bom_id.is_external_subcontractor',
        store=True
    )
    subcontractor_po_id = fields.Many2one(
        'purchase.order',
        string="Subcontractor PO",
        copy=False
    )
    subcontractor_receipt_done = fields.Boolean(
        string="Subcontractor Receipt Done",
        default=False,
        copy=False
    )

    def action_view_subcontractor_po(self):
        self.ensure_one()
        if self.subcontractor_po_id:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Subcontractor PO'),
                'res_model': 'purchase.order',
                'res_id': self.subcontractor_po_id.id,
                'view_mode': 'form',
                'target': 'current',
            }

    def action_create_subcontract_po(self):
        self.ensure_one()
        if not self.bom_id.external_subcontractor_id:
            raise UserError(_("Please set a subcontractor on the Bill of Materials."))

        # Create the Purchase Order
        po_vals = {
            'partner_id': self.bom_id.external_subcontractor_id.id,
            'mrp_production_id': self.id,
            'origin': self.name,
            'order_line': [(0, 0, {
                'product_id': self.product_id.id,
                'product_qty': self.product_qty,
                'product_uom': self.product_uom_id.id,
                'name': self.product_id.name,
                'price_unit': 0.0,  # You can update this manually on the PO
                'date_planned': fields.Datetime.now(),
            })]
        }
        po = self.env['purchase.order'].create(po_vals)
        self.subcontractor_po_id = po.id

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'res_id': po.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def button_mark_done(self):
        """ Backend validation to prevent producing before receipt is done """
        for mo in self:
            if mo.is_external_subcontractor and not mo.subcontractor_receipt_done:
                raise UserError(_("You cannot produce this order until the subcontractor receipt is completed."))
        return super(MrpProduction, self).button_mark_done()