from odoo import fields, models

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    customer_po_no = fields.Char("Customer PO#")
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

    custom_layout_size = fields.Selection(
        selection=[
            ('auto', 'Auto (Based on Lines)'),
            ('compact', 'Compact'),
            ('dense', 'Dense (30+ Lines)')
        ],
        string='Layout Size',
        default='auto',
        help='Controls the padding and line height of the printed document.'
    )

    custom_font_size = fields.Selection(
        selection=[
            ('small', 'Small (10px)'),
            ('standard', 'Standard (12px)'),
            ('medium', 'Medium (13px)'),
            ('large', 'Large (14px)'),
            ('xlarge', 'Extra Large (15px)')
        ],
        string='Base Font Size',
        default='large'
    )

    # 2. Table Configurations
    custom_table_style = fields.Selection(
        selection=[
            ('bordered', 'Fully Bordered'),
            ('minimal', 'Minimal (Horizontal Lines Only)'),
            ('striped', 'Striped Rows')
        ],
        string='Table Style',
        default='striped'
    )

    custom_bold_table_data = fields.Boolean(
        string='Bold Table Data',
        default=False,
        help='Check this to make all text within the product lines bold.'
    )

    def _l10n_in_get_hsn_summary_table(self):
        self.ensure_one()
        if self.company_id.country_id.code != 'IN':
            return None

        hsn_data = {}
        has_gst = False
        has_igst = False

        for line in self.order_line.filtered(lambda l: not l.display_type and l.product_id):
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

            # Use taxes_id for Purchase
            taxes = line.taxes_id.compute_all(
                line.price_unit, self.currency_id, line.product_qty,
                product=line.product_id, partner=self.partner_id)

            for tax_val in taxes['taxes']:
                tax = self.env['account.tax'].browse(tax_val['id'])
                if any(tag.name == '+CGST' for tag in tax.repartition_line_ids.tag_ids):
                    res['tax_amount_cgst'] += tax_val['amount']
                    res['rate'] = tax.amount * 2
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