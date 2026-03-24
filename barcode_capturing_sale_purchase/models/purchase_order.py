# -*- coding: utf-8 -*-
################################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2025-TODAY Cybrosys Technologies(<https://www.cybrosys.com>).
#    Author: Manasa T P (odoo@cybrosys.com)
#
#    You can modify it under the terms of the GNU AFFERO
#    GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#    You should have received a copy of the GNU AFFERO GENERAL PUBLIC LICENSE
#    (AGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
################################################################################
from odoo import api, fields, models, tools, _, Command

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    is_verified = fields.Boolean(string="Is Verified", default=False)
    dc_number = fields.Char(string="DC Number")
    dc_date = fields.Date(
        'Dc Date', default=fields.Date.context_today, tracking=True)
    partner_id = fields.Many2one('res.partner', string='Customer Name')
    inward_date = fields.Date(
        'Inward Date', default=fields.Date.context_today, tracking=True)
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

    plant = fields.Selection(
        selection=plant_selection,
        string="Plant",
    )

    @api.model
    def _get_inventory_fields_create(self):
        return ['product_id', 'customer_po', 'owner_id','dc_date','dc_number','is_verified','partner_id','plant','inward_date','customer_state'] + self._get_inventory_fields_write()

    @api.model
    def barcode_search(self, barcode):
        quant = self.search([('lot_id.name', '=', barcode),('inventory_quantity_auto_apply', '>',0)], limit=1)

        if quant:
            quant.is_verified = True
            return {'id': quant.id}
        return True  # ✅ This should be TRUE for "not found"

    # def _check_stock_avail(self,barcode):
    #     stock = self.env['stock.quant'].search([('lot_id.name', '=', barcode)], limit=1)
    #     print(stock,barcode,'its jmdhdhkdkd')
    #     if not stock:
    #         return True  # frontend will show "Product Not Found"
    #
    #     if stock:
    #         stock.is_verified = True
    #
    #         return {
    #             'effect': {
    #                 'title': '🎉 Congratulations!',
    #                 'message': 'Stock is available and verrified succesfully.',
    #                 'type': 'rainbow_man',
    #                 'sticky': True,
    #             }
    #         }




class RepairOrder(models.Model):
    _inherit = 'repair.order'

    @api.model
    def barcode_search(self, last_code, order_id=None):
        """Purchase Order line is created and product is added by checking
        the barcode. args contains the barcode of product and purchase order
        id"""
        product = self.env['stock.quant'].search([('lot_id.name', '=',
                                                       last_code)])
        if product:
            return True
        else:
            self.create({
                'product_id': product.product_id.id,
                'lot_id': product.lot_id.id,
            })

            return {
                'type': 'ir.actions.client',
                'tag': 'reload',
            }

    @api.model
    def create_repair_order_from_barcode(self, barcode):
        """Find product by barcode and create a new repair order with it"""
        product = self.env['product.product'].search([('barcode', '=', barcode)], limit=1)
        if not product:
            return True  # frontend will show "Product Not Found"

        partner = self.env['res.partner'].search([], limit=1)  # dummy partner

        self.create({
            'product_id': product.id,
            'invoice_method': 'none',
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }


class PurchaseOrder(models.Model):
    """Module is inherited and function is created to create a purchase
    order line with the scanned barcode of product"""
    _inherit = 'purchase.order'

    @api.model
    def barcode_search(self, last_code, order_id):
        """Purchase Order line is created and product is added by checking
        the barcode. args contains the barcode of product and purchase order
        id"""
        product = self.env['product.product'].search([('barcode', '=',
                                                       last_code)])
        if not product:
            return True
        else:
            purchase_order = self.browse(order_id)
            if purchase_order.order_line:
                for rec in purchase_order.order_line:
                    if rec.product_id == product:
                        rec.product_qty += 1
                        return {
                            'type': 'ir.actions.client',
                            'tag': 'reload',
                        }
            purchase_order.order_line.create({
                'order_id': purchase_order.id,
                'product_id': product.id,
                'product_uom_qty': 1
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'reload',
            }



class VerifyBarcodeWizard(models.TransientModel):
    _name = 'verify.barcode.wizard'
    _description = 'Verify Barcode Wizard'

    barcode = fields.Char(string="Barcode")

    def verify_barcode_action(self):
        self.ensure_one()
        barcode = self.barcode

        quant = self.env['stock.quant'].search([
            ('lot_id.name', '=', barcode),
            ('inventory_quantity_auto_apply', '=', 1),
            ('location_id.usage', '=', 'internal')
        ], limit=1)

        if quant:
            quant.is_verified = True
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Verified',
                    'message': f'Barcode "{barcode}" verified successfully.',
                    'type': 'success',
                    'sticky': False,
                    'next': {
                        'type': 'ir.actions.client',
                        'tag': 'soft_reload',
                    },
                }
            }

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Not Found',
                'message': f'No matching quant found for barcode "{barcode}".',
                'type': 'danger',
                'sticky': False,
            }
        }




