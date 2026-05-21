from odoo import api, fields, models
from odoo.exceptions import UserError


class MaterialRequisition(models.Model):
    _name = "material.requisition"
    _description = 'Material Requisition'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Requisition Reference", readonly=True, required=True, copy=False, index=True,
                       default='New')
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user.id, string="Requested By",
                              readonly=True)
    requested_on = fields.Datetime(string='Requested On', default=fields.Datetime.now(), readonly=True)
    request_line_ids = fields.One2many('material.request.line', 'requisition_id', string='Request Lines', copy=True,
                                       auto_join=True)
    state = fields.Selection(
        [('new', 'New'), ('confirmed', 'Confirmed'), ('approved', 'Approved'), ('done', 'Done'), ('refuse', 'Refuse'),
         ('resubmit', 'Resubmit'), ('cancelled', 'Cancelled'), ('on_hold', 'On Hold')],
        string='Status',
        required=True, copy=False, default='new', tracking=True)
    repair_id = fields.Many2one('repair.order', string="Repair", readonly=True)
    date_approve = fields.Datetime('Approval Date', readonly=1, index=True, copy=False)
    approved_by = fields.Many2one('res.users', string="Approved By",
                                           readonly=True)

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('material.requisition') or 'New'
        result = super(MaterialRequisition, self).create(vals)
        return result

    def action_confirm(self):
        if not self.request_line_ids:
            raise UserError("You are not allowed to authorize request with no Requests")
        else:
            self.write({'state': 'confirmed'})
            if self.repair_id:
                self.repair_id.write({'state': 'material_requested'})
        return True

    def action_on_hold(self):
        if self.repair_id.state not in ['draft', 'confirmed', 'cancel', 'material_requested', 'material_refused', 'material_approved']:
            raise UserError("You cannot put the request on hold as the repair order is already in progress.")

        self.write({'state': 'on_hold'})
        if self.repair_id:
            self.repair_id.write({'state': 'material_on_hold'})
        return True

    def action_refuse(self):
        if self.repair_id.state not in ['draft', 'confirmed', 'cancel', 'material_requested', 'material_refused', 'material_approved']:
            raise UserError("You cannot refuse the request as the repair order is already in progress.")

        self.write({'state': 'refuse'})
        if self.repair_id:
            self.repair_id.write({'state': 'material_refused'})
        return True

    def action_resubmit(self):
        self.write({'state': 'new'})
        if self.repair_id:
            self.repair_id.write({'state': 'material_requested'})
        return True

    def action_cancel(self):
        if self.repair_id.state not in ['draft', 'confirmed', 'cancel', 'material_requested', 'material_refused', 'material_approved']:
            raise UserError("You cannot cancel the request as the repair order is already in progress.")

        self.write({'state': 'cancelled'})
        if self.repair_id:
            self.repair_id.write({'state': 'material_cancelled'})
        return True

    def action_reset_to_draft(self):
        self.write({'state': 'new'})
        return True

    def action_approve(self):
        for lines in self.request_line_ids:
            if not lines.product_id:
                raise UserError("You can't authorize the request without Product")
            else:
                self.write({'state': 'approved', 'date_approve': fields.Datetime.now(),
                            'approved_by': self.env.user.id})
                if self.repair_id:
                    self.repair_id.write({'state': 'material_approved'})
                    if self.repair_id:
                        self.repair_id.write({'state': 'material_approved'})

                        # UPDATED: Loop through requisition lines and update the matching pre-existing stock moves
                        for line in self.request_line_ids:
                            # Find the existing move on the Repair Order for this specific product
                            matching_move = self.repair_id.move_ids.filtered(
                                lambda m: m.product_id == line.product_id and m.state not in ['done', 'cancel']
                            )

                            if matching_move:
                                # Take the first matched move block (if multiples exist), update quantity
                                move = matching_move[0]
                                move.write({'quantity': line.quantity})
                                line.write({'move_id': move.id})
                self.request_line_ids.write({'states': 'authorized'})
        return True

    def unlink(self):
       for requisition in self:
           if requisition.state in ['approved', 'done']:
               raise UserError("You cannot delete a requisition that has been approved or done.")
       if self.repair_id:
           self.repair_id.write({'state': 'confirmed'})
       return super(MaterialRequisition, self).unlink()


class MaterialRequestLine(models.Model):
    _name = "material.request.line"
    _description = 'Material Requisition'

    requisition_id = fields.Many2one('material.requisition', string="Requisition Name")
    product_id = fields.Many2one('product.product', string="Product Name")
    description = fields.Char(string="Description", required=True)
    quantity = fields.Integer(string="Quantity", default=1)
    unit_of_measure_id = fields.Many2one('uom.uom', string="Unit of Measure")
    states = fields.Selection(
        [('new', 'New'), ('authorized', 'Authorized'), ('ordered', 'Ordered'), ('done', 'Done'),
         ('cancel', 'Cancel')],
        required=True, default='new', copy=False, string="State"
    )
    move_id = fields.Many2one('stock.move', string="Linked Stock Move", ondelete='set null')

    @api.onchange('product_id')
    def onchange_product_id(self):
        self.description = self.product_id.name
        self.unit_of_measure_id = self.product_id.uom_po_id or self.product_id.uom_id

    @api.model_create_multi
    def create(self, vals_list):
        lines = super(MaterialRequestLine, self).create(vals_list)

        for line in lines:
            repair = line.requisition_id.repair_id

            if repair and not line.move_id:
                move = self.env['stock.move'].create({
                    'name': line.description or line.product_id.display_name,
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.quantity,
                    'product_uom': line.unit_of_measure_id.id or line.product_id.uom_id.id,
                    'repair_id': repair.id,
                    'repair_line_type': 'add',
                    'location_id': repair.location_id.id,
                    'location_dest_id': line.product_id.with_company(repair.company_id).property_stock_inventory.id,
                    'company_id': repair.company_id.id,
                })
                line.write({'move_id': move.id})

        return lines

    def unlink(self):
        """ Automatically remove the linked part from the Repair Order when line is deleted """
        for line in self:
            # We only delete the move if it hasn't been processed (done) or cancelled yet
            if line.move_id and line.move_id.state not in ['done', 'cancel']:
                line.move_id.sudo().unlink()
        return super(MaterialRequestLine, self).unlink()

    def write(self, vals):
        """ Update the Repair Order part if the quantity is changed on the requisition """
        res = super(MaterialRequestLine, self).write(vals)
        if 'quantity' in vals:
            for line in self:
                if line.move_id and line.move_id.state not in ['done', 'cancel']:
                    line.move_id.write({'product_uom_qty': line.quantity})
        return res