from odoo import models, fields, api, _

class MrpSubcontractorWizard(models.TransientModel):
    _name = 'mrp.subcontractor.wizard'
    _description = 'Select Subcontractor Wizard'

    mrp_production_id = fields.Many2one('mrp.production', string="Manufacturing Order")
    subcontractor_id = fields.Many2one('res.partner', string="Subcontractor", required=True)

    def action_confirm(self):
        self.ensure_one()
        if self.mrp_production_id and self.subcontractor_id:
            return self.mrp_production_id.action_create_subcontractor_po(self.subcontractor_id)
