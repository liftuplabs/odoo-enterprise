from odoo import api, Command, fields, models, modules, tools, _
from odoo.exceptions import UserError, ValidationError

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    is_repair_parts = fields.Boolean("Is Reapir Parts?")
    lot_ids = fields.Many2many('stock.lot', string='Serial No', readonly=True)
    lot_id = fields.Many2one('stock.lot', readonly=True)
    repair_id = fields.Many2one('repair.order', 'Reapir Order', readonly=True)

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    used_qty = fields.Float("Used QTY", readonly=True)

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    is_used = fields.Boolean("Is Used?", compute='_compute_is_used', store=True)

    @api.depends('order_line.used_qty')
    def _compute_is_used(self):
        for order in self:
            order.is_used = all(line.used_qty == line.product_qty for line in order.order_line)


class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    # purchase_order_ids = fields.Many2many('purchase.order', string='Related Purchase Orders',
    #     domain="[('partner_id', '=', partner_id), ('is_used', '=', False)]")
    dispatch_doc_no = fields.Char(string='Dispatch Doc No.')
    dispatch_through = fields.Char(string='Dispatched Through')
    destination = fields.Char(string='Destination')
    terms_of_delivery = fields.Text(string='Terms of Delivery')

    supplier_reference = fields.Char(string='Supplier Reference')
    other_reference = fields.Char(string='Other Reference')

    delivery_note = fields.Char(string='Delivery Note')
    delivery_note_date = fields.Date(string='Delivery Note Date')

    mode_of_payment = fields.Char(string='Mode/Terms of Payment')

    buyers_order_no = fields.Char(string="Buyer's Order No.")
    buyers_order_date = fields.Date(string="Buyer's Order Date")

    # def _check_po_quantity_match(self):
    #     for order in self:
    #         if not order.purchase_order_ids:
    #             continue
    #
    #         warnings = []
    #
    #         for so_line in order.order_line.filtered(lambda l: l.is_repair_parts and l.product_id.type != 'service'):
    #             purchase_lines = self.env['purchase.order.line'].search([
    #                 ('product_id', '=', so_line.product_id.id),
    #                 ('order_id', 'in', order.purchase_order_ids.ids),
    #             ])
    #
    #             if not purchase_lines:
    #                 warnings.append(_("Product %s not found in Purchase Order.") % so_line.product_id.display_name)
    #                 continue
    #
    #             total_qty = sum(purchase_lines.mapped('product_qty'))
    #             total_used_qty = sum(purchase_lines.mapped('used_qty'))
    #             total_available_qty = total_qty - total_used_qty
    #
    #             if total_available_qty < so_line.product_uom_qty:
    #                 warnings.append(_(
    #                     "Product %s has insufficient quantity on Purchase Order "
    #                     "(SO Qty: %s, PO Qty: %s)."
    #                 ) % (so_line.product_id.display_name,
    #                      so_line.product_uom_qty,
    #                      total_available_qty))
    #                 continue
    #
    #             # Consume PO lines quantity according to SO qty
    #             remaining_to_use = so_line.product_uom_qty
    #             for po_line in purchase_lines.sorted(lambda l: l.id):  # deterministic order
    #                 if remaining_to_use <= 0:
    #                     break
    #
    #                 available_in_po = po_line.product_qty - (po_line.used_qty or 0)
    #                 if available_in_po <= 0:
    #                     continue
    #
    #                 use_qty = min(available_in_po, remaining_to_use)
    #                 po_line.used_qty = (po_line.used_qty or 0) + use_qty
    #                 remaining_to_use -= use_qty
    #
    #         if warnings:
    #             raise ValidationError("\n".join(warnings))

    def _action_confirm(self):
        # if not self.purchase_order_ids and self.repair_count > 0:
        #     raise UserError(_("Please select a Purchase Order for repair parts before confirming the Sale Order."))
        #
        # self._check_po_quantity_match()

        # 1. Execute standard confirmation (creates pickings and moves)
        res = super(SaleOrder, self)._action_confirm()

        # 2. Process the generated pickings
        pickings = self.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel'))
        for picking in pickings:
            for move in picking.move_ids:
                sale_line = move.sale_line_id

                if not sale_line:
                    continue

                if sale_line.is_repair_parts:
                    move.unlink()
                    continue

                # Assign Lots to the Stock Move and Move Lines
                if sale_line.lot_ids:
                    # Assign to the move itself
                    move.lot_ids = [Command.set(sale_line.lot_ids.ids)]

                    # Update or Create Move Lines (this handles the actual reservation)
                    # We clear existing move lines to ensure we use only the ones from the SO
                    move.move_line_ids.unlink()

                    for lot in sale_line.lot_ids:
                        self.env['stock.move.line'].create({
                            'move_id': move.id,
                            'product_id': move.product_id.id,
                            'lot_id': lot.id,
                            'quantity': 1,  # Serial numbers always have qty 1
                            'picking_id': picking.id,
                            'location_id': move.location_id.id,
                            'location_dest_id': move.location_dest_id.id,
                        })
        return res

    # def action_cancel(self):
    #     """ Override to reverse PO quantity usage before the order is cancelled. """
    #     for order in self:
    #         # We only reverse if the order was already confirmed (state 'sale' or 'done')
    #         # because draft orders haven't updated the PO quantities yet.
    #         if order.state in ('sale', 'done'):
    #             order._reverse_po_quantity_usage()
    #     return super(SaleOrder, self).action_cancel()

    # def _reverse_po_quantity_usage(self):
    #     for order in self:
    #         # if not order.purchase_order_ids:
    #         #     continue
    #
    #         for so_line in order.order_line.filtered(lambda l: l.is_repair_parts and l.product_id.type != 'service'):
    #             # Search for the same PO lines used during confirmation
    #             # We sort by 'id desc' to reverse the allocation in LIFO order
    #             purchase_lines = self.env['purchase.order.line'].search([
    #                 ('product_id', '=', so_line.product_id.id),
    #                 ('order_id', 'in', order.purchase_order_ids.ids),
    #                 ('used_qty', '>', 0),
    #             ], order='id desc')
    #
    #             qty_to_release = so_line.product_uom_qty
    #
    #             for po_line in purchase_lines:
    #                 if qty_to_release <= 0:
    #                     break
    #
    #                 # Determine how much this specific line can "give back"
    #                 can_release = min(po_line.used_qty, qty_to_release)
    #
    #                 po_line.used_qty -= can_release
    #                 qty_to_release -= can_release


    def _l10n_in_get_hsn_summary_table(self):
        self.ensure_one()
        # Only process if the company is in India
        if self.company_id.country_id.code != 'IN':
            return None

        hsn_data = {}
        has_gst = False
        has_igst = False

        for line in self.order_line.filtered(lambda l: not l.display_type and l.product_id):
            # Get HSN from product or fallback
            hsn_code = line.product_id.l10n_in_hsn_code or 'N/A'

            if hsn_code not in hsn_data:
                hsn_data[hsn_code] = {
                    'l10n_in_hsn_code': hsn_code,
                    'amount_untaxed': 0.0,
                    'tax_amount_cgst': 0.0,
                    'tax_amount_sgst': 0.0,
                    'tax_amount_igst': 0.0,
                    'rate': 0.0,
                }

            res = hsn_data[hsn_code]
            res['amount_untaxed'] += line.price_subtotal

            # Compute taxes for the current line
            taxes = line.tax_id.compute_all(
                line.price_unit,
                self.currency_id,
                line.product_uom_qty,
                product=line.product_id,
                partner=self.partner_shipping_id or self.partner_id
            )

            for tax_val in taxes['taxes']:
                tax = self.env['account.tax'].browse(tax_val['id'])
                # Distribute tax amounts based on Indian Tax tags
                if any(tag.name == '+CGST' for tag in tax.repartition_line_ids.tag_ids):
                    res['tax_amount_cgst'] += tax_val['amount']
                    res['rate'] = tax.amount * 2  # Standard GST Rate
                    has_gst = True
                elif any(tag.name == '+SGST' for tag in tax.repartition_line_ids.tag_ids):
                    res['tax_amount_sgst'] += tax_val['amount']
                    has_gst = True
                elif any(tag.name == '+IGST' for tag in tax.repartition_line_ids.tag_ids):
                    res['tax_amount_igst'] += tax_val['amount']
                    res['rate'] = tax.amount
                    has_igst = True

        return {
            'items': sorted(hsn_data.values(), key=lambda x: x['l10n_in_hsn_code']),
            'has_gst': has_gst,
            'has_igst': has_igst,
        }