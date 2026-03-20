# models/hr_employee_document.py

from odoo import models, fields, api
from odoo.exceptions import AccessError
from odoo import models, api, _
from odoo.exceptions import ValidationError
import math
from geopy.distance import geodesic
from odoo import models, fields, api
import base64
import xlrd
import pandas as pd
import io



class ResUsers(models.Model):
    _inherit = "res.users"

    can_edit_repair_parts = fields.Boolean(
        string="Can Edit Repair Parts",
        compute="_compute_can_edit_repair_parts",
        inverse="_inverse_can_edit_repair_parts",
        store=False,  # optional, no need to store
    )

    @api.depends('groups_id')
    def _compute_can_edit_repair_parts(self):
        repair_group = self.env.ref('repair_history.group_edit_repair_stock_moves')
        for user in self:
            user.can_edit_repair_parts = repair_group in user.groups_id

    def _inverse_can_edit_repair_parts(self):
        repair_group = self.env.ref('repair_history.group_edit_repair_stock_moves')
        for user in self:
            if user.can_edit_repair_parts:
                user.groups_id = [(4, repair_group.id)]
            else:
                user.groups_id = [(3, repair_group.id)]

class ResCompanyInherit(models.Model):
    _inherit = 'res.company'

    allowed_latitude = fields.Float("Allowed Latitude")
    allowed_longitude = fields.Float("Allowed Longitude")
    allowed_radius_km = fields.Float("Allowed Radius (KM)", default=0.2)



class HrAttendance(models.Model):
    _inherit = 'hr.attendance'


    is_manually_check_in = fields.Boolean(string='Manually Check In')

    @api.constrains('check_in','check_out')
    def _check_in_validation(self):
        company = self.env.user.company_id
        lat = self.in_latitude
        lon = self.in_longitude
        if not lon and not lat and self.is_manually_check_in == False:
            raise ValidationError(_("Location permission is required to check out."))
        if lat and lon and company.allowed_latitude and company.allowed_longitude and self.is_manually_check_in == False:
            allowed_point = ((company.allowed_latitude), (company.allowed_longitude))
            user_point = (lat, lon)
            distance = geodesic(allowed_point, user_point).meters
            if distance > company.allowed_radius_km:
                raise ValidationError(_("You can't check in outside the company location."))
        lat_out = self.out_latitude
        lon_out = self.out_longitude

        if not lat_out and not lon_out and self.is_manually_check_in == False:
            raise ValidationError(_("Location permission is required to check out."))
        if lat_out and lon_out and company.allowed_latitude and company.allowed_longitude and self.is_manually_check_in == False:
            allowed_point = (company.allowed_latitude, company.allowed_longitude)
            user_point = (lon_out, lon_out)
            distance = geodesic(allowed_point, user_point).meters
            if distance > company.allowed_radius_km:
                raise ValidationError(_("You can't check out outside the company location."))

    @api.model
    def _haversine_distance(self, lat1, lon1, lat2, lon2):
        R = 6371  # Earth radius in KM
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        d_phi = math.radians(lat2 - lat1)
        d_lambda = math.radians(lon2 - lon1)

        a = math.sin(d_phi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c



class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    def _action_done(self):
        res = super()._action_done()

        for line in self:
            picking = line.picking_id
            quant = self.env['stock.quant'].search([
                ('product_id', '=', line.product_id.id),
                ('lot_id', '=', line.lot_id.id),
                ('location_id', '=', line.location_dest_id.id),
            ], limit=1)

            if quant and picking:
                quant.partner_id = picking.partner_id.id
                quant.dc_number = picking.dc_number
                quant.plant = picking.plant
                quant.customer_state = picking.customer_state
                quant.dc_date = picking.dc_date

        lot_ids = self.picking_id.move_ids_without_package.filtered(lambda l: l.lot_ids).mapped('lot_ids').ids
        product_ids = self.picking_id.move_ids_without_package.filtered(lambda l: l.product_id).mapped('product_id').ids

        self.picking_id.lot_ids = [(6, 0, lot_ids)]
        self.picking_id.product_ids = [(6, 0, product_ids)]

        return res


class SerialExcelImportWizard(models.TransientModel):
    _name = 'serial.excel.import.wizard'
    _description = 'Import Serial Numbers from Excel'

    file = fields.Binary("Upload Excel", required=True)
    file_name = fields.Char("File Name")
    serial_ids = fields.One2many('serial.import.line', 'wizard_id', string="Serials Found")

    def action_import_serials(self):
        self.serial_ids.unlink()

        data = base64.b64decode(self.file)
        df = pd.read_excel(io.BytesIO(data), engine='openpyxl')

        lines = []
        for serial in df.iloc[:, 0].dropna():
            serial_number = str(serial).strip()
            if serial_number:
                lines.append((0, 0, {'serial_number': serial_number}))

        self.serial_ids = lines
        serials = self.serial_ids.mapped('serial_number')
        print(serials,'serialsserialsserialsserials')


        # 🔍 Now search on stock.picking's lot_ids.name
        pickings = self.env['stock.picking'].search([
            ('state', '=', 'done'),
            ('picking_type_id.code', '!=', 'incoming'),
            ('lot_ids.name', 'in', serials)
        ])

        print(pickings, 'pickings')



        return {
            'type': 'ir.actions.act_window',
            'name': 'Delivered Pickings by Serial',
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('id', 'in', pickings.ids)],
            'target': 'current',
        }

    def action_show_related_deliveries(self):
        pass




class SerialImportLine(models.TransientModel):
    _name = 'serial.import.line'
    _description = 'Serial Entry in Excel'

    wizard_id = fields.Many2one('serial.excel.import.wizard', ondelete="cascade")
    serial_number = fields.Char("Serial Number")

class SaleAdvancePaymentInvInherit(models.TransientModel):
    _inherit = "sale.advance.payment.inv"

    def create_invoices(self):
        result = super(SaleAdvancePaymentInvInherit, self).create_invoices()
        invoice = self.env['account.move'].browse(result.get('res_id'))
        sale_order = self.env['sale.order'].browse(self._context.get('active_id'))
        if invoice and sale_order.purchase_order_ids:
            for line in invoice.invoice_line_ids:
                for so_line in line.sale_line_ids:
                    if not so_line.is_repair_parts:
                        line.unlink()
        # active_id se current sale order fetch karo
        # sale_order = self.env['sale.order'].browse(self._context.get('active_id'))
        # if sale_order:
        #     # linked repair orders
        #     repair_orders = sale_order.repair_order_ids
        #     for repair in repair_orders:
        #         if repair.state not in ('delivered', 'cancel'):
        #             # move_type error avoid karne ke liye context override
        #             repair.action_mark_repair_delivered()
        #         else:
        #             raise ValidationError(
        #                 f"Repair Order {repair.name} is already {repair.state}. Delivery cannot be processed.")

        # wizard ka normal action dict return karo
        return result



