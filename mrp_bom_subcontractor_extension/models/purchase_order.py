from odoo import models, fields, api


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    mrp_production_id = fields.Many2one('mrp.production', string="Source MO")

    # 1. Override the compute method purely to add 'picking_ids' to the depends list
    # This ensures the field re-evaluates when our custom pickings are generated.
    @api.depends('order_line.move_ids', 'picking_ids')
    def _compute_subcontracting_resupply_picking_count(self):
        super()._compute_subcontracting_resupply_picking_count()

    def button_confirm(self):
        res = super(PurchaseOrder, self).button_confirm()

        for order in self:
            if order.mrp_production_id:
                mo = order.mrp_production_id

                # Setup Locations
                prod_location = mo.production_location_id
                dest_location = self.env['stock.location'].search([
                    ('name', 'ilike', 'Subcontracting Location'),
                    ('company_id', 'in', [order.company_id.id, False])
                ], limit=1)

                if not dest_location:
                    dest_location = order.partner_id.property_stock_supplier

                # Update automatically generated receipt
                for picking in order.picking_ids:
                    picking.location_dest_id = prod_location
                    for move in picking.move_ids:
                        move.location_dest_id = prod_location
                        for line in move.move_line_ids:
                            line.location_dest_id = prod_location

                # Find Resupply Operation Type
                picking_type_resupply = self.env['stock.picking.type'].search([
                    ('name', 'ilike', 'Resupply Subcontractor'),
                    ('company_id', '=', order.company_id.id)
                ], limit=1)

                if not picking_type_resupply:
                    picking_type_resupply = self.env['stock.picking.type'].search([
                        ('code', '=', 'internal'),
                        ('company_id', '=', order.company_id.id)
                    ], limit=1)

                # Create Custom Resupply Order
                receipt = order.picking_ids and order.picking_ids[0] or False

                if picking_type_resupply and receipt:
                    resupply_picking = self.env['stock.picking'].create({
                        'partner_id': order.partner_id.id,
                        'picking_type_id': picking_type_resupply.id,
                        'location_id': prod_location.id,
                        'location_dest_id': dest_location.id,
                        'origin': receipt.name,
                        'group_id': receipt.group_id.id,
                        'move_ids': [(0, 0, {
                            'name': f"Resupply: {mo.product_id.name}",
                            'product_id': mo.product_id.id,
                            'product_uom_qty': mo.product_qty,
                            'product_uom': mo.product_uom_id.id,
                            'location_id': prod_location.id,
                            'location_dest_id': dest_location.id,
                            'group_id': receipt.group_id.id,
                        })]
                    })
                    resupply_picking.action_confirm()

        # 2. Force Odoo to clear the cache for this specific field.
        # This guarantees the smart button updates immediately on the UI.
        self.invalidate_recordset(['subcontracting_resupply_picking_count'])
        return res

    # 3. Override standard retrieval to inject our custom pickings
    def _get_subcontracting_resupplies(self):
        # Fetch standard resupplies
        pickings = super()._get_subcontracting_resupplies()

        # Append our custom resupplies
        for order in self:
            if order.mrp_production_id and order.picking_ids:
                receipt_names = order.picking_ids.mapped('name')
                receipt_groups = order.picking_ids.mapped('group_id').ids

                if receipt_names and receipt_groups:
                    custom_resupplies = self.env['stock.picking'].search([
                        ('origin', 'in', receipt_names),
                        ('group_id', 'in', receipt_groups)
                    ])
                    # Merge custom pickings with standard ones
                    pickings |= custom_resupplies

        return pickings