import ast

from datetime import datetime
from email.policy import default

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.osv.expression import OR
from odoo.tools.float_utils import float_round
from odoo.tools import float_utils
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)

class Maintenace(models.Model):
    _inherit = 'maintenance.equipment'

class ProductionOrder(models.Model):
    _name = "production.order"
    _description = "Production Order"

    name = fields.Char('Reference', required=True, copy=False, readonly=True, default=lambda self: self.env['ir.sequence'].next_by_code('production.order'))
    date = fields.Datetime(
        'Date', default=fields.Datetime.now, required=True,
        help="The date when the production order was created.")
    machine_id = fields.Many2many('maintenance.equipment', string='Machine')
    shift_no = fields.Selection(string='Shift No', selection=[('shift_1', 'Shift 1'), ('shift_2', 'Shift 2'), ('shift_3', 'Shift 3')], required=True)
    mrp_ids = fields.One2many('mrp.production', 'production_order_id', string='Manufacturing Orders', help="Manufacturing orders associated with this production order.")
    state = fields.Selection([('draft', 'Draft'), ('in_progress', 'In Progress'), ('done', 'Done'), ('cancel', 'Cancelled')], string='Status', default='draft', required=True, help="The current status of the production order.")

    def action_confirm(self):
        self.state = 'in_progress'
    def action_done(self):
        self.state = 'done'
    def action_cancel(self):
        self.state = 'cancel'
    def action_draft(self):
        self.state = 'draft'

class MrpProduction(models.Model):
    """ Manufacturing Orders """
    _inherit = 'mrp.production'

    production_order_id = fields.Many2one('production.order', string='Production Order', help="The production order associated with this manufacturing order.")
    machine_id = fields.Many2one('maintenance.equipment', string='Machine', help="The machine used for this manufacturing order.")

    @api.onchange('machine_id')
    def _onchange_machine_id(self):
        if self.machine_id and self.production_order_id:
            existing_machines = self.production_order_id.machine_id.ids or []
            if self.machine_id.id not in existing_machines:
                self.production_order_id.machine_id = [(4, self.machine_id.id)]


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    downtime_duration_seconds = fields.Integer(
        string='Downtime Duration (Seconds)',
        help='Total downtime duration in seconds for this work order.',
        default=0,
    )
    downtime_duration_display = fields.Char(
        string='Downtime Duration',
        compute='_compute_downtime_duration_display',
        help='Formatted downtime duration in MM:SS format.',
    )
    downtime_start_time = fields.Datetime(
        string='Downtime Start Time',
        help='Timestamp when the workorder was last paused for downtime tracking.',
    )
    operator = fields.Many2one('hr.employee', string='Operator', help="The operator assigned to this work order.")
    reason_id = fields.Many2many('downtime.reasons', string='Downtime Reason')
    efficiency = fields.Float(string='Efficiency %', compute='_compute_efficiency', help="Efficiency of the work order based on production and downtime.")
    downtime_include = fields.Boolean(string='Include Downtime in Efficiency', default=False, help="If checked, downtime will be included in the efficiency calculation.")

    def _compute_efficiency(self):
        """Compute the efficiency of the work order based on production and downtime."""
        for workorder in self:
            if workorder.duration_expected > 0:
                if workorder.downtime_include:
                    # Include downtime in efficiency calculation
                    total_duration = workorder.duration + workorder.downtime_duration_seconds / 60  # Convert seconds to minutes
                    workorder.efficiency = (workorder.duration_expected / total_duration) * 100 if total_duration > 0 else 0.0
                else:
                    total_duration = workorder.duration
                    workorder.efficiency = (workorder.duration_expected / total_duration) * 100 if total_duration > 0 else 0.0
            else:
                workorder.efficiency = 0.0

    @api.onchange('downtime_include')
    def _onchange_downtime_include(self):
        self._compute_efficiency()


    @api.depends('downtime_duration_seconds')
    def _compute_downtime_duration_display(self):
        """Compute the formatted downtime duration in MM:SS format."""
        for workorder in self:
            total_seconds = workorder.downtime_duration_seconds
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            workorder.downtime_duration_display = f"{minutes:02d}:{seconds:02d}"

    def button_pending(self):
        """Start downtime timer when pausing the workorder."""
        for workorder in self:
            if workorder.state not in ('pending', 'done', 'cancel'):
                _logger.info("Pausing workorder %s, starting downtime timer", workorder.name)
                workorder.downtime_start_time = fields.Datetime.now()
            else:
                _logger.warning("Workorder %s is already in state %s, skipping downtime timer start", workorder.name,
                                workorder.state)
        return super(MrpWorkorder, self).button_pending()

    def button_start(self, raise_on_invalid_state=False):
        """Stop downtime timer and update downtime duration when resuming the workorder."""
        for workorder in self:
            if workorder.downtime_start_time:
                pause_end = fields.Datetime.now()
                downtime_seconds = (pause_end - workorder.downtime_start_time).total_seconds()
                if downtime_seconds >= 0:
                    workorder.downtime_duration_seconds += int(float_round(downtime_seconds, precision_digits=0))
                    _logger.info("Resuming workorder %s, downtime recorded: %s seconds (%s)",
                                 workorder.name, workorder.downtime_duration_seconds,
                                 workorder.downtime_duration_display)
                else:
                    _logger.warning("Negative downtime detected for workorder %s, skipping update", workorder.name)
                workorder.downtime_start_time = False
            else:
                _logger.info("Resuming workorder %s, no active downtime timer found", workorder.name)
        return super(MrpWorkorder, self).button_start(raise_on_invalid_state=raise_on_invalid_state)

    def action_add_downtime_reason(self):
        """Open a wizard to add or edit downtime reasons."""
        self.ensure_one()
        return {
            'name': 'Add Downtime Reason',
            'type': 'ir.actions.act_window',
            'res_model': 'downtime.reasons.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_workorder_id': self.id,
                'default_reason_ids': self.reason_id.ids,
            },
        }

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    dc_date = fields.Date(string='DC Date', help="Delivery Challan date for this stock picking.")

class StockMove(models.Model):
    _inherit = 'stock.move'

    rejected = fields.Float(string='Rejected', help="The quantity of items rejected during the stock move.")
    reason_rejection = fields.Char(string='Reason for Rejection', help="The reason for rejecting the items in this stock move.")
    required_time = fields.Float(string='Required Time', help="The time required for this stock move in minutes.")