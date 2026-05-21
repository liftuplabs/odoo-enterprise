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
import io
import xlsxwriter

class StockPicking(models.Model):
    _inherit = 'stock.picking'

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

    dc_number = fields.Char(string="DC Number")
    lot_id = fields.Many2one('stock.lot', 'Lot/Serial', readonly=True)
    lot_ids = fields.Many2many('stock.lot', readonly=True)
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    product_ids = fields.Many2many('product.product', string='Products')
    plant = fields.Selection(
        selection=plant_selection,
        string="Plant"
    )
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

    is_inward_confirm = fields.Boolean(
        string="Is Inward Confirmed",
        default=False,
        copy=False,
        tracking=True
    )

    product_names = fields.Text(
        string="Product Names",
        compute="_compute_aggregated_move_data",
        store=True,
        help="Summary of all products in this transfer"
    )
    serial_numbers = fields.Text(
        string="Serial Numbers",
        compute="_compute_aggregated_move_data",
        store=True,
        help="Summary of all serial numbers assigned in this transfer"
    )

    barcode_scan_trigger = fields.Char(string="Scan Serial Number", store=False)
    scanning_mode = fields.Selection([
        ('product', 'Product'),
        ('serial', 'Serial Number')
    ], string="Scanning Mode", default='serial')

    @api.onchange('barcode_scan_trigger')
    def _onchange_barcode_scan_trigger(self):
        if not self.barcode_scan_trigger or not self.scanning_mode:
            return

        scanned_val = self.barcode_scan_trigger.strip()
        found = False
        message = ""

        if self.scanning_mode == 'product':
            # Find the product based on the scanned barcode or internal reference
            product = self.env['product.product'].search([
                '|', ('name', '=', scanned_val), ('default_code', '=', scanned_val)
            ], limit=1)

            if product:
                for move in self.move_ids_without_package:
                    # Match if customer intended this product and it's not yet verified
                    if move.customer_product_id == product and not move.actual_product_id:
                        move.actual_product_id = product
                        # Also update any associated move lines
                        move.move_line_ids.write({'product_id': product.id})
                        found = True
                        message = _('Product "%s" verified successfully.') % product.display_name
                        break
            else:
                message = _('No product found with barcode : %s') % scanned_val

        # --- MODE 2: VERIFY SERIAL NUMBER ---
        elif self.scanning_mode == 'serial':
            for line in self.move_line_ids:
                if line.customer_lot_name == scanned_val and not line.lot_name:
                    line.lot_name = scanned_val
                    # Ensure product_id is also filled if it wasn't already verified
                    if line.move_id.customer_product_id and not line.product_id:
                        line.product_id = line.move_id.customer_product_id
                        line.move_id.product_id = line.move_id.customer_product_id

                    found = True
                    message = _('Serial Number "%s" verified successfully.') % scanned_val
                    break

        self.barcode_scan_trigger = False

        if found:
            return {'warning': {'title': _('Success'), 'message': message}}
        else:
            return {'warning': {'title': _('Verification Failed'),
                                'message': message or _('No match found for: %s') % scanned_val}}


    @api.depends('move_ids.product_id', 'move_ids.move_line_ids.lot_name')
    def _compute_aggregated_move_data(self):
        for picking in self:
            products = picking.move_ids.mapped('product_id.display_name')
            picking.product_names = ", ".join(filter(None, set(products)))

            serials = picking.move_ids.mapped('move_line_ids.lot_name')
            picking.serial_numbers = ", ".join(filter(None, set(serials)))

    def action_set_inward_confirm(self):
        """ Method to mark the receipt as inward confirmed """
        for record in self:
            record.is_inward_confirm = True

    def button_validate(self):
        for rec in self.move_ids_without_package.filtered(lambda t: t.picked == False):
            rec.picked = True
        res = super(StockPicking, self).button_validate()
        for repair_id in self.sale_id.repair_ids:
            repair_id.write({'state': 'delivered'})
        return res

    def action_export_difference_report(self):
        output = io.BytesIO()
        import xlsxwriter
        workbook = xlsxwriter.Workbook(output)
        sheet = workbook.add_worksheet('Difference Report')

        # Formatting
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'border': 1})

        headers = [
            'DC Number', 'DC Date', 'Customer', 'Customer State',
            'Drive Type(Customer)', 'Drive Type(Adroit)', 'Drive Type Difference',
            'Serial Number(Customer)', 'Serial Number(Adroit)', 'Serial Number Difference'
        ]

        # Write Headers
        for col, text in enumerate(headers):
            sheet.write(0, col, text, header_fmt)

        row = 1
        # Loop through ALL selected pickings
        for picking in self:
            dc_number = picking.dc_number or ''
            dc_date = str(picking.dc_date) if picking.dc_date else ''
            customer = picking.partner_id.name or ''
            customer_state = picking.customer_state or ''

            for ml in picking.move_line_ids:
                cust_prod = ml.move_id.customer_product_id.name or ''
                adr_prod = ml.product_id.name or ''
                prod_diff = cust_prod != adr_prod

                cust_serial = ml.customer_lot_name or ''
                adr_serial = ml.lot_name or ml.lot_id.name or ''
                serial_diff = cust_serial != adr_serial

                sheet.write(row, 0, dc_number)
                sheet.write(row, 1, dc_date)
                sheet.write(row, 2, customer)
                sheet.write(row, 3, customer_state)
                sheet.write(row, 4, cust_prod)
                sheet.write(row, 5, adr_prod)
                sheet.write(row, 6, 'TRUE' if prod_diff else 'FALSE')
                sheet.write(row, 7, cust_serial)
                sheet.write(row, 8, adr_serial)
                sheet.write(row, 9, 'TRUE' if serial_diff else 'FALSE')
                row += 1

        workbook.close()
        output.seek(0)

        # FIXED: Prevent Singleton Error by checking length first
        if len(self) > 1:
            file_name = f'Difference_Report_Multiple_{fields.Date.today()}.xlsx'
        else:
            safe_name = self.name.replace('/', '_') if self.name else 'Picking'
            file_name = f'Difference_Report_{safe_name}.xlsx'

        attachment = self.env['ir.attachment'].create({
            'name': file_name,
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }

    # def action_open_serial_excel_wizard(self):
    #     return {
    #         'type': 'ir.actions.act_window',
    #         'name': 'Import Serial Excel',
    #         'res_model': 'serial.excel.import.wizard',
    #         'view_mode': 'form',
    #         'target': 'new',
    #         'context': {
    #             # Optionally pass something to context
    #         }
    #     }

    # def custom_return_with_dc(self):
    #     return {
    #         'type': 'ir.actions.act_window',
    #         'name': 'Return with DC Number',
    #         'res_model': 'return.dc.wizard',
    #         'view_mode': 'form',
    #         'target': 'new',
    #         # 'context': {
    #         #     'default_picking_ids': [p.id for p in self],
    #         # }
    #     }

    # def auto_populate_data(self):
    #     for rec in self:
    #         rec.plant = False
    #         # self.customer_state = False
    #         existing_quant = self.env['stock.quant'].with_context(prefetch_fields=False).search([
    #             ('lot_id', '=', rec.lot_id.id),
    #             ('product_id', '=', rec.product_id.id),
    #             ('inventory_quantity_auto_apply', '>', 0)
    #         ], limit=1)
    #         if existing_quant:
    #             if existing_quant.plant:
    #                 rec.plant = existing_quant.plant



    # def action_return_all_and_validate(self, dc_number=None):
    #     RepairOrder = self.env['repair.order']
    #     Picking = self.env['stock.picking']
    #     Move = self.env['stock.move']
    #     MoveLine = self.env['stock.move.line']
    #     Quant = self.env['stock.quant']
    #
    #     return_picking = None
    #
    #     for picking in self:
    #         repair = RepairOrder.search([('name', '=', picking.origin)], limit=1)
    #         if not repair or not repair.product_id or not repair.lot_id:
    #             continue
    #
    #         product = repair.product_id
    #         lot = repair.lot_id
    #
    #         source_location = picking.location_dest_id.id
    #         return_location = picking.location_id.id
    #
    #         if not return_picking:
    #             return_picking = Picking.create({
    #                 'origin': 'Multiple Returns - ' + (dc_number or ''),
    #                 'picking_type_id': self.env.ref('stock.picking_type_in').id,
    #                 'location_id': source_location,
    #                 'location_dest_id': return_location,
    #                 'move_type': 'direct',
    #                 'partner_id': repair.partner_id.id
    #             })
    #
    #         move = Move.create({
    #             'name': product.display_name,
    #             'product_id': product.id,
    #             'product_uom_qty': 1.0,
    #             'product_uom': product.uom_id.id,
    #             'location_id': source_location,
    #             'location_dest_id': return_location,
    #             'picking_id': return_picking.id,
    #         })
    #
    #         MoveLine.create({
    #             'move_id': move.id,
    #             'picking_id': return_picking.id,
    #             'product_id': product.id,
    #             'product_uom_id': product.uom_id.id,
    #             'quantity': 1.0,
    #             'lot_id': lot.id,
    #             'location_id': source_location,
    #             'location_dest_id': return_location,
    #         })
    #
    #         repair.return_date = fields.Date.today()
    #
    #         quant = Quant.search([
    #             ('product_id', '=', product.id),
    #             ('lot_id', '=', lot.id),
    #             ('location_id', '=', return_location),
    #         ], limit=1)
    #
    #         if quant:
    #             quant.plant = repair.plant
    #             quant.partner_id = repair.partner_id.id
    #             quant.dc_number = dc_number
    #
    #     if return_picking:
    #         # Collect all lot_ids and product_ids from its move lines
    #         lot_ids = return_picking.move_line_ids.filtered(lambda l: l.lot_id).mapped('lot_id').ids
    #         product_ids = return_picking.move_line_ids.mapped('product_id').ids
    #
    #         return_picking.write({
    #             'lot_ids': [(6, 0, lot_ids)],
    #             'product_ids': [(6, 0, product_ids)],
    #         })
    #
    #     if return_picking:
    #         return {
    #             'type': 'ir.actions.act_window',
    #             'res_model': 'stock.picking',
    #             'res_id': return_picking.id,
    #             'view_mode': 'form',
    #             'target': 'current',
    #         }
    #
    #
    #
    #     return {'type': 'ir.actions.act_window_close'}
    #
    # def action_return_all_and_validate2(self,dc_number=None):
    #     RepairOrder = self.env['repair.order']
    #     Picking = self.env['stock.picking']
    #     Move = self.env['stock.move']
    #     MoveLine = self.env['stock.move.line']
    #     Quant = self.env['stock.quant']
    #
    #     for picking in self:
    #         repair = RepairOrder.search([('name', '=', picking.origin)], limit=1)
    #         if not repair or not repair.product_id or not repair.lot_id:
    #             continue
    #
    #         product = repair.product_id
    #         lot = repair.lot_id
    #
    #         # From where it's being returned
    #         source_location = picking.location_dest_id.id  # e.g., customer location
    #         return_location = picking.location_id.id  # e.g., stock location
    #
    #         # NOTE: Removed lot_in_stock check — even if it's already returned, we want to ensure qty is updated
    #
    #         # Create return picking
    #         return_picking = Picking.create({
    #             'origin': picking.name + ' - Return',
    #             'picking_type_id': self.env.ref('stock.picking_type_in').id,
    #             'location_id': source_location,
    #             'location_dest_id': return_location,
    #             'move_type': 'direct',
    #             'dc_number': dc_number,
    #         })
    #
    #         # Create stock move
    #         move = Move.create({
    #             'name': product.display_name,
    #             'product_id': product.id,
    #             'product_uom_qty': 1.0,
    #             'product_uom': product.uom_id.id,
    #             'location_id': source_location,
    #             'location_dest_id': return_location,
    #             'picking_id': return_picking.id,
    #         })
    #
    #         # Create move line with qty_done (mandatory)
    #         MoveLine.create({
    #             'move_id': move.id,
    #             'picking_id': return_picking.id,
    #             'product_id': product.id,
    #             'product_uom_id': product.uom_id.id,
    #             'quantity': 1.0,  # ✅ Required for validation
    #             'lot_id': lot.id,
    #             'location_id': source_location,
    #             'location_dest_id': return_location,
    #         })
    #
    #         # Validate the picking
    #         return_picking.with_context(skip_immediate=True).button_validate()
    #
    #         # Update return date in repair
    #         repair.return_date = fields.Date.today()
    #
    #         quant = Quant.search([
    #             ('product_id', '=', product.id),
    #             ('lot_id', '=', lot.id),
    #             ('location_id', '=', return_location),
    #         ], limit=1)
    #
    #         if quant:
    #             print("iam here")
    #             quant.plant = repair.plant
    #             quant.partner_id = repair.partner_id.id
    #             quant.dc_number = dc_number
