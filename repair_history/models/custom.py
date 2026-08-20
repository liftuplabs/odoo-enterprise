# from django.utils.duration import duration_string
# from pkg_resources import require
from odoo import api, Command, fields, models, modules, tools, _
from datetime import datetime, timedelta
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from collections import defaultdict
import json
from odoo.tools import float_compare, format_datetime, float_is_zero, float_round
from odoo.exceptions import UserError, ValidationError
import qrcode, base64
from io import BytesIO
from odoo.tools.misc import clean_context, OrderedSet, groupby



class SaleOrder(models.Model):
    _inherit = "sale.order"

    repair_ids = fields.One2many('repair.order', 'sale_order_id', string="Repairs")


class StockMove(models.Model):
    _inherit = 'stock.move'

    scan_data = fields.Text(string="Scan Data")
    customer_product_id = fields.Many2one('product.product', 'Product (Customer)', readonly=True)
    actual_product_id = fields.Many2one('product.product', 'Product (Actual)', readonly=True)
    is_auto_added_service_part = fields.Boolean(
        string="Auto-added Service Part",
        default=False
    )
    # product_id = fields.Many2one(
    #     'product.product', 'Product',
    #     check_company=True,
    #     domain="[('type', '=', 'consu')]", index=True, required=False)


    @api.onchange('customer_product_id')
    def _onchange_customer_product_id(self):
        for move in self:
            if move.actual_product_id:
                move.product_id = move.actual_product_id
            else:
                move.product_id = move.customer_product_id

    @api.onchange('actual_product_id')
    def _onchange_actual_product_id(self):
        for move in self:
            move.product_id = move.actual_product_id


    @api.onchange('product_id')
    def _onchange_product_id_update_lines(self):
        """
        When the product is changed on the move,
        update all existing move lines to match the new product.
        """
        for move in self:
            if move.state not in ['done', 'cancel'] and move.move_line_ids:
                # Update product_id on all existing lines
                move.move_line_ids.write({'product_id': move.product_id.id})

                # Optional: If the UOM changes with the product, update that too
                if move.product_id.uom_id:
                    move.move_line_ids.write({'product_uom_id': move.product_id.uom_id.id})

    def write(self, vals):
        # If product_id is changed via a standard write call (not just UI onchange)
        old_products = {}
        if 'product_id' in vals:
            for move in self:
                old_products[move.id] = move.product_id.name or _('None')

        res = super(StockMove, self).write(vals)
        if 'product_id' in vals:
            for move in self:
                if move.move_line_ids:
                    move.move_line_ids.write({'product_id': vals['product_id']})

        if 'product_id' in vals:
            for move in self:
                if move.picking_id:
                    # Get the new product name from the updated record
                    new_product_name = move.product_id.name or _('None')
                    old_product_name = old_products.get(move.id, _('None'))

                    # Only log if the product actually changed
                    if old_product_name != new_product_name:
                        move.picking_id.message_post(
                            body=_("Product updated from %s to %s") % (old_product_name, new_product_name)
                        )
        return res

    @api.constrains('lot_ids','product_uom_qty')
    def _check_in_validation(self):
        for rec in self:
            if rec.product_uom_qty and rec.lot_ids:
                if rec.product_uom_qty != len(rec.lot_ids.ids):
                    raise ValidationError(
                        f"Product '{rec.product_id.name}' has quantity {rec.product_uom_qty} "
                        f"but {len(rec.lot_ids.ids)} lot(s) selected.\n"
                        "Each quantity should have one corresponding lot/serial number."
                    )



    warranty_days = fields.Integer(string="Warranty Duration (Days)")
    warranty_validity = fields.Date(string="Warranty Validity Up To", readonly=1)
    warranty_validity_check = fields.Date(string="Warranty Validity Up To", readonly=1)
    tag_ids = fields.Many2many('repair.tags', string="Tags")

    def _create_repair_sale_order_line(self):
        if not self:
            return
        so_line_vals = []

        self.env['sale.order.line'].create(so_line_vals)
        for move in self:
            if move.sale_line_id or move.repair_line_type != 'add' or not move.repair_id.sale_order_id:
                continue
            product_qty = move.product_uom_qty if move.repair_id.state != 'done' else move.quantity
            so_line_vals.append({
                'order_id': move.repair_id.sale_order_id.id,
                'product_id': move.product_id.id,
                'product_uom_qty': product_qty,
                # When relying only on so_line compute method, the sol quantity is only updated on next sol creation
                'product_uom': move.product_uom.id,
                'move_ids': [Command.link(move.id)],
                'qty_delivered': move.quantity if move.state == 'done' else 0.0,
            })

            if not move.repair_id.start_date:
                raise UserError("Please set the **Start Date** before performing action.")

            if move.warranty_validity_check and move.warranty_validity_check > move.repair_id.start_date:
                so_line_vals[-1]['price_unit'] = 0.0
            elif move.price_unit:
                so_line_vals[-1]['price_unit'] = move.price_unit
        new_line = self.env['sale.order.line'].create(so_line_vals)
        past_repairs = self.env['repair.order'].search([
            ('partner_id', '=', self.repair_id.partner_id.id),
            ('product_id', '=', self.repair_id.product_id.id),
            ('lot_id', '=', self.repair_id.lot_id.id),
            ('id', '!=', self.repair_id.id),
            ('state', 'in', ['done', 'delivered']),
        ], order='end_date desc', limit=1)

        if past_repairs and move.repair_id.under_warranty is True:
            service_lines = self.env['sale.order.line'].search([
                ('order_id', '=', past_repairs.sale_order_id.id),
                ('product_id.type', '=', 'service'),
            ])
            for line in service_lines:
                so_line_vals = {
                    'order_id': move.repair_id.sale_order_id.id,  # Add to current sale order
                    'product_id': line.product_id.id,
                    'product_uom_qty': line.product_uom_qty,
                    'product_uom': line.product_uom.id,
                    'price_unit': 0,
                    'name': line.name,
                    'tax_id': [(6, 0, line.tax_id.ids)],
                }
                new_line = self.env['sale.order.line'].create(so_line_vals)

    @api.constrains('product_uom_qty', 'quantity', 'state', 'product_id', 'repair_id')
    def _check_repair_qty_limits(self):
        for move in self:
            # Only trigger this constraint if the stock move is part of a Repair Order
            if move.repair_id and move.product_id:
                min_qty = move.product_id.repair_min_qty
                max_qty = move.product_id.repair_max_qty

                # 1. Check Planned Quantity (Demand) when the user adds the product
                planned_qty = move.product_uom_qty
                if max_qty > 0 and planned_qty > max_qty:
                    raise ValidationError(
                        f"The planned quantity for {move.product_id.display_name} ({planned_qty}) cannot exceed the maximum limit of {max_qty}."
                    )
                if min_qty > 0 and planned_qty < min_qty:
                    raise ValidationError(
                        f"The planned quantity for {move.product_id.display_name} ({planned_qty}) cannot be less than the minimum limit of {min_qty}."
                    )

                # 2. Check Consumed Quantity (Done) when the repair order is validated/finished
                if move.state == 'done':
                    consumed_qty = move.quantity
                    if max_qty > 0 and consumed_qty > max_qty:
                        raise ValidationError(
                            f"The consumed quantity for {move.product_id.display_name} ({consumed_qty}) cannot exceed the maximum limit of {max_qty}."
                        )
                    if min_qty > 0 and consumed_qty < min_qty:
                        raise ValidationError(
                            f"The consumed quantity for {move.product_id.display_name} ({consumed_qty}) cannot be less than the minimum limit of {min_qty}."
                        )

