from odoo import models, fields, api, _

class MrpSubcontractorWizard(models.TransientModel):
    _name = 'mrp.subcontractor.wizard'
    _description = 'Select Subcontractor Wizard'

    mrp_production_id = fields.Many2one('mrp.production', string="Manufacturing Order")
    subcontractor_id = fields.Many2one('res.partner', string="Subcontractor", required=True)
    product_qty = fields.Float('Quantity', required=True)

    @api.model
    def default_get(self, fields_list):
        res = super(MrpSubcontractorWizard, self).default_get(fields_list)
        if 'mrp_production_id' in res:
            mo = self.env['mrp.production'].browse(res['mrp_production_id'])
            # Calculate remaining qty
            ordered_qty = sum(mo.subcontractor_po_ids.filtered(lambda p: p.state not in ['cancel']).mapped('order_line.product_qty'))
            res['product_qty'] = max(0, mo.product_qty - ordered_qty) or mo.product_qty
        return res


    def action_confirm(self):
        self.ensure_one()
        if self.mrp_production_id and self.subcontractor_id:
            return self.mrp_production_id.action_create_subcontractor_po(self.subcontractor_id, self.product_qty)
