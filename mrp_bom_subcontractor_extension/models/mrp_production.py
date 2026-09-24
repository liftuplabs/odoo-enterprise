from odoo import models, fields, api, _
from odoo.exceptions import UserError


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    is_external_subcontractor = fields.Boolean(
        related='bom_id.is_external_subcontractor',
        store=True
    )
    subcontractor_po_ids = fields.Many2many(
        'purchase.order',
        'mrp_production_purchase_order_rel',
        'production_id', 'purchase_order_id',
        string="Subcontractor POs",
        copy=True
    )
    subcontractor_receipt_done = fields.Boolean(
        string="Subcontractor Receipt Done",
        default=False,
        copy=False
    )

    def action_view_subcontractor_po(self):
        self.ensure_one()
        if self.subcontractor_po_ids:
            action = {
                'type': 'ir.actions.act_window',
                'name': _('Subcontractor POs'),
                'res_model': 'purchase.order',
                'view_mode': 'list,form',
                'domain': [('id', 'in', self.subcontractor_po_ids.ids)],
                'target': 'current',
            }
            if len(self.subcontractor_po_ids) == 1:
                action['view_mode'] = 'form'
                action['res_id'] = self.subcontractor_po_ids[0].id
            return action

    def action_open_subcontractor_wizard(self):
        self.ensure_one()
        if not self.bom_id.external_subcontractor_id:
            raise UserError(_("Please set a subcontractor on the Bill of Materials."))
        
        return {
            'name': _('Select Subcontractor'),
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.subcontractor.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_mrp_production_id': self.id,
                'allowed_subcontractor_ids': self.bom_id.external_subcontractor_id.ids,
            }
        }

    def action_create_subcontractor_po(self, subcontractor_id, qty):
        self.ensure_one()
        if not subcontractor_id:
            raise UserError(_("Please select a subcontractor."))
        if qty <= 0:
            raise UserError(_("Quantity must be greater than zero."))

        # Create the Purchase Order
        po_vals = {
            'partner_id': subcontractor_id.id,
            'mrp_production_id': self.id,
            'origin': self.name,
            'order_line': [(0, 0, {
                'product_id': self.product_id.id,
                'product_qty': qty,
                'product_uom': self.product_uom_id.id,
                'name': self.product_id.name,
                'price_unit': 0.0,  # You can update this manually on the PO
                'date_planned': fields.Datetime.now(),
            })]
        }
        po = self.env['purchase.order'].create(po_vals)
        self.subcontractor_po_ids = [(4, po.id)]

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'res_id': po.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def button_mark_done(self):
        """ Calculate available received qty and trigger native backorder wizard """
        for mo in self:
            if mo.is_external_subcontractor and mo.subcontractor_po_ids:
                if not mo.subcontractor_receipt_done:
                    raise UserError(_("You cannot produce this order until the subcontractor receipt is completed."))

                # 1. Get total quantity received on the POs so far
                po_lines = mo.subcontractor_po_ids.mapped('order_line').filtered(lambda l: l.product_id == mo.product_id)
                total_received = sum(po_lines.mapped('qty_received'))

                # 2. Get total quantity already produced in past MOs (previous backorders) for these POs
                related_mos = self.env['mrp.production'].search([
                    ('subcontractor_po_ids', 'in', mo.subcontractor_po_ids.ids),
                    ('state', '=', 'done')
                ])
                already_produced = sum(related_mos.mapped('qty_produced'))

                available_to_produce = total_received - already_produced

                if available_to_produce <= 0:
                    raise UserError(
                        _("You have already produced all received quantities. Process the next subcontractor receipt first."))

                # 3. If they try to produce more than received (or if qty_producing is 0 which implies 'Produce All'), cap it.
                qty_intended = mo.qty_producing if mo.qty_producing > 0 else mo.product_qty

                if qty_intended > available_to_produce:
                    mo.qty_producing = available_to_produce
                    # Because we set qty_producing < product_qty, Odoo's super() call
                    # will automatically pop up the standard Backorder Wizard.

        return super(MrpProduction, self).button_mark_done()