class RepairOrderInherit(models.Model):
    _inherit = 'repair.order'
    _description = 'Work Orders'


    can_edit_parts = fields.Boolean(string="Can Edit Parts", compute='_compute_can_edit_parts', default=True,)

    move_product_ids = fields.Many2many(
        'product.product',
        compute='_compute_move_products',
        string='Parts Products',
        store=True,
        tracking=True,
    )
    sale_order_date = fields.Datetime(
        string="Sale Date",
        related='sale_order_id.date_order',
        store=True
    )
    delivery_date = fields.Datetime(
        string="Delivery Date",
        compute='_compute_delivery_date',
        store=True,
        tracking=True
    )

    @api.depends('sale_order_id.picking_ids.state', 'sale_order_id.picking_ids.date_done')
    def _compute_delivery_date(self):
        for record in self:
            delivery_date = False
            if record.sale_order_id and record.sale_order_id.picking_ids:
                # Find all 'done' outgoing deliveries linked to the Sales Order
                done_deliveries = record.sale_order_id.picking_ids.filtered(
                    lambda p: p.picking_type_code == 'outgoing' and p.state == 'done' and p.date_done
                )
                if done_deliveries:
                    # If there are multiple deliveries, get the most recent one
                    delivery_date = max(done_deliveries.mapped('date_done'))

            record.delivery_date = delivery_date

    @api.constrains('name')
    def _check_duplicate_name(self):
        for rec in self:
            if rec.name:
                existing = self.env['repair.order'].search([('name', '=', rec.name), ('id', '!=', rec.id)], limit=1)
                if existing:
                    raise ValidationError(f"The name '{rec.name}' is already used by another repair order. Please choose a unique name.")

    @api.depends('move_ids.product_id')
    def _compute_move_products(self):
        for rec in self:
            rec.move_product_ids = rec.move_ids.mapped('product_id')


    def _compute_can_edit_parts(self):
        for rec in self:
            rec.can_edit_parts = self.env.user.has_group('repair_history.group_edit_repair_stock_moves')

    dc_number = fields.Char(string="DC Number")
    check_list_ids = fields.One2many(
        'check.list', "Check_list_id", copy=True)
    related_repair_ids = fields.Many2many(
        'repair.order',
        'repair_order_related_repair_rel',  # ← M2M relation table name
        'repair_id',  # ← current record column
        'related_repair_id',  # ← linked record column
        string="Related Repairs",
        domain="[('partner_id', '=', partner_id)]"
    )

    @api.onchange('product_id', 'account_en')
    def _onchange_product_id(self):
        # Only execute if account_en is 'cost'
        if self.account_en != 'cost':
            return

        new_service_products = self.env['product.product']
        if self.product_id and self.product_id.product_tmpl_id.service_product_ids:
            new_service_products = self.product_id.product_tmpl_id.service_product_ids

        ui_lines_to_remove = self.move_ids.filtered(
            lambda m: m.is_auto_added_service_part or (m.product_id and m.product_id.id in new_service_products.ids)
        )
        if ui_lines_to_remove:
            self.move_ids -= ui_lines_to_remove

        existing_product_ids = [m.product_id.id for m in self.move_ids if m.product_id]

        new_moves = self.env['stock.move']

        for sp in new_service_products:
            if sp.id in existing_product_ids:
                continue

            move_vals = {
                'name': sp.display_name,
                'product_id': sp.id,
                'product_uom_qty': 1.0,
                'product_uom': sp.uom_id.id,
                'repair_id': self._origin.id if self._origin else False,
                'repair_line_type': 'add',
                'location_id': self.location_id.id,
                'location_dest_id': sp.with_company(self.company_id).property_stock_inventory.id,
                'company_id': self.company_id.id,
                'is_auto_added_service_part': True,  # Custom field set to True
            }

            new_moves += self.env['stock.move'].new(move_vals)
            existing_product_ids.append(sp.id)

        if new_moves:
            self.move_ids += new_moves

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        questions = self.env['check.list.question'].search([])
        checklist_lines = []

        for question in questions:
            if question.name:
                checklist_lines.append((0, 0, {
                    'question_id': question.id,
                    'is_check': False,
                }))

        res['check_list_ids'] = checklist_lines
        return res

    @api.onchange('failure_date')
    def _on_change_of_falure_date(self):
        if self.failure_date:
            failure_date = self.failure_date or fields.Date.today()
            today = fields.Date.today()
            failure_date_dt = datetime.strptime(str(failure_date), "%Y-%m-%d")
            today_dt = datetime.strptime(str(today), "%Y-%m-%d")
            days_difference = (today_dt - failure_date_dt).days
            self.failure_days = days_difference

    @api.onchange('lot_id')
    def _on_change_of_lot(self):
        if self.lot_id:
            past_repairs = self.env['repair.order'].search([
                ('partner_id', '=', self.partner_id.id),
                ('product_id', '=', self.product_id.id),
                ('lot_id', '=', self.lot_id.id),
                ('id', '!=', self.id),
                ('state', 'in', ['done', 'delivered']),
            ], order='end_date desc', limit=1)
            print(past_repairs,'past_repairspast_repairs')

            existing_quant = self.env['stock.quant'].search([
                ('lot_id', '=', self.lot_id.id),
                ('quantity', '=', 1),
                ('location_id.usage', '=', 'internal')  # Optional: to filter stock in warehouse
            ], limit=1)

            self.old_part_ids = [(5, 0, 0)]
            if past_repairs:
                if past_repairs.warranty_validity:
                    self.warranty_validity = past_repairs.warranty_validity

                # ✅ Clear old records first
                self.old_part_ids = [(5, 0, 0)]

                # ✅ Add new records from move_ids
                vals = []
                for move in past_repairs.move_ids:
                    vals.append((0, 0, {
                        'product_id': move.product_id.id,
                        'warranty_validity': past_repairs.warranty_validity,
                        'tag_ids': [(6, 0, past_repairs.tag_ids.ids)],
                        'fi_part_old': move.product_id.display_name,
                    }))
                self.old_part_ids = vals

            if past_repairs and past_repairs.end_date:
                self.last_repair_date = past_repairs.end_date
            if existing_quant and existing_quant.partner_id:
                self.partner_id = existing_quant.partner_id.id
            if existing_quant and existing_quant.plant:
                self.plant = existing_quant.plant
            # if existing_quant and existing_quant.customer_po:
            #     self.customer_po = existing_quant.customer_po
            if existing_quant and existing_quant.inward_date:
                self.inward_date = existing_quant.inward_date
            if existing_quant and existing_quant.dc_number:
                self.dc_number = existing_quant.dc_number
            if existing_quant and existing_quant.customer_state:
                self.customer_state = existing_quant.customer_state


    account_en = fields.Selection([
        ('open', '____ OPEN ___'),
        ('in_warranty', 'In Warranty'),
        ('goodwill', 'Goodwill'),
        ('cost', 'Cost'),
        ('fix_price', 'Fix Price'),
        ('production_warranty', 'Production Warranty'),
        ('service_warranty', 'Service Warranty'),
        ('inspection_cost', 'Inspection Cost'),
        ('material_cost', 'Material Cost'),
        ('scrap', 'Scrap'),
    ], string="Account EN")

    customer_state = fields.Selection([
        ('MH', 'Maharashtra'),
        ('GJ-BJ', 'Gujarat - Bhuj'),
        ('RJ', 'Rajasthan'),
        ('MP', 'Madhya Pradesh'),
        ('AP', 'Andhra Pradesh'),
        ('KN', 'Karnataka'),
        ('TN', 'Tamilnadu'),
        ('GJ-JM', 'Gujarat - Jamnagar'),
    ], string="Customer State")

    plant_selection = [
        ('A001', 'A001'),
        ('A101', 'A101'),
        ('A201', 'A201'),
        ('A403', 'A403'),
        ('A605', 'A605'),
        ('A607', 'A607'),
        ('A609', 'A609'),
        ('A611', 'A611'),
        ('A615', 'A615'),
        ('A617', 'A617'),
        ('A620', 'A620'),
        ('A621', 'A621'),
        ('A707', 'A707'),
        ('A709', 'A709'),
        ('A712', 'A712'),
        ('C301', 'C301'),
        ('R202', 'R202'),
        ('R302', 'R302'),
        ('R502', 'R502'),
        ('R607', 'R607'),
        ('R705', 'R705'),
    ]

    plant = fields.Selection(
        selection=plant_selection,
        string="Plant",
    )

    failure_category_main_info = fields.Selection([
        ('nothing_found', 'Nothing found'),
        ('24v_spikes', '24 Volt Spikes'),
        ('foreign_materials', 'Foreign materials'),
        ('water_condensation', 'Water/condensation'),
        ('defective_components', 'Defective components'),
        ('handling', 'Handling'),
        ('other', 'Other'),
    ], string="Failure Category Main Info")

    failure_sub_info = fields.Selection([
        ('unknown', 'Unknown'),
        ('no_error', 'No error'),
        ('igbt_damaged', 'IGBT damaged'),
        ('rectifier_damage', 'Rectifier damage'),
        ('damaged_brake_transistors', 'Damaged brake transistors'),
        ('external_power_supply', 'External power supply'),
        ('port_cooling_fan', 'Port cooling fan'),
        ('comm_232', '232 communication interface'),
        ('comm_can', 'CAN communication interface'),
        ('comm_interbus', 'INTERBUS communication interface'),
        ('internal_power_supply', 'Internal power supply'),
        ('comm_tcp_ip', 'TCP/IP communication interface'),
        ('comm_profibus', 'PROFUBUS communication interface'),
        ('comm_ethercat', 'EtherCAT communication interface'),
        ('expansion_port_failure', 'Expansion port failure'),
        ('io_port_circuits', 'I/O port (control part) input and output circuits'),
        ('resolver_circuit', 'Resolver encoder interface circuits'),
        ('incremental_encoder_circuit', 'Incremental encoder interface circuit'),
        ('sek_encoder_circuit', 'SEK encoder interface circuits'),
        ('endat_encoder_circuit', 'Endat encoder interface circuits'),
        ('pulse_io', 'The main circuit from the pulse input and output p'),
        ('power_io', 'Power part of the input and output circuits'),
        ('cpu_circuit', 'CPU processing circuit'),
        ('switch_power_circuit', 'Switch power circuit'),
        ('dc_link_measure', 'DC-Link measure'),
        ('current_measure', 'Current- measure'),
        ('unit_temp_measure', 'unit Temp- measure'),
        ('motor_temp_measure', 'motor Temp- measure'),
        ('brake_resistor', 'Brake resistor'),
        ('igbt_drive_circuit', 'IGBT drive circuit'),
        ('rectifier_drive_circuit', 'Rectifier drive circuit'),
        ('heatsink_temp', 'Heat sink temp'),
        ('motor_brake_ctrl', 'Motor Brake control circuit'),
        ('model_confirmation', 'Model confirmation does not do'),
        ('wrong_param', 'Wrong parameter'),
        ('wrong_software', 'Wrong software'),
        ('label_damage', 'Damage or loss of terminal labeling'),
        ('reset_button_damage', 'damage RESET-button'),
        ('dip_switch_damage', 'DIP DIP switch is damaged or wrong'),
        ('cpu', 'CPU'),
        ('dc_filter_capacitor', 'Part of the DC filter capacitor damage'),
        ('cable_connection', 'Flat wire or cable connection is not good'),
        ('memory_chips', 'Memory chips'),
        ('plug_or_pins_damage', 'Damaged Plug or Pins'),
        ('fan_damage', 'Damaged fan'),
        ('switching_transformer', 'Switching Transformer'),
        ('charging_resistor', 'Charging resistor damaged'),
        ('output_relay', 'Output relay damaged'),
        ('inductance', 'Inductance damaged'),
        ('filter_damaged', 'Filter damaged'),
        ('bad_hall_element', 'Bad Hall element'),
        ('varistor_damage', 'varistor damage'),
        ('optical_coupler_damage', 'Optical coupler damaged'),
        ('pressure_resistance', 'Pressure resistance of damage'),
        ('input_stage', 'input stage'),
        ('output_stage', 'output stage'),
        ('no_display', 'No display'),
        ('led_lcd_error', 'LED/LCD display error'),
        ('hw_upgrade', 'Hardware upgrades or modifications'),
        ('mechanical_damage', 'Mechanical damage (skin deformation)'),
        ('screw_loss', 'Screw loss or slip teeth'),
        ('encoder_not_working', 'Encoder can not use'),
        ('batt_charger_comm_fail', 'Battery charger communication fail'),
        ('brake_not_working', 'Brake can not be used'),
        ('batt_retrofit', 'Battery charger Retrofit_Batt. Volt.measuring'),
        ('pm_iid_fuse_f1', 'PMIID_control_Fuse F1 fauty'),
        ('pmii_card_r252', 'PM II+ conrol card_resistor R252'),
        ('lt_board_pmii', 'LT-board_PM II'),
        ('moduladapter_pmi', 'Moduladapter_PM I'),
        ('can_address_switch', 'CAN-Address switch damage'),
        ('reloader_pmii', 'Reloader for PM II+'),
        ('reloader_fuse_f2', 'Reloader_Fuse F2 for PM II+'),
        ('reloader_fuse_f3', 'Reloader_Fuse F3 for PM II+'),
        ('reloader_shunt', 'Reloader_Shunt damage for PM II+'),
        ('reloader_batt_volt', 'Reloader_Batt. Voltage Measuring  for PM II+'),
        ('reloader_accu_temp', 'Reloader Accumulator Temp'),
        ('reloader_24v_fail', 'Reloader 24 Volt Output Failure'),
        ('pmii_fuse_f6', 'PM II+ conrol card Fuse F6'),
    ], string="Failure sub info")

    @api.model_create_multi
    def create(self, vals_list):
        records = super(RepairOrderInherit, self).create(vals_list)
        for record in records:
            record._sync_related_repairs()
        return records

    def write(self, vals):
        res = super(RepairOrderInherit, self).write(vals)
        if 'related_repair_ids' in vals and not self.env.context.get('no_recursive_sync'):
            for record in self:
                record._sync_related_repairs()
        return res

    def _sync_related_repairs(self):
        for rec in self:
            # Set of all related orders including self
            all_records = rec.related_repair_ids | rec

            # Loop through each related record
            for other in rec.related_repair_ids:
                # New set: all records except current `other`
                others_to_link = all_records - other
                # Sync other's related_repair_ids without triggering recursion
                other.with_context(no_recursive_sync=True).write({
                    'related_repair_ids': [(6, 0, others_to_link.ids)]
                })

    start_date = fields.Date("Start Date", default=fields.Date.today)
    inward_date = fields.Date("Inward Date", default=fields.Date.today)
    delivery_id = fields.Many2one("stock.picking", "Stock Transfer", compute='get_delivery_id')
    return_date = fields.Date("Return Date")
    quotation_day = fields.Date("Quotation Day")
    recommended_notes = fields.Html(string="Recommended Notes")
    end_date = fields.Date("End Date", readonly=1)  # no start and end = always active
    failure_date = fields.Date("Failure_Date", readonly=0)  # no start and end = always active
    open_by_customer = fields.Boolean("Open By customer?")
    tested_with_motot = fields.Boolean("Tested With Motor?")
    tested_digital = fields.Boolean("Tested Digital I/O's")
    unit_converted = fields.Boolean("Unit Converted?")
    fulltime_test_2hr = fields.Boolean("Full Time Test 2Hr?")
    unit_cleaned = fields.Boolean("Unit Cleaned?")
    interbus_check = fields.Boolean("Can Bus;Interbus Check")
    resolver_check = fields.Boolean("SSI\Resolver Check?")
    parameter = fields.Boolean("Basic Parameter Installed?")
    internal_psu = fields.Boolean("Internal PSU_24VDC?")
    state = fields.Selection([
        ('draft', 'New'),
        ('confirmed', 'Confirmed'),
        ('material_requested', 'Material Requested'),
        ('material_approved', 'Material Approved'),
        ('material_refused', 'Material Refused'),
        ('material_on_hold', 'Material On Hold'),
        ('material_cancelled', 'Material Cancelled'),
        ('under_repair', 'Under Repair'),
        ('done', 'Repaired'),
        ('delivered', 'Delivered'),
        ('cancel', 'Scrap')], string='Status',
        copy=False, default='draft', readonly=True, tracking=True, index=True,
        help="* The \'New\' status is used when a user is encoding a new and unconfirmed repair order.\n"
             "* The \'Confirmed\' status is used when a user confirms the repair order.\n"
             "* The \'Under Repair\' status is used when the repair is ongoing.\n"
             "* The \'Repaired\' status is set when repairing is completed.\n"
             "* The \'Scarp\' status is used when user scrap repair order.")
    requisition_count = fields.Integer(string='Requisition Count', compute='_compute_requisition_count')

    def get_delivery_id(self):
        for rec in self:
            delivery = self.env['stock.picking'].search([('origin', '=', rec.name)], limit=1)
            if delivery:
                rec.delivery_id = delivery  # You can assign the record directly
            else:
                rec.delivery_id =  False

    def open_repair_confirmation_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Confirm Repair',
            'res_model': 'repair.confirmation.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_repair_id': self.id,
            },
        }

    @api.onchange('warranty_days', 'end_date')
    def _onchange_warranty_up_to(self):
        if self.end_date and self.move_ids:
            for rec in self.move_ids:
                if rec.warranty_days:
                    rec.warranty_validity = self.end_date + timedelta(days=rec.warranty_days)

    duration = fields.Float(string="Real Duration", compute='_compute_efficiency', store=True)
    warranty_days = fields.Integer(string="Warranty Duration (Days)")
    failure_days = fields.Integer(string="Failure Days (Days)")
    sw_on_label = fields.Char(string='Sw_On_Label')
    unit_status = fields.Char(string='Unit Status', invisible='1')
    unit_status_us = fields.Selection([
        ('looks_new', 'Looks new'),
        ('little_wear', 'Little wear'),
        ('intense_usage', 'Intensely traces of usage'),
        ('not_usable', 'Not usable'),
    ], string="Unit Status")

    unit = fields.Char(string='Unit')
    rep_india = fields.Char(string='REP INDIA')
    sn_unit = fields.Char(string='SN-Unit')
    module = fields.Char(string='Modul')
    shipment_carrier = fields.Char(string='Shipment Carrier')

    incoming_software = fields.Char(string='Incoming Software')
    incoming_software_label = fields.Selection([
        ('v003_10_01', 'V003.10-01'),
        ('v260_70_01', 'V260.70-01'),
        ('v260_95_01', 'V260.95-01'),
        ('2813_2f6', '2813_2F6'),
        ('2813_2f9', '2813_2F9'),
        ('2925_263', '2925_263'),
        ('2xxx_2fa', '2xxx_2FA'),
        ('190_2100_001', '190 2100-001'),
        ('190_210_100_1', '190 210 100-1'),
        ('v260_95_04', 'V260.95-04'),
        ('v260_95_06', 'V260.95-06'),
        ('v130_00_10', 'V130.00-10'),
        ('v130_05_02', 'V130.05-02'),
        ('v130_10_08', 'V130.10-08'),
        ('v130_20_00', 'V130.20-00'),
        ('v130_20_05', 'V130.20-05'),
        ('v130_15_01', 'V130.15-01'),
        ('v130_15_03', 'V130.15-03'),
        ('v003_05_02', 'V003.05-02'),
        ('v260_95_07', 'V260.95-07'),
        ('v260_95_08', 'V260.95-08'),
        ('v260_95_09', 'V260.95-09'),
        ('v260_95_97', 'V260.95-97'),
        ('v260_95_98', 'V260.95-98'),
        ('v003_10_04', 'V003.10-04'),
        ('v130_25_01', 'V130.25-01'),
        ('v130_30_01', 'V130.30-01'),
        ('v260_95_12', 'V260.95-12'),
        ('v130_41_00', 'V130.41-00'),
    ], string="Incoming Software")

    def get_selection_label(self, field_name):
        """Return the label of a selection field"""
        field = self._fields.get(field_name)
        if not field or field.type != 'selection':
            return False
        return dict(field.selection).get(self[field_name])

    customer_error = fields.Char(string='Customer Error')
    customer_po = fields.Char(string='Customer PO')
    failure_description = fields.Text(string='Possible Reason')
    reported_issue = fields.Text(string='Reported Issue')
    priority_level = fields.Selection(
        selection=[
            ('low', "Low"),
            ('medium', "Medium"),
            ('high', "High"),
        ],
        string="Priority",
        readonly=False,
        tracking=True,
    )
    warranty_validity = fields.Date(string="Warranty Validity Up To", readonly=0)
    last_repair_date = fields.Date(string=" Last repair day")
    duration_compute = fields.Float(string="Real Duration", compute='_compute_efficiency')
    duration_expected = fields.Float(string="Production Time")
    efficiency = fields.Float("Efficiency (%)", compute='_compute_efficiency', store=True)
    barcode = fields.Char(string='Barcode', related='product_id.barcode')
    sw_label = fields.Selection([
        ('v003_10_01', 'V003.10-01'),
        ('v260_70_01', 'V260.70-01'),
        ('v260_95_01', 'V260.95-01'),
        ('2813_2f6', '2813_2F6'),
        ('2813_2f9', '2813_2F9'),
        ('2925_263', '2925_263'),
        ('2xxx_2fa', '2xxx_2FA'),
        ('190_2100_001', '190 2100-001'),
        ('190_210_100_1', '190 210 100-1'),
        ('v260_95_04', 'V260.95-04'),
        ('v260_95_06', 'V260.95-06'),
        ('v130_00_10', 'V130.00-10'),
        ('v130_05_02', 'V130.05-02'),
        ('v130_10_08', 'V130.10-08'),
        ('v130_20_00', 'V130.20-00'),
        ('v130_20_05', 'V130.20-05'),
        ('v130_15_01', 'V130.15-01'),
        ('v130_15_03', 'V130.15-03'),
        ('v003_05_02', 'V003.05-02'),
        ('v260_95_07', 'V260.95-07'),
        ('v260_95_08', 'V260.95-08'),
        ('v260_95_09', 'V260.95-09'),
        ('v260_95_97', 'V260.95-97'),
        ('v260_95_98', 'V260.95-98'),
        ('v003_10_04', 'V003.10-04'),
        ('v130_25_01', 'V130.25-01'),
        ('v130_30_01', 'V130.30-01'),
        ('v260_95_12', 'V260.95-12'),
        ('v130_41_00', 'V130.41-00'),
    ], string="Software On Label")

    repair_history_count = fields.Integer(
        string='Repair History Count',
        compute='_compute_repair_history_count'
    )
    delivery_count = fields.Integer(
        string='Delivery',
        compute='_compute_repair_history_count'
    )
    delivery_count_dc = fields.Integer(
        string='Delivery',
        compute='_compute_repair_history_count_dc'
    )

    qr_code_url = fields.Char(string="QR Code URL", compute="_compute_qr_code_url")
    qr_code = fields.Char(string="QR Code")
    qr_code_image = fields.Binary("QR Code", compute="_compute_qr_code_image", store=True)



    def action_repair_end(self):
        res = super(RepairOrderInherit, self).action_repair_end()
        for rec in self:
            rec.end_date = datetime.today()
            if rec.warranty_days and rec.warranty_days > 0:
                rec.warranty_validity = datetime.today() + timedelta(days=self.warranty_days)
            rec._onchange_warranty_up_to()
        return res

    def check_warranty(self):
        if not self.start_date:
            raise UserError("Please set the **Start Date** before checking warranty.")

        if not self.product_id:
            raise UserError("Please select the **Product** before checking warranty.")

        if not self.partner_id:
            raise UserError("Please select the **Customer** before checking warranty.")

        if not self.lot_id:
            raise UserError("Please select the **Lot/Serial Number** before checking warranty.")

        return_tag = self.env['repair.tags'].search([('name', '=', 'Under Warranty')], limit=1)
        tag = [(6, 0, [return_tag.id])] if return_tag else [(5, 0, 0)]
        print(self.product_id.name, self.partner_id.name, self.lot_id.name)
        past_repairs = self.env['repair.order'].search([
            ('partner_id', '=', self.partner_id.id),
            ('product_id', '=', self.product_id.id),
            ('lot_id', '=', self.lot_id.id),
            ('id', '!=', self.id),
            ('state', 'in', ['done', 'delivered']),
        ], order='end_date desc', limit=1)

        failure_date = self.failure_date or fields.Date.today()
        service_warranty_products = []
        if past_repairs and past_repairs.warranty_validity > failure_date:
            service_warranty_products.append(self.product_id.display_name)
            self.under_warranty = True
            return_tag = self.env['repair.tags'].search([('name', '=', 'Service Warranty')], limit=1)
            print(return_tag, 'return_tag')
            tag = [(6, 0, [return_tag.id])] if return_tag else [(5, 0, 0)]
            self.tag_ids = tag

        if past_repairs and past_repairs.move_ids:
            warranty_products = []
            for move in past_repairs.move_ids:
                if move.warranty_validity and move.warranty_validity > self.start_date:
                    warranty_products.append(move.product_id.display_name)
                    for current in self.move_ids:
                        if move.product_id.name == current.product_id.name:
                            current.tag_ids = tag
                            current.warranty_validity = move.warranty_validity
                            current.warranty_validity_check = move.warranty_validity

            msg_lines = []
            if warranty_products:
                msg_lines.append("🟢 Under Warranty: " + ", ".join(set(warranty_products)))
            if service_warranty_products:
                msg_lines.append("🔵 Service Warranty: " + ", ".join(set(service_warranty_products)))

            message = "\n".join(msg_lines) if msg_lines else "No warranty products found."

            return {
                'effect': {
                    'title': '🎉 Congratulations!',
                    'message': message,
                    'type': 'rainbow_man',
                    'sticky': True,
                }
            }


        else:

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '🔍 No History Found',
                    'message': 'No previous repair records found for warranty check.',
                    'type': 'warning',
                }
            }

    def action_generate_qr(self):
        self._compute_qr_code_url()
        self._compute_qr_code_image()

    def action_download_qr(self):
        self.ensure_one()
        if not self.qr_code_image:
            raise UserError("No QR code to download.")

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{self._name}/{self.id}/qr_code_image?download=true',
            'target': 'self',
        }

    @api.depends('product_id')
    def _compute_qr_code_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for rec in self:
            rec.qr_code_url = f"{base_url}/repair/track/{rec.id}"

    @api.depends('qr_code_url')
    def _compute_qr_code_image(self):
        for rec in self:
            if rec.qr_code_url:
                qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=4)
                qr.add_data(rec.qr_code_url)
                qr.make(fit=True)

                img = qr.make_image(fill_color="black", back_color="white")
                buffer = BytesIO()
                img.save(buffer, format="PNG")
                rec.qr_code_image = base64.b64encode(buffer.getvalue())
            else:
                rec.qr_code_image = False

    def _compute_repair_history_count(self):
        for rec in self:
            # rec.repair_history_count = self.env['repair.order'].search_count(
            #     [('partner_id', '=', self.partner_id.id), ('product_id', '=', self.product_id.id),
            #      ('lot_id', '=', self.lot_id.id), ('id', '!=', self.id), ('state', '=', ['done', 'delivered'])])
            # rec.delivery_count = self.env['stock.picking'].search_count([('origin', '=', self.name)])
            if rec.sale_order_id and rec.sale_order_id.picking_ids:
                rec.delivery_count = len(rec.sale_order_id.picking_ids)
                rec.repair_history_count = len(rec.sale_order_id.picking_ids)
            else:
                rec.delivery_count = 0
                rec.repair_history_count = 0

    def _compute_repair_history_count_dc(self):
        for rec in self:
            rec.delivery_count_dc = self.env['stock.picking'].search_count(
                [('partner_id', '=', rec.partner_id.id), ('dc_number', '=', rec.dc_number), ('state', '=', 'done')])

    work_time_id2 = fields.One2many(
        'mrp.repair', 'work_id', string='Work time',
        store=True, readonly=False)

    old_part_ids = fields.One2many(
        'old.part', 'old_part_id', "Old Parts", copy=True)

    failure_part_ids = fields.One2many(
        'failure.part', 'failure_part_id', "Failure Parts", copy=True)



    def float_to_hours_minutes(self, float_val):
        hours = int(float_val)
        minutes = int(round((float_val - hours) * 60))
        return f"{hours:02d}:{minutes:02d}"

    @api.depends('work_time_id2.duration')
    def _compute_efficiency(self):
        for record in self:
            duration_sum = sum(record.work_time_id2.mapped('duration'))  # this is already float
            duration_str = self.float_to_hours_minutes(duration_sum)  # for display/logging only

            record.duration_compute = duration_sum
            record.duration = duration_sum

            if record.duration > 0 and record.duration_expected > 0:
                record.efficiency = round((record.duration_expected / record.duration) * 100, 2)
            else:
                record.efficiency = 0.0

    def action_open_product_history(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _("Repair History"),
            'res_model': 'repair.order',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.partner_id.id), ('product_id', '=', self.product_id.id),
                       ('lot_id', '=', self.lot_id.id), ('id', '!=', self.id), ('state', '=', ['done', 'delivered'])],
        }

    def action_open_delivery_dc(self):
        repair_names = [self.name]
        repair_orders = self.env['repair.order'].search(
            [('dc_number', '=', self.dc_number), ('partner_id', '=', self.partner_id.id), ('state', '=', 'done')])
        if repair_orders:
            repair_names += repair_orders.mapped('name')

        return {
            'type': 'ir.actions.act_window',
            'name': _("Delivery"),
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('origin', 'in', repair_names)],
        }

    def action_open_delivery(self):
        # repair_names = [self.name]
        # if self.related_repair_ids:
        #     repair_names += self.related_repair_ids.mapped('name')
        return {
            'type': 'ir.actions.act_window',
            'name': _("Delivery"),
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.sale_order_id.picking_ids.ids)],
        }

    def action_create_sale_orders(self):

        if not self.filtered(lambda repair: repair.partner_id):
            raise UserError("Selected records don't have customer set.")
        if self.filtered(lambda repair: repair.sale_order_id):
            raise UserError("Selected records have already sale order create.")
        if self.filtered(lambda repair: repair.state not in ['done','cancel']):
            raise UserError("Please select records with the done or scrap status only.")
        if len(self.mapped('partner_id')) > 1:
            raise UserError("Please select records with the same customer only.")
        if len(self.mapped('company_id')) > 1:
            raise UserError("Please select records with the same company only.")
        if len(set(self.mapped('customer_state'))) > 1:
            raise UserError("Please select records with the same customer state only.")

        sale = {
                "partner_id": self.mapped('partner_id').id,
                "company_id": self.mapped('company_id').id,
                "repair_order_ids":  self.ids
                }
        sale_order= self.env['sale.order'].create(sale)

        so_line_map = {}

        for repair in self:
            # 1. Process the main Repair Product
            res_product = repair.product_id
            if res_product.id not in so_line_map:
                so_line_map[res_product.id] = {
                    'order_id': sale_order.id,
                    'product_uom': res_product.uom_id.id,
                    'product_id': res_product.id,
                    'product_uom_qty': 0,
                    'qty_delivered': 0,
                    'lot_ids': [],
                }

            # Update values for the main product
            so_line_map[res_product.id]['product_uom_qty'] += 1
            so_line_map[res_product.id]['qty_delivered'] += 1
            if repair.lot_id:
                so_line_map[res_product.id]['lot_ids'].append(Command.link(repair.lot_id.id))

            # 2. Process the Repair Parts (move_ids)
            for move in repair.move_ids.filtered(lambda m: m.repair_line_type == 'add'):
                p_id = move.product_id.id
                if p_id not in so_line_map:
                    so_line_map[p_id] = {
                        'order_id': sale_order.id,
                        'product_id': p_id,
                        'product_uom_qty': 0,
                        'product_uom': move.product_uom.id,
                        'qty_delivered': 0,
                        'is_repair_parts': True,
                        'price_unit': move.product_id.list_price if not repair.under_warranty else 0.0,
                        'lot_ids': [],
                    }

                # Update quantities
                so_line_map[p_id]['product_uom_qty'] += move.quantity
                if move.state == 'done':
                    so_line_map[p_id]['qty_delivered'] += move.quantity

                # If moves have lots/serials, you can link them here as well
                if move.lot_ids:
                    for lot in move.lot_ids:
                        so_line_map[p_id]['lot_ids'].append(Command.link(lot.id))

        # Create all lines at once from the dictionary values
        self.env['sale.order.line'].create(list(so_line_map.values()))

        return {
            'name': 'Sale Order',
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': sale_order.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_repair_done(self):
        """ Creates stock move for final product of repair order.
        Writes move_id and move_ids state to 'done'.
        Writes repair order state to 'Repaired'.
        @return: True
        """

        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')
        product_move_vals = []

        # Cancel moves with 0 quantity
        self.move_ids.filtered(
            lambda m: float_is_zero(m.quantity, precision_rounding=m.product_uom.rounding))._action_cancel()

        no_service_policy = 'service_policy' not in self.env['product.template']
        # SOL qty delivered = repair.move_ids.quantity
        for repair in self:
            if all(not move.picked for move in repair.move_ids):
                repair.move_ids.picked = True
            if repair.sale_order_line_id:
                ro_origin_product = repair.sale_order_line_id.product_template_id
                # TODO: As 'service_policy' only appears with 'sale_project' module, isolate conditions related to this field in a 'sale_project_repair' module if it's worth
                if ro_origin_product.type == 'service' and (
                        no_service_policy or ro_origin_product.service_policy == 'ordered_prepaid'):
                    repair.sale_order_line_id.qty_delivered = repair.sale_order_line_id.product_uom_qty
            if not repair.product_id:
                continue

            if repair.product_id.product_tmpl_id.tracking != 'none' and not repair.lot_id:
                raise ValidationError(_(
                    "Serial number is required for product to repair : %s",
                    repair.product_id.display_name
                ))

            # Try to create move with the appropriate owner
            owner_id = False
            available_qty_owner = self.env['stock.quant']._get_available_quantity(repair.product_id, repair.location_id,
                                                                                  repair.lot_id,
                                                                                  owner_id=repair.partner_id,
                                                                                  strict=True)
            if float_compare(available_qty_owner, repair.product_qty, precision_digits=precision) >= 0:
                owner_id = repair.partner_id.id

            move_lines = repair.move_ids.move_line_ids
            for line in move_lines:
                if line.product_id.type == 'service':
                    move_lines -= line

            product_move_vals.append({
                'name': repair.name,
                'product_id': repair.product_id.id,
                'product_uom': repair.product_uom.id or repair.product_id.uom_id.id,
                'product_uom_qty': repair.product_qty,
                'partner_id': repair.partner_id.id,
                'location_id': repair.product_location_src_id.id,
                'location_dest_id': repair.product_location_dest_id.id,
                'picked': True,
                'picking_id': False,
                'move_line_ids': [(0, 0, {
                    'product_id': repair.product_id.id,
                    'lot_id': repair.lot_id.id,
                    'product_uom_id': repair.product_uom.id or repair.product_id.uom_id.id,
                    'quantity': repair.product_qty,
                    'package_id': False,
                    'result_package_id': False,
                    'owner_id': owner_id,
                    'location_id': repair.product_location_src_id.id,
                    'company_id': repair.company_id.id,
                    'location_dest_id': repair.product_location_dest_id.id,
                    'consume_line_ids': [(6, 0, move_lines.ids)]
                })],
                'repair_id': repair.id,
                'origin': repair.name,
                'company_id': repair.company_id.id,
            })

        product_moves = self.env['stock.move'].create(product_move_vals)
        repair_move = {m.repair_id.id: m for m in product_moves}
        for repair in self:
            move_id = repair_move.get(repair.id, False)
            if move_id:
                repair.move_id = move_id

        move_ids = self.move_ids
        for move_id in move_ids:
            if move_id.product_id.type == 'service':
                move_ids -= move_id
        all_moves = move_ids + product_moves
        all_moves._action_done(cancel_backorder=True)

        for sale_line in self.move_ids.sale_line_id:
            price_unit = sale_line.price_unit
            sale_line.write({'product_uom_qty': sale_line.qty_delivered, 'price_unit': price_unit})

        self.state = 'done'
        return True

    def back_to_under_repair(self):
        for repair in self:
            if repair.state != 'done':
                raise UserError(_("Only 'Done' repair orders can be reset."))

            # 1. Find the internal transfer picking type
            picking_type = self.env['stock.picking.type'].search([
                ('code', '=', 'internal'),
                ('warehouse_id', '=', repair.picking_type_id.warehouse_id.id)
            ], limit=1)

            if not picking_type:
                raise UserError(_("No internal picking type found for this warehouse."))

            # 2. Build the Move Data
            move_vals = []
            for move in repair.move_ids:
                if move.state == 'done':
                    # Create move lines from the original finished moves
                    move_lines = []
                    for line in move.move_line_ids:
                        # Check for Odoo 17+ 'quantity' or Odoo 16 'qty_done'
                        qty = getattr(line, 'quantity', getattr(line, 'qty_done', 0.0))

                        move_lines.append((0, 0, {
                            'product_id': line.product_id.id,
                            'product_uom_id': line.product_uom_id.id,
                            'location_id': move.location_dest_id.id,  # Returning from where it was
                            'location_dest_id': move.location_id.id,  # To the repair input
                            'lot_id': line.lot_id.id if line.lot_id else False,  # Key: Pass the Lot ID
                            'quantity': qty,
                        }))

                    move_vals.append((0, 0, {
                        'name': move.name,
                        'product_id': move.product_id.id,
                        'product_uom_qty': move.quantity,
                        'product_uom': move.product_uom.id,
                        'location_id': move.location_dest_id.id,
                        'location_dest_id': move.location_id.id,
                        'repair_id': repair.id,
                        'move_line_ids': move_lines,  # Link the lines here
                    }))

            # 3. Create and Validate Picking
            if move_vals:
                picking = self.env['stock.picking'].create({
                    'picking_type_id': picking_type.id,
                    'location_id': repair.location_dest_id.id,
                    'location_dest_id': repair.location_id.id,
                    'origin': f"Reset Repair: {repair.name}",
                    'move_ids_without_package': move_vals
                })

                # Confirming and validating the picking automatically processes the move lines
                picking.action_confirm()
                picking.button_validate()

                repair.message_post(body=_("Repair reset. Parts returned via Picking: %s") % picking.name)
            else:
                repair.message_post(body=_("Repair reset (No parts returned)."))

            # 4. Update Repair State
            repair.move_ids.write({'state': 'draft'})
            repair.write({
                'state': 'under_repair',
                'move_id': False,
            })
    def action_create_material_requisition(self):
        self.ensure_one()
        if not self.move_ids:
            return

        req_lines = []
        for move in self.move_ids:
            req_lines.append((0, 0, {
                'product_id': move.product_id.id,
                'description': move.name or move.product_id.display_name,
                'quantity': move.product_uom_qty,
                'unit_of_measure_id': move.product_uom.id,
                'move_id': move.id,  # CRITICAL: This establishes the link
            }))

        # Create the Material Requisition
        requisition = self.env['material.requisition'].create({
            'repair_id': self.id,
            'request_line_ids': req_lines,
            'state': 'new',
        })

        self.write({'state': 'material_requested'})  # Update repair order state

        # Return action to open the newly created requisition
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'material.requisition',
            'view_mode': 'form',
            'res_id': requisition.id,
            'target': 'current',
        }



    def _compute_requisition_count(self):
        for record in self:
            record.requisition_count = self.env['material.requisition'].search_count([('repair_id', '=', record.id)])

    def action_view_material_requisitions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Material Requisitions',
            'res_model': 'material.requisition',
            'view_mode': 'list,form',
            'domain': [('repair_id', '=', self.id)],
            'context': {'default_repair_id': self.id},
            'target': 'current',
        }

    def action_repair_start(self):
        """ Writes repair order state to 'Under Repair'
        """
        if self.move_ids and self.requisition_count == 0:
            raise UserError(_("Please create a material requisition before starting the repair."))
        if self.move_ids and self.requisition_count > 0 and self.state != 'material_approved':
            raise UserError(_("Material requisition must be approved before starting the repair."))

        if self.filtered(lambda repair: repair.state != 'confirmed'):
            self._action_repair_confirm()
        return self.write({'state': 'under_repair'})

    def _action_repair_confirm(self):
        """ Repair order state is set to 'Confirmed'.
        @param *arg: Arguments
        @return: True
        """
        repairs_to_confirm = self.filtered(lambda repair: repair.state == 'draft')
        repairs_to_confirm._check_company()
        repairs_to_confirm.move_ids._check_company()
        repairs_to_confirm.move_ids._adjust_procure_method(picking_type_code='repair_operation')
        repairs_to_confirm.move_ids._action_confirm()
        repairs_to_confirm.move_ids._trigger_scheduler()
        for repair in repairs_to_confirm:
            # Find all material requisitions linked to this repair order
            requisitions = self.env['material.requisition'].search([('repair_id', '=', repair.id)])

            if requisitions:
                # Extract all the states of the linked requisitions into a list
                req_states = requisitions.mapped('state')

                # Apply priority logic to determine the repair order state
                if 'confirmed' in req_states:
                    repair.write({'state': 'material_requested'})
                elif 'on_hold' in req_states:
                    repair.write({'state': 'material_on_hold'})
                elif 'refuse' in req_states:
                    repair.write({'state': 'material_refused'})
                elif 'approved' in req_states:
                    repair.write({'state': 'material_approved'})
                elif 'cancelled' in req_states:
                    repair.write({'state': 'material_cancelled'})
                else:
                    repair.write({'state': 'confirmed'})
            else:
                # Normal behavior if no material requests exist at all
                repair.write({'state': 'confirmed'})
        return True

    def action_repair_cancel(self):
        if any(repair.state == 'done' for repair in self):
            raise UserError(_("You cannot cancel a Repair Order that's already been completed"))
        for repair in self:
            if repair.sale_order_id:
                repair.sale_order_line_id.write({'product_uom_qty': 0.0})  # Quantity of the product that generated the RO is set to 0
        self.move_ids._action_cancel()

        for repair in self:
            if repair.requisition_count > 0:
                requisitions = self.env['material.requisition'].search([('repair_id', '=', repair.id)])
                requisitions.write({'state': 'cancelled'})
        return self.write({'state': 'cancel'})


