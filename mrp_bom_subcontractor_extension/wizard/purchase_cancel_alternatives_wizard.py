from odoo import models, fields, api

class PurchaseCancelAlternativesWizard(models.TransientModel):
    _name = 'purchase.cancel.alternatives.wizard'
    _description = 'Confirm Cancel Alternative POs'

    purchase_order_id = fields.Many2one('purchase.order', string="Purchase Order")
    
    def action_confirm(self):
        self.ensure_one()
        # Call button_confirm with context to skip the check
        return self.purchase_order_id.with_context(skip_alternative_po_check=True).button_confirm()
