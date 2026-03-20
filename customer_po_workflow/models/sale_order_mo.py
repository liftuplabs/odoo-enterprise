from odoo import models, api,fields

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    invoice_line_ids_custom = fields.Many2many(
        comodel_name='account.move',
        string="Invoices",
        copy=False)

    def action_view_custom_invoices(self):
        self.ensure_one()
        return {
            'name': 'Invoices',
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.invoice_line_ids_custom.ids)],
            'context': dict(self.env.context),
        }

    def action_create_mo_and_invoice(self):
        mo_obj = self.env['mrp.production']
        invoice_obj = self.env['account.move']
        for so in self:
            customer_po = self.env['customer.po'].search([('sale_order_id', '=', so.id)], limit=1)
            production_order_obj = self.env['production.order']
            # Create Manufacturing Orders
            mo_ids = []
            for line in so.order_line:
                if line.product_id:
                    mo = mo_obj.create({
                        'product_id': line.product_id.id,
                        'product_qty': line.product_uom_qty,
                        'product_uom_id': line.product_uom.id,
                        'origin': so.name,
                        'bom_id': line.product_id.bom_ids and line.product_id.bom_ids[0].id,
                        'customer_po_id': customer_po.id if customer_po else False
                    })
                    # Mark MO as done immediately (optional for testing)
                    mo.button_mark_done()
                    mo_ids.append(mo.id)
            if mo_ids:
                production_order_obj.create({'mrp_ids': [(6, 0, mo_ids)],
                                             'shift_no':'shift_1'})

            # Create Invoice
            invoice_vals = {
                'move_type': 'out_invoice',
                'partner_id': so.partner_id.id,
                'invoice_origin': so.name,
                'invoice_line_ids': [(0,0,{
                    'product_id': line.product_id.id,
                    'quantity': line.product_uom_qty,
                    'price_unit': line.price_unit,
                    'account_id': line.product_id.categ_id.property_account_income_categ_id.id,
                }) for line in so.order_line]
            }
            invoice = invoice_obj.create(invoice_vals)
            so.write({'invoice_line_ids_custom': [(4, invoice.id)]})



class StockQuantInherit(models.Model):
    _inherit = 'stock.quant'

    customer_po = fields.Char(string="Customer PO")

    @api.model
    def _get_inventory_fields_create(self):
        return ['product_id', 'customer_po', 'owner_id','dc_date','dc_number','is_verified','partner_id','plant','inward_date','customer_state','customer_po'] + self._get_inventory_fields_write()