class MrpRepair(models.Model):
    _name = 'mrp.repair'
    _description = 'Work Repair'

    duration_tracked = fields.Float("Tracked Duration", default=0.0, store=True)

    production_id = fields.Many2one('repair.order', 'work time', required=False,
                                    readonly=False, )

    work_id = fields.Many2one('repair.order', 'work time', required=False,
                              readonly=False, )

    state = fields.Selection([
        ('pending', 'Waiting for another WO'),
        ('waiting', 'Waiting for components'),
        ('ready', 'Ready'),
        ('progress', 'In Progress'),
        ('done', 'Finished'),
        ('cancel', 'Cancelled')], string='Status',
        store=True,
        default='pending', copy=False, readonly=True, recursive=True, index=True)

    is_user_working = fields.Boolean(
        'Is the Current User Working', )

    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True,
    )

    date_start = fields.Datetime(
        'Start',
        store=True, copy=False)
    date_finished = fields.Datetime(
        'End',
        store=True, copy=False)
    duration_expected = fields.Float(
        'Expected Duration', digits=(16, 2), compute='_compute_duration_expected',
        readonly=False, store=True)  # in minutes
    duration = fields.Float(
        'Real Duration', compute='_compute_duration',
        readonly=False, store=True, copy=False)

    def button_stop(self):

        for wo in self:
            if wo.date_start:
                delta = fields.Datetime.now() - wo.date_start
                tracked_minutes = delta.total_seconds() / 60.0
                wo.duration_tracked += tracked_minutes  # ⬅️ ADD this

            wo.write({
                'is_user_working': False,
                'date_finished': fields.Datetime.now(),
                'date_start': False,  # Optional: clear start for clarity
            })
        self.production_id._compute_efficiency()

    def _should_start_timer(self):
        return True

    def _prepare_timeline_vals(self, duration, date_start, date_end=False):
        # Need a loss in case of the real time exceeding the expecte
        return

    def _calculate_date_finished(self, date_start=False):
        return

    def button_start(self, raise_on_invalid_state=False):
        for wo in self:
            wo.is_user_working = True
            if wo.state in ('done', 'cancel'):
                if raise_on_invalid_state:
                    continue
                raise UserError(_('You cannot start a work order that is already done or cancelled'))

            vals = {
                'state': 'progress',
                'is_user_working': True,
            }

            # ✅ Sirf pehli baar start ho raha ho to date_start do
            if not wo.date_start:
                vals['date_start'] = fields.Datetime.now()

            # Agar pause ke baad resume ho raha hai, to date_start ko mat ched
            vals['date_finished'] = False
            wo.write(vals)

    @api.depends('duration_tracked', 'date_start', 'date_finished', 'is_user_working')
    def _compute_duration(self):
        for record in self:
            duration = record.duration_tracked
            if record.is_user_working and record.date_start:
                delta = datetime.now() - record.date_start
                duration += delta.total_seconds() / 60.0
            record.duration = duration

    def get_duration(self):
        self.ensure_one()
        duration = self.duration_tracked
        if self.is_user_working and self.date_start:
            delta = datetime.now() - self.date_start
            duration += delta.total_seconds() / 60.0
        return duration

    def button_finish(self):
        date_finished = fields.Datetime.now()
        for workorder in self:
            vals = {
                'state': 'done',
                'date_finished': date_finished,
            }
            if workorder.date_start and date_finished < workorder.date_start:
                vals['date_start'] = date_finished
            workorder.with_context(bypass_duration_calculation=True).write(vals)
            workorder.production_id._compute_efficiency()

        return True


