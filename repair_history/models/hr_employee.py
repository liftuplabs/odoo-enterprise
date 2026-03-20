# models/hr_employee_document.py

from odoo import models, fields, api
from odoo.exceptions import AccessError, UserError, ValidationError

class EmployeeDocument(models.Model):
    _name = 'hr.employee.document'
    _description = 'Employee Documents'
    _order = 'create_date desc'

    name = fields.Char(string='Document Name', required=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    document_file = fields.Binary(string='Document File', required=True)
    file_name = fields.Char(string="File Name")

    @api.model
    def _check_access(self, operation):
        if not self.env.user.has_group('hr.group_hr_user'):
            # Only allow viewing own documents
            return [('employee_id.user_id', '=', self.env.uid)]
            print([('employee_id.user_id', '=', self.env.uid)],'ssjshsh')
        return []

    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        domain = self._check_access('read')  # <- pass operation
        return super().search(args + domain, offset=offset, limit=limit, order=order, count=count)


class HrEmployeeInherit(models.Model):
    _inherit = 'hr.employee'

    employee_document_ids = fields.One2many('hr.employee.document', 'employee_id', string="Documents")
    is_not_visible = fields.Boolean(string="Is Not Visible", compute="_compute_is_not_visible")


    def _compute_is_not_visible(self):
        for record in self:
            print(record.id, self.env.user.employee_id.id,'dekh lo vinod')
            if not self.env.user.has_group('hr.group_hr_user') and record.id != self.env.user.employee_id.id:
                record.is_not_visible = True
            else:
                record.is_not_visible = False


class ReturnDCWizard(models.TransientModel):
    _name = 'return.dc.wizard'
    _description = 'DC Number for Return Pickings'

    dc_number = fields.Char(string="DC Number", required=True)
    picking_ids = fields.Many2many('stock.picking', string="Selected Pickings")
    lot_ids = fields.Many2many('stock.lot', string="Lots")

    def action_search_pickings_by_lots(self):
        """Search all pickings that contain move lines with selected lots."""
        self.ensure_one()
        if not self.lot_ids:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'No Lots Selected',
                    'message': 'Please select at least one Lot/Serial Number.',
                    'type': 'warning',
                    'sticky': False,
                }
            }

        picking_ids = []
        for lot_id in self.lot_ids:
            pickings = self.env['stock.picking'].search([
                ('move_line_ids.lot_id', 'in', lot_id.ids), ('state', '=', 'done'), ('picking_type_code', '=', 'outgoing')
            ], order='date_done desc', limit=1)
            if not pickings:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'No Pickings Found',
                        'message': 'No pickings found for selected lots.',
                        'type': 'warning',
                        'sticky': False,
                    }
                }

            return_picking = self.env['stock.picking'].search([
                ('move_line_ids.lot_id', 'in', lot_id.ids), ('state', '=', 'done'), ('picking_type_code', '=', 'incoming')
            ], order='date_done desc', limit=1)

            if return_picking.date_done >= pickings.date_done:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Already Returned',
                        'message': f'The lot/serial number {lot_id.name} has already been returned.',
                        'type': 'warning',
                        'sticky': False,
                    }
                }
            picking_ids.append(pickings.id)



        self.picking_ids = [(6, 0, picking_ids)]

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'return.dc.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': self.env.context,
        }

    def action_create_single_return_for_lots(self):
        """Create a single return picking for all selected lots."""
        self.ensure_one()
        if not self.picking_ids:
            raise UserError("Please search and select pickings first.")
        if not self.lot_ids:
            raise UserError("Please select at least one lot.")

        # Use first picking as reference (to get partner, location, etc.)
        reference_picking = self.picking_ids[0]
        return_picking_vals = {
            'origin': f'Return for Lots ({self.dc_number or "N/A"})',
            'partner_id': reference_picking.partner_id.id,
            'picking_type_id': reference_picking.picking_type_id.return_picking_type_id.id,
            'location_id': reference_picking.location_dest_id.id,
            'location_dest_id': reference_picking.location_id.id,
            'dc_number': self.dc_number,
        }
        return_picking = self.env['stock.picking'].create(return_picking_vals)

        # Add return move lines based on selected lots
        move_lines_to_return = self.env['stock.move.line'].search([
            ('picking_id', 'in', self.picking_ids.ids),
            ('lot_id', 'in', self.lot_ids.ids),
        ])

        for line in move_lines_to_return:
            move = self.env['stock.move'].create({
                'name': line.move_id.name,
                'product_id': line.product_id.id,
                'product_uom_qty': line.quantity,
                'product_uom': line.product_uom_id.id,
                'picking_id': return_picking.id,
                'location_id': line.location_dest_id.id,
                'location_dest_id': line.location_id.id,
            })

            self.env['stock.move.line'].create({
                'move_id': move.id,
                'picking_id': return_picking.id,
                'product_id': line.product_id.id,
                'product_uom_id': line.product_uom_id.id,
                'quantity': line.quantity,
                'lot_id': line.lot_id.id,
                'location_id': line.location_dest_id.id,
                'location_dest_id': line.location_id.id,
            })

        # Open the newly created picking (so user can manually add lines)
        return {
            'name': 'Return Picking',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': return_picking.id,
            'target': 'current',
        }

    # def action_confirm_dc_return(self):
    #     for picking in self.picking_ids:
    #         print(picking,'pickingpickingpicking')
    #         picking.action_return_all_and_validate(dc_number=self.dc_number)

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        active_ids = self.env.context.get('picking_ids')
        if active_ids:
            res['picking_ids'] = [(6, 0, active_ids)]
        return res