class RepairConfirmationWizard(models.TransientModel):
    _name = 'repair.confirmation.wizard'
    _description = 'Repair Confirmation Wizard'
    is_warranty = fields.Boolean("Declare Service warranty")
    warranty_days = fields.Integer("Warranty Duration (Days)")
    repair_id = fields.Many2one('repair.order', string="Repair Order")
    note = fields.Text("Internal Note")

    def confirm_repair(self):
        if self.repair_id:
            if self.warranty_days:
                self.repair_id.write({'warranty_days': self.warranty_days})
            self.repair_id.action_repair_end()


class OldPart(models.Model):
    _name = 'old.part'
    _description = 'old part'

    fi_part_old = fields.Text("Fi Part Old")
    product_id = fields.Many2one('product.product', 'Product')

    old_part_id = fields.Many2one('repair.order', 'work time', required=False,
                                  readonly=False, )

    warranty_validity = fields.Date(string="Warranty Validity Up To", readonly=1)
    tag_ids = fields.Many2many('repair.tags', string="Tags")

class FailurePart(models.Model):
    _name = 'failure.part'
    _description = 'Failure Parts'

    failure_part_id = fields.Many2one('repair.order', 'failure', required=False,
                                  readonly=False, )
    product_id = fields.Many2one('product.product', 'Product')
    barcode_text = fields.Text('Barcode Scan', required=False,
                                  readonly=False, )
    quantity = fields.Integer('Quantity')


class StockReturnPickingInherit(models.TransientModel):
    _inherit = "stock.return.picking"

    def action_create_returns(self):
        res = super(StockReturnPickingInherit, self).action_create_returns()
        for rec in self:
            return_tag = self.env['repair.tags'].search([('name', '=', 'Return')], limit=1)
            repair_return = self.env['repair.order'].search([('name', '=', rec.picking_id.origin)], limit=1)
            if repair_return:
                repair_return.return_date = datetime.today()
                repair_return.picking_id = rec.picking_id.id
                repair_return.tag_ids = [(6, 0, [return_tag.id])] if return_tag else [(5, 0, 0)]
        return res

    def action_create_returns_all(self):
        res = super(StockReturnPickingInherit, self).action_create_returns_all()
        for rec in self:
            repair_return = self.env['repair.order'].search([('name', '=', rec.picking_id.origin)], limit=1)
            return_tag = self.env['repair.tags'].search([('name', '=', 'Return')], limit=1)
            if repair_return:
                repair_return.return_date = datetime.today()
                repair_return.picking_id = rec.picking_id.id
                repair_return.tag_ids = [(6, 0, [return_tag.id])] if return_tag else [(5, 0, 0)]
        return res


class StockReturnPickingLine(models.TransientModel):
    _inherit = 'stock.return.picking.line'

    def _process_line(self, new_picking):
        self.ensure_one()
        if not float_is_zero(self.quantity, precision_rounding=self.uom_id.rounding):
            vals = self._prepare_move_default_values(new_picking)

            if self.move_id:
                # Create a copy of the move
                new_return_move = self.move_id.copy(vals)
                vals = {}

                # Link origin & destination moves
                move_orig_to_link = self.move_id.move_dest_ids.returned_move_ids
                move_orig_to_link |= self.move_id
                move_orig_to_link |= self.move_id.move_dest_ids.filtered(
                    lambda m: m.state not in ('cancel')
                ).move_orig_ids.filtered(
                    lambda m: m.state not in ('cancel')
                )

                move_dest_to_link = self.move_id.move_orig_ids.returned_move_ids
                move_dest_to_link |= self.move_id.move_orig_ids.returned_move_ids.move_orig_ids.filtered(
                    lambda m: m.state not in ('cancel')
                ).move_dest_ids.filtered(
                    lambda m: m.state not in ('cancel')
                )

                vals['move_orig_ids'] = [Command.link(m.id) for m in move_orig_to_link]
                vals['move_dest_ids'] = [Command.link(m.id) for m in move_dest_to_link]

                new_return_move.write(vals)

                # ✅ FIX: Clear repair_id and origin to avoid duplicate lines in repair
                new_return_move.repair_id = False
                new_return_move.origin = 'Return'
                new_return_move.reference = 'Return'

            else:
                self.env['stock.move'].create(vals)

            return True
