from odoo import models, fields
import pandas as pd
import base64
import io
from datetime import datetime
from odoo.exceptions import UserError
import logging
import re
_logger = logging.getLogger(__name__)

class TallySalesImportWizard(models.TransientModel):
    _name = 'tally.sales.import.wizard'
    _description = 'Tally Sales Import Wizard'

    excel_file = fields.Binary(string='Excel File', required=True)
    file_name = fields.Char(string='File Name')
    import_type = fields.Selection([
        ('sales', 'Sales'),
        ('purchase', 'Purchase'),
        ('receipt', 'Receipt'),
        ('payment', 'Payment'),
        ('journal', 'Journal'),
        ('contra', 'Contra'),
        ('credit_note', 'Credit Note'),
        ('debit_note', 'Debit Note'),
    ], string='Import Type', required=True, default='sales')

    def action_import(self):
        if not self.excel_file:
            return

        # Decode and read the Excel file
        file_content = base64.b64decode(self.excel_file)
        file_io = io.BytesIO(file_content)
        try:
            df = pd.read_excel(file_io, sheet_name=0, header=None, engine='openpyxl')
        except Exception:
            file_io.seek(0)
            try:
                df = pd.read_excel(file_io, sheet_name=0, header=None, engine='xlrd')
            except Exception as e:
                raise UserError(f"Failed to read Excel file: {str(e)}")

        if self.import_type == 'sales':
            self._import_sales(df)
        elif self.import_type == 'purchase':
            self._import_purchase(df)
        elif self.import_type == 'receipt':
            self._import_receipt(df)
        elif self.import_type == 'payment':
            self._import_payment(df)
        elif self.import_type == 'journal':
            self._import_journal(df)
        elif self.import_type == 'contra':
            self._import_contra(df)
        elif self.import_type == 'credit_note':
            self._import_credit_note(df)
        elif self.import_type == 'debit_note':
            self._import_debit_note(df)

        return {'type': 'ir.actions.act_window_close'}

    def _import_sales(self, df):
        # Detect company based on header
        company = 'lasertech'
        for row_idx in range(10):
            row = df.iloc[row_idx]
            if pd.notna(row.get(0)) and 'ADROIT ENGINEERING' in str(row[0]).strip():
                company = 'engineering'
                break
            elif pd.notna(row.get(0)) and 'ADROITRE ENERGY LLP' in str(row[0]).strip():
                company = 'energyllp'
                break

        invoices = []
        current_invoice = None

        if company == 'engineering':
            # New logic for ADROIT ENGINEERING
            # Get taxes
            # igst_18 = self.env['account.tax'].search(
            #     [('name', '=ilike', 'IGST @ 18%'), ('amount', '=', 18.0), ('type_tax_use', '=', 'sale')], limit=1)
            # cgst_9 = self.env['account.tax'].search(
            #     [('name', '=ilike', 'CGST @ 9%'), ('amount', '=', 9.0), ('type_tax_use', '=', 'sale')], limit=1)
            # sgst_9 = self.env['account.tax'].search(
            #     [('name', '=ilike', 'SGST @ 9%'), ('amount', '=', 9.0), ('type_tax_use', '=', 'sale')], limit=1)
            # if not igst_18 or not cgst_9 or not sgst_9:
            #     raise UserError("Required taxes (IGST 18%, CGST 9%, SGST 9%) not found in the system.")

            for i in range(len(df)):
                row = df.iloc[i].dropna(how='all')
                if row.empty:
                    continue

                # Detect new invoice: date in col 0, vch type containing 'Sales' in col 6, vch no in col 7
                if pd.notna(row.get(0)) and (
                        isinstance(row.get(0), datetime) or isinstance(row.get(0), (int, float))) and pd.notna(
                        row.get(6)) and 'Sales' in str(row.get(6)).strip() and pd.notna(row.get(7)):
                    if current_invoice:
                        invoices.append(current_invoice)

                    inv_date = row[0]
                    if not isinstance(inv_date, datetime):
                        try:
                            inv_date = datetime(1899, 12, 30) + timedelta(days=int(inv_date))
                        except:
                            raise ValueError(f"Invalid date format at row {i + 1}")

                    customer = str(row[1]).strip() if pd.notna(row[1]) else ''
                    if not customer:
                        raise ValueError(f"Customer name missing for invoice ref {row[7]} at row {i + 1}")

                    current_invoice = {
                        'date': inv_date.date(),
                        'customer': customer,
                        'ref': str(row[7]).strip(),
                        'lines': [],
                    }

                elif current_invoice:
                    # Product lines: name in col 1, amount in col 4, optional qty in 2, price in 3
                    if pd.notna(row.get(1)) and pd.notna(row.get(4)) and '@' not in str(row[1]):
                        try:
                            product_name = str(row[1]).strip()
                            qty = float(row.get(2, 1.0)) if pd.notna(row.get(2)) else 1.0
                            if pd.notna(row.get(3)):
                                price = float(row[3])
                            else:
                                price = float(row[4]) / qty
                            current_invoice['lines'].append({
                                'name': product_name,
                                'quantity': qty,
                                'price_unit': price
                            })
                        except ValueError:
                            pass  # Skip invalid numeric conversions

            # Append the last invoice
            if current_invoice:
                invoices.append(current_invoice)

            # Now create Odoo records for each parsed invoice
            for inv_data in invoices:
                # Partner (customer) - trim state code if present
                # customer_name = inv_data['customer'].split('_')[0].strip()
                customer_name = inv_data['customer'].split('(')[0].strip()
                partner = self.env['res.partner'].search([('name', '=', customer_name)], limit=1)
                if not partner:
                    raise ValueError(
                        f"Customer '{customer_name}' not found in the system. Please create it before importing.")

                # Determine tax based on customer state code
                # tax_ids = [igst_18.id]
                # if '_Mh' in inv_data['customer']:
                #     tax_ids = [cgst_9.id, sgst_9.id]

                # Invoice lines
                invoice_lines = []
                for line in inv_data['lines']:
                    product = self.env['product.product'].search([('name', '=', line['name'])], limit=1)
                    if not product:
                        raise ValueError(
                            f"Product '{line['name']}' not found in the system. Please create it before importing.")

                    invoice_lines.append((0, 0, {
                        'product_id': product.id,
                        'quantity': line['quantity'],
                        'price_unit': line['price_unit'],
                        # 'tax_ids': [(6, 0, tax_ids)],
                    }))

                # Create the invoice
                self.env['account.move'].create({
                    'partner_id': partner.id,
                    'move_type': 'out_invoice',
                    'ref': inv_data['ref'],
                    'invoice_date': inv_data['date'],
                    'date': inv_data['date'],
                    'invoice_line_ids': invoice_lines,
                })
                _logger.info("---------- Created invoice for %s, ref %s ----------------------", customer_name,
                             inv_data['ref'])
        elif company == 'energyllp':
            for i in range(len(df)):
                row = df.iloc[i].dropna(how='all')
                if row.empty:
                    continue

                # Detect new invoice
                if pd.notna(row.get(0)) and (
                        isinstance(row.get(0), datetime) or isinstance(row.get(0), (int, float))) and \
                        pd.notna(row.get(6)) and 'Sales' in str(row.get(6)).strip() and pd.notna(row.get(7)):

                    if current_invoice:
                        invoices.append(current_invoice)

                    inv_date = row[0]
                    if not isinstance(inv_date, datetime):
                        try:
                            inv_date = datetime(1899, 12, 30) + timedelta(days=int(inv_date))
                        except:
                            continue

                    customer = str(row.get(1, '')).strip().replace('_x000D_', ' ').strip()
                    if not customer:
                        customer = 'Unknown Customer'

                    current_invoice = {
                        'date': inv_date.date(),
                        'customer': customer,
                        'ref': str(row.get(7)).strip(),
                        'lines': [],
                    }

                elif current_invoice:
                    # Product lines
                    if pd.notna(row.get(1)) and pd.notna(row.get(4)) and '@' not in str(row.get(1, '')):
                        try:
                            product_name = str(row.get(1)).strip().replace('_x000D_', ' ').strip()
                            qty = float(row.get(2, 1.0)) if pd.notna(row.get(2)) else 1.0
                            if pd.notna(row.get(3)):
                                price = float(row.get(3))
                            else:
                                price = float(row.get(4)) / qty if qty != 0 else 0
                            current_invoice['lines'].append({
                                'name': product_name,
                                'quantity': qty,
                                'price_unit': price
                            })
                        except ValueError:
                            pass

                    # Special case for Metal Trolley (no rate)
                    elif pd.notna(row.get(1)) and 'Metal Trolley' in str(row.get(1)).upper() and pd.notna(row.get(2)):
                        try:
                            qty = float(row.get(2))
                            current_invoice['lines'].append({
                                'name': 'Metal Trolley',
                                'quantity': qty,
                                'price_unit': 0.0
                            })
                        except ValueError:
                            pass

            if current_invoice:
                invoices.append(current_invoice)

            # ====================== CREATE ODOO INVOICES ======================
            for inv_data in invoices:
                customer_name = inv_data['customer'].split('(')[0].strip()

                partner = self.env['res.partner'].search([('name', '=', customer_name)], limit=1)
                if not partner:
                    raise ValueError(f"Customer '{customer_name}' not found. Please create it before importing.")

                invoice_lines = []
                for line in inv_data['lines']:
                    product = self.env['product.product'].search([('name', '=', line['name'])], limit=1)
                    if not product:
                        raise ValueError(f"Product '{line['name']}' not found. Please create it before importing.")

                    invoice_lines.append((0, 0, {
                        'product_id': product.id,
                        'quantity': line['quantity'],
                        'price_unit': line['price_unit'],
                    }))

                self.env['account.move'].create({
                    'partner_id': partner.id,
                    'move_type': 'out_invoice',
                    'ref': inv_data['ref'],
                    'invoice_date': inv_data['date'],
                    'date': inv_data['date'],
                    'invoice_line_ids': invoice_lines,
                })
                _logger.info("---------- Created Sales Invoice for %s, ref %s ----------------------", customer_name,
                             inv_data['ref'])

            return True
        else:
            # Old logic for adroit lasertech
            for i in range(len(df)):
                row = df.iloc[i].dropna(how='all')  # Skip fully empty rows
                if row.empty:
                    continue

                # Detect new invoice: Check for 'Sales' in column 6 (0-based index 6) and voucher in column 7
                # if len(row) > 7 and str(row.get(6, '')).strip() == 'Sales' and pd.notna(row[7]):
                if pd.notna(row.get(0)) and isinstance(row.get(0), datetime) and pd.notna(row.get(6)) and str(
                        row.get(6)).strip() == 'Sales' and pd.notna(row.get(7)):
                    if current_invoice:
                        invoices.append(current_invoice)

                    inv_date = row[0].date()
                    # Extract customer name
                    customer = str(row[1]).strip() if pd.notna(row[1]) else ''
                    # if pd.notna(row[0]) and str(row[0]).isdigit():
                    #     customer = f"{row[0]} - {customer}".replace('-Debtors', '').strip()
                    if not customer:
                        raise ValueError(f"Customer name missing for invoice ref {row[7]} at row {i + 1}")

                    current_invoice = {
                        'date': inv_date,
                        'customer': customer,
                        'ref': str(row[7]).strip(),
                        'lines': [],
                    }

                elif current_invoice:
                    # Product lines with qty, rate, amount (columns 1,2,3,4)
                    if len(row) >= 4 and pd.notna(row.get(1)) and isinstance(row[1], str) and pd.notna(
                            row.get(2)) and pd.notna(row.get(3)) and pd.notna(row.get(4)):
                        try:
                            product_name = str(row[1]).strip()
                            qty = float(row[2])
                            price = float(row[3])
                            current_invoice['lines'].append({
                                'name': product_name,
                                'quantity': qty,
                                'price_unit': price
                            })
                        except ValueError:
                            pass  # Skip invalid numeric conversions

                    # Special case for 'METAL TROLLEY' (qty in col 2, no rate/amount)
                    elif len(row) >= 2 and 'METAL TROLLEY' in str(row.get(1, '')) and pd.notna(row[2]):
                        try:
                            qty = float(row[2])
                            current_invoice['lines'].append({
                                'name': 'METAL TROLLEY',
                                'quantity': qty,
                                'price_unit': 0.0
                            })
                        except ValueError:
                            pass

                    # Tax lines (amount in column 9, 0-based index 8)
                    if len(row) > 1 and pd.notna(row.get(1)):
                        desc = str(row[1]).strip()
                        if len(row) > 9 and pd.notna(row[9]):
                            try:
                                tax_amount = float(row[9])
                                if 'Output CGST @ 9%' in desc:
                                    # current_invoice['cgst'] = tax_amount
                                    pass
                                elif 'Output SGST @ 9%' in desc:
                                    # current_invoice['sgst'] = tax_amount
                                    pass
                            except ValueError:
                                pass

            # Append the last invoice
            if current_invoice:
                invoices.append(current_invoice)

            # Now create Odoo records for each parsed invoice
            for inv_data in invoices:
                # Partner (customer)
                partner = self.env['res.partner'].search([('name', '=', inv_data['customer'])], limit=1)
                if not partner:
                    raise ValueError(
                        f"Customer '{inv_data['customer']}' not found in the system. Please create it before importing.")

                # Invoice lines
                invoice_lines = []
                for line in inv_data['lines']:
                    product = self.env['product.product'].search([('name', '=', line['name'])], limit=1)
                    if not product:
                        raise ValueError(
                            f"Product '{line['name']}' not found in the system. Please create it before importing.")
                        # product = self.env['product.product'].create({
                        #     'name': line['name'],
                        #     'type': 'product',  # or 'service' if appropriate
                        #     'list_price': line['price_unit'],
                        # })

                    invoice_lines.append((0, 0, {
                        'product_id': product.id,
                        'quantity': line['quantity'],
                        'price_unit': line['price_unit'],
                        # 'tax_ids': [(6, 0, [cgst.id, sgst.id])],
                    }))

                # Create the invoice
                self.env['account.move'].create({
                    'partner_id': partner.id,
                    'move_type': 'out_invoice',
                    'ref': inv_data['ref'],
                    'invoice_date': inv_data['date'],
                    'date': inv_data['date'],
                    'invoice_line_ids': invoice_lines,
                })
                _logger.info("---------- Created invoice for %s, ref %s ----------------------", inv_data['customer'],
                             inv_data['ref'])

    def _import_purchase(self, df):
        # Detect company based on header
        company = 'lasertech'
        for row_idx in range(10):
            row = df.iloc[row_idx]
            if pd.notna(row.get(0)) and 'ADROIT ENGINEERING' in str(row[0]).strip():
                company = 'engineering'
                break
            elif pd.notna(row.get(0)) and 'ADROITRE ENERGY LLP' in str(row[0]).strip():
                company = 'energyllp'
                break

        bills = []
        current_bill = None
        if company == 'engineering':
            # New logic for ADROIT ENGINEERING
            current_tax_cat = None
            # tax_parsed = []

            for i in range(len(df)):
                row = df.iloc[i].dropna(how='all')
                if row.empty:
                    continue

                # Detect new bill
                if (pd.notna(row.get(0)) and (
                        isinstance(row.get(0), (float, int)) or isinstance(row.get(0), datetime))) and pd.notna(
                        row.get(1)) and pd.notna(row.get(6)) and 'Purchase' in str(row.get(6)).strip() and pd.notna(
                        row.get(7)) and pd.notna(row.get(9)):
                    if current_bill:
                        # current_bill['taxes'] = tax_parsed
                        bills.append(current_bill)

                    inv_date = row[0]
                    if not isinstance(inv_date, datetime):
                        try:
                            inv_date = datetime(1899, 12, 30) + timedelta(days=float(inv_date))
                        except:
                            continue

                    supplier = str(row[1]).strip()
                    current_bill = {
                        'date': inv_date.date(),
                        'supplier': supplier,
                        'vch_type': str(row[6]).strip(),
                        'vch_no': str(row[7]).strip(),
                        'ref': '',
                        'lines': [],
                        'taxes': [],  # list of (type, rate, amount)
                        'adjustments': [],
                        'currency': 'INR',
                        'invoice_currency_rate': False,
                        'exchange_rate_inr_per_eur': False,
                    }
                    current_tax_cat = None
                    # tax_parsed = []

                elif current_bill:
                    # Currency conversion line for imports
                    if current_bill['vch_type'] == 'Import Purchase' and pd.notna(row.get(1)) and str(
                            row.get(2)) == '@' and pd.notna(row.get(3)):
                        try:
                            euro_total = float(row[1])
                            exchange_rate_inr_per_eur = float(row[3])
                            inverse_rate = 1 / exchange_rate_inr_per_eur
                            current_bill['currency'] = 'EUR'
                            current_bill['invoice_currency_rate'] = inverse_rate
                            current_bill['exchange_rate_inr_per_eur'] = exchange_rate_inr_per_eur
                        except ValueError:
                            pass

                    # Ref
                    if pd.notna(row.get(1)) and ('New Ref' in str(row[1]) or 'Agst Ref' in str(row[1])) and pd.notna(row.get(2)):
                        current_bill['ref'] = str(row[2]).strip()

                    # Tax category
                    if pd.notna(row.get(1)) and '@' in str(row[1]) and 'Purchase' in row[1] and pd.notna(row.get(8)):
                        current_tax_cat = str(row[1]).strip()

                    # Item lines with qty, rate, amount
                    if pd.notna(row.get(1)) and pd.notna(row.get(2)) and pd.notna(row.get(3)) and pd.notna(row.get(4)):
                        try:
                            product_name = str(row[1]).strip()
                            qty = float(row[2])
                            price = float(row[3])
                            current_bill['lines'].append({
                                'name': product_name,
                                'quantity': qty,
                                'price_unit': price,
                                'tax_cat': current_tax_cat,
                            })
                        except ValueError:
                            pass

                    # Lines without qty/rate (freight, etc.)
                    elif pd.notna(row.get(1)) and not '@' in str(row[1]) and pd.notna(row.get(4)) and 'Ref' not in str(
                            row[1]):
                        try:
                            product_name = str(row[1]).strip()
                            qty = 1.0
                            amount_inr = float(row[4])
                            if current_bill['currency'] == 'EUR' and current_bill['exchange_rate_inr_per_eur']:
                                price = amount_inr / current_bill['exchange_rate_inr_per_eur']
                            else:
                                price = amount_inr
                            current_bill['lines'].append({
                                'name': product_name,
                                'quantity': qty,
                                'price_unit': price,
                                'tax_cat': current_tax_cat,
                            })
                        except ValueError:
                            pass

                    # Tax lines
                    # if pd.notna(row.get(1)) and 'Input' in str(row[1]) and '@' in str(row[1]) and pd.notna(row.get(8)):
                    #     desc = str(row[1]).strip()
                    #     amount = float(row[8])
                    #     match = re.search(r'@\s*(\d+\.?\d*)%', desc)
                    #     if match:
                    #         rate = float(match.group(1))
                    #         tax_type = 'IGST' if 'IGST' in desc else 'CGST' if 'CGST' in desc else 'SGST' if 'SGST' in desc else ''
                    #         if tax_type:
                    #             tax_parsed.append((tax_type, rate, amount))

                    # Round Off
                    if pd.notna(row.get(1)) and 'Round Off' in str(row[1]):
                        if pd.notna(row.get(8)):
                            amount = float(row[8])
                        elif pd.notna(row.get(9)):
                            amount = -float(row[9])
                        else:
                            amount = 0
                        current_bill['adjustments'].append({'name': 'Round Off (+/-)', 'amount': amount})

            if current_bill:
                # current_bill['taxes'] = tax_parsed
                bills.append(current_bill)

            # Create Odoo records
            for bill_data in bills:
                partner = self.env['res.partner'].search([('name', '=', bill_data['supplier'])], limit=1)
                if not partner:
                    raise ValueError(
                        f"Supplier '{bill_data['supplier']}' not found in the system. Please create it before importing.")

                # tax_ids = []
                # for tax_type, rate, _ in bill_data['taxes']:
                #     tax_name = f'Input {tax_type} @ {rate}%'
                #     tax = self.env['account.tax'].search(
                #         [('name', '=ilike', tax_name), ('amount', '=', rate), ('type_tax_use', '=', 'purchase')],
                #         limit=1)
                #     if not tax:
                #         raise UserError(f"Tax '{tax_name}' not found in the system.")
                #     tax_ids.append(tax.id)

                bill_lines = []
                for line in bill_data['lines']:
                    product = self.env['product.product'].search([('name', '=', line['name'])], limit=1)
                    if not product:
                        raise ValueError(
                            f"Product '{line['name']}' not found in the system. Please create it before importing.")

                    bill_lines.append((0, 0, {
                        'product_id': product.id,
                        'quantity': line['quantity'],
                        'price_unit': line['price_unit'],
                        # 'tax_ids': [(6, 0, tax_ids)] if tax_ids else False,
                    }))

                for adj in bill_data['adjustments']:
                    product = self.env['product.product'].search([('name', '=', adj['name'])], limit=1)
                    if not product:
                        product = self.env['product.product'].create({
                            'name': adj['name'],
                            'type': 'service',
                        })

                    bill_lines.append((0, 0, {
                        'product_id': product.id,
                        'quantity': 1.0,
                        'price_unit': adj['amount'],
                    }))

                currency_id = self.env.company.currency_id.id
                if bill_data['currency'] == 'EUR':
                    eur = self.env['res.currency'].search([('name', '=', 'EUR')], limit=1)
                    if not eur:
                        raise UserError("EUR currency not found in the system.")
                    currency_id = eur.id

                vals = {
                    'partner_id': partner.id,
                    'move_type': 'in_invoice',
                    'ref': bill_data['ref'] or bill_data['vch_no'],
                    'invoice_date': bill_data['date'],
                    'date': bill_data['date'],
                    'currency_id': currency_id,
                    'invoice_line_ids': bill_lines,
                }
                if bill_data['invoice_currency_rate']:
                    vals['invoice_currency_rate'] = bill_data['invoice_currency_rate']

                self.env['account.move'].create(vals)
                _logger.info("---------- Created bill for %s, vch_no %s ----------------------", bill_data['supplier'],
                             bill_data['vch_no'])
        elif company in ('energyllp'):
            # ====================== NEW LOGIC FOR ADROIT ENGINEERING + ADROITRE ENERGY LLP ======================
            current_tax_cat = None

            for i in range(len(df)):
                row = df.iloc[i].dropna(how='all')
                if row.empty:
                    continue

                # Detect new bill
                if pd.notna(row.get(0)) and (
                        isinstance(row.get(0), (float, int)) or isinstance(row.get(0), datetime)) and \
                        pd.notna(row.get(6)) and 'Purchase' in str(row.get(6)).strip() and pd.notna(row.get(7)):

                    if current_bill:
                        bills.append(current_bill)

                    inv_date = row[0]
                    if not isinstance(inv_date, datetime):
                        try:
                            inv_date = datetime(1899, 12, 30) + timedelta(days=float(inv_date))
                        except:
                            continue

                    supplier = str(row.get(1, '')).strip().replace('_x000D_', ' ').strip()
                    if not supplier:
                        supplier = 'Unknown Supplier'

                    current_bill = {
                        'date': inv_date.date(),
                        'supplier': supplier,
                        'vch_type': str(row.get(6)).strip(),
                        'vch_no': str(row.get(7)).strip(),
                        'ref': '',
                        'lines': [],
                        'adjustments': [],
                        'currency': 'INR',
                        'invoice_currency_rate': False,
                        'exchange_rate_inr_per_foreign': False,
                        'taxes': [],
                    }
                    current_tax_cat = None

                elif current_bill:
                    # Currency conversion line for imports (e.g. 73500,@,82.97)
                    if pd.notna(row.get(1)) and str(row.get(2)) == '@' and pd.notna(row.get(3)):
                        try:
                            foreign_total = float(row.get(1))
                            exchange_rate = float(row.get(3))
                            current_bill['currency'] = 'EUR' if any(
                                x in current_bill['supplier'].upper() for x in ['KEBA', 'STEMMANN']) else 'USD'
                            current_bill['invoice_currency_rate'] = 1 / exchange_rate
                            current_bill['exchange_rate_inr_per_foreign'] = exchange_rate
                        except ValueError:
                            pass

                    if pd.notna(row.get(1)) and pd.notna(row.get(8)):
                        if 'Input' not in str(row.get(1)):
                            expense_account = str(row.get(1)).strip()
                            current_bill['expense_account'] = expense_account

                    if str(row.get(1)).strip() == 'Input SGST 9%':
                        current_bill['taxes'].append('18% GST P')

                    # New Ref / Agst Ref
                    if pd.notna(row.get(1)) and (
                            'New Ref' in str(row.get(1)) or 'Agst Ref' in str(row.get(1))) and pd.notna(row.get(2)):
                        current_bill['ref'] = str(row.get(2)).strip()

                    # Tax category
                    if pd.notna(row.get(1)) and '@' in str(row.get(1)) and pd.notna(row.get(8)):
                        current_tax_cat = str(row.get(1)).strip()

                    # Product lines with qty, rate, amount
                    if pd.notna(row.get(1)) and pd.notna(row.get(4)) and '@' not in str(row.get(1)):
                        try:
                            product_name = str(row.get(1)).strip().replace('_x000D_', ' ').strip()
                            if product_name not in ['Agst Ref']:
                                qty = float(row.get(2, 1.0)) if pd.notna(row.get(2)) else 1.0
                                price = float(row.get(3)) if pd.notna(row.get(3)) else float(row.get(4)) / qty
                                current_bill['lines'].append({
                                    'name': product_name,
                                    'quantity': qty,
                                    'price_unit': price,
                                    'tax_cat': current_tax_cat,
                                })
                        except ValueError:
                            pass

                    # Lines without qty/rate (freight, labour, etc.)
                    elif pd.notna(row.get(1)) and pd.notna(row.get(4)) and 'Ref' not in str(row.get(1)):
                        try:
                            product_name = str(row.get(1)).strip().replace('_x000D_', ' ').strip()
                            if product_name not in ['Agst Ref']:
                                amount_inr = float(row.get(4))
                                if current_bill['currency'] != 'INR' and current_bill['exchange_rate_inr_per_foreign']:
                                    price = amount_inr / current_bill['exchange_rate_inr_per_foreign']
                                else:
                                    price = amount_inr
                                current_bill['lines'].append({
                                    'name': product_name,
                                    'quantity': 1.0,
                                    'price_unit': price,
                                    'tax_cat': current_tax_cat,
                                })
                        except ValueError:
                            pass

                    # Round Off / Adjustments
                    if pd.notna(row.get(1)) and 'Round Off' in str(row.get(1)):
                        try:
                            if pd.notna(row.get(8)):
                                amount = float(row.get(8))
                            elif pd.notna(row.get(9)):
                                amount = -float(row.get(9))
                            else:
                                amount = 0
                            current_bill['adjustments'].append({'name': 'Round Off (+/-)', 'amount': amount})
                        except ValueError:
                            pass

            if current_bill:
                bills.append(current_bill)

            # ====================== CREATE ODOO BILLS ======================

            for bill_data in bills:
                partner = self.env['res.partner'].search([('name', '=', bill_data['supplier'])], limit=1)
                if not partner:
                    raise ValueError(
                        f"Supplier '{bill_data['supplier']}' not found. Please create it before importing.")

                bill_lines = []
                for line in bill_data['lines']:
                    product = self.env['product.product'].search([('name', '=', line['name'])], limit=1)
                    if not product:
                        raise ValueError(f"Product '{line['name']}' not found. Please create it before importing.")
                    expense_account = self.env['account.account'].search([('name', '=', bill_data.get('expense_account', ''))], limit=1)
                    if not expense_account:
                        raise ValueError(f"----------- Expense account '{bill_data.get('expense_account', '')}' not found. Please create it before importing.")
                    tax_ids = []
                    if bill_data['taxes']:
                        for tax_name in bill_data['taxes']:
                            tax = self.env['account.tax'].search(
                                [('name', '=', tax_name), ('type_tax_use', '=', 'purchase')], limit=1)
                            if not tax:
                                raise UserError(f"Tax '{tax_name}' not found in the system.")
                            tax_ids.append(tax.id)
                    bill_lines.append((0, 0, {
                        'product_id': product.id,
                        'account_id': expense_account.id,
                        'quantity': line['quantity'],
                        'price_unit': line['price_unit'],
                        'tax_ids': [(6, 0, tax_ids)] if tax_ids else False,
                    }))

                for adj in bill_data['adjustments']:
                    product = self.env['product.product'].search([('name', '=', adj['name'])], limit=1)
                    if not product:
                        product = self.env['product.product'].create({
                            'name': adj['name'],
                            'type': 'service',
                        })
                    bill_lines.append((0, 0, {
                        'product_id': product.id,
                        'quantity': 1.0,
                        'price_unit': adj['amount'],
                    }))

                currency_id = self.env.company.currency_id.id
                if bill_data['currency'] != 'INR':
                    curr = self.env['res.currency'].search([('name', '=', bill_data['currency'])], limit=1)
                    if curr:
                        currency_id = curr.id

                vals = {
                    'partner_id': partner.id,
                    'move_type': 'in_invoice',
                    'ref': bill_data['ref'] or bill_data['vch_no'],
                    'invoice_date': bill_data['date'],
                    'date': bill_data['date'],
                    'currency_id': currency_id,
                    'invoice_line_ids': bill_lines,
                }
                if bill_data.get('invoice_currency_rate'):
                    vals['invoice_currency_rate'] = bill_data['invoice_currency_rate']

                self.env['account.move'].create(vals)
                _logger.info("---------- Created Purchase Bill for %s, vch_no %s ----------------------",
                             bill_data['supplier'], bill_data['vch_no'])

            return True
        else:
            # Old logic for adroit lasertech
            # Updated Purchase parsing logic
            # Handles 'Educational' in col0 (ignores as non-date), uses default_date since no dates present
            bills = []
            current_bill = None

            for i in range(len(df)):
                row = df.iloc[i]
                if row.dropna().empty:
                    continue

                # Detect new bill: col0 may be 'Educational' (ignore for date), col1=supplier, col6='Purchase', col8=debit (empty), col9=credit total
                if pd.notna(row.get(1)) and pd.notna(row.get(6)) and str(
                        row.get(6, '')).strip() == 'Purchase' and pd.notna(
                        row.get(9)):
                    if current_bill:
                        bills.append(current_bill)
                    inv_date = None
                    if pd.notna(row.get(0)) and isinstance(row[0], datetime):
                        inv_date = row[0].date()

                    supplier = str(row.get(1, 'Unknown Supplier')).strip()

                    current_bill = {
                        'date': inv_date,
                        'supplier': supplier,
                        'vch_no': str(row.get(7, 'Unknown')).strip(),
                        'ref': '',
                        'lines': [],
                        # 'taxes': [],
                        'adjustments': [],
                    }

                elif current_bill:
                    # New Ref: col1='New Ref', col2=ref_value
                    if pd.notna(row.get(1)) and str(row.get(1, '')).strip() == 'New Ref' and pd.notna(row.get(2)):
                        current_bill['ref'] = str(row[2]).strip()

                    # Main purchase line: 'Job Work Charges Paid' in col1, amount in col8
                    if pd.notna(row.get(1)) and 'Job Work Charges Paid' in str(row.get(1, '')) and pd.notna(row.get(8)):
                        try:
                            amount = float(row[8])
                            current_bill['lines'].append({
                                'name': 'Job Work Charges Paid',
                                'quantity': 1.0,
                                'price_unit': amount
                            })
                        except ValueError:
                            pass

                    # Tax lines: 'Input CGST/SGST @ X%' in col1, amount in col7 or col8 (debit)
                    # if pd.notna(row.get(1)) and 'Input' in str(row.get(1, '')) and '@' in str(row.get(1, '')) and (
                    #         pd.notna(row.get(7)) or pd.notna(row.get(8))):
                    #     desc = str(row[1]).strip()
                    #     amount_col = row.get(8) if pd.notna(row.get(8)) else row.get(7)
                    #     if pd.notna(amount_col):
                    #         match = re.search(r'@\s*(\d+\.?\d*)%', desc)
                    #         if match:
                    #             rate = float(match.group(1))
                    #             try:
                    #                 amount = float(amount_col)
                    #                 tax_type = 'CGST' if 'CGST' in desc else 'SGST' if 'SGST' in desc else ''
                    #                 if tax_type:
                    #                     current_bill['taxes'].append((tax_type, rate, amount))
                    #             except ValueError:
                    #                 pass

                    # Adjustments: TDS, Round Off, Discount in col1, amount in col9 (credit, make negative)
                    if pd.notna(row.get(1)) and any(
                            keyword in str(row.get(1, '')) for keyword in ['Round Off', 'Discount']):
                        desc = str(row[1]).strip()
                        if pd.notna(row.get(8)):
                            try:
                                amount = float(row[8])  # Debit: positive
                                current_bill['adjustments'].append({
                                    'name': desc,
                                    'quantity': 1.0,
                                    'price_unit': amount
                                })
                            except ValueError:
                                pass
                        elif pd.notna(row.get(9)):
                            try:
                                amount = -float(row[9])  # Credit: negative
                                current_bill['adjustments'].append({
                                    'name': desc,
                                    'quantity': 1.0,
                                    'price_unit': amount
                                })
                            except ValueError:
                                pass

            if current_bill:
                bills.append(current_bill)
            # Create purchase bills
            for bill_data in bills:
                partner = self.env['res.partner'].search([('name', '=', bill_data['supplier'])], limit=1)
                if not partner:
                    raise ValueError(
                        f"Supplier '{bill_data['supplier']}' not found in the system. Please create it before importing.")
                    # partner = self.env['res.partner'].create({
                    #     'name': bill_data['supplier'],
                    #     'company_type': 'company',
                    #     'supplier_rank': 1,
                    # })

                # tax_ids = []
                # for tax_type, rate, _ in bill_data['taxes']:
                #     tax_name = f'Input {tax_type} @{rate}%'
                #     tax = self.env['account.tax'].search([
                #         ('name', '=', tax_name), ('amount', '=', rate), ('type_tax_use', '=', 'purchase')
                #     ], limit=1)
                #     if not tax:
                #         tax = self.env['account.tax'].create({
                #             'name': tax_name, 'amount': rate, 'type_tax_use': 'purchase', 'amount_type': 'percent',
                #         })
                #     tax_ids.append(tax.id)

                bill_lines = []
                for line in bill_data['lines']:
                    product = self.env['product.product'].search([('name', '=', line['name'])], limit=1)
                    if not product:
                        raise ValueError(
                            f"Product '{line['name']}' not found in the system. Please create it before importing.")
                        # product = self.env['product.product'].create({
                        #     'name': line['name'], 'type': 'service', 'purchase_price': line['price_unit'],
                        # })
                    bill_lines.append((0, 0, {
                        'product_id': product.id,
                        'quantity': line['quantity'],
                        'price_unit': line['price_unit'],
                        # 'tax_ids': [(6, 0, tax_ids)] if tax_ids else False,
                    }))

                for adj in bill_data['adjustments']:
                    product = self.env['product.product'].search([('name', '=', adj['name'])], limit=1)
                    if not product:
                        raise ValueError(
                            f"Product '{adj['name']}' not found in the system. Please create it before importing.")
                        # product = self.env['product.product'].create({
                        #     'name': adj['name'], 'type': 'service', 'purchase_price': adj['price_unit'],
                        # })
                    bill_lines.append((0, 0, {
                        'product_id': product.id,
                        'quantity': adj['quantity'],
                        'price_unit': adj['price_unit'],
                    }))

                self.env['account.move'].create({
                    'partner_id': partner.id,
                    'move_type': 'in_invoice',
                    'ref': bill_data['ref'] or bill_data['vch_no'],
                    'invoice_date': bill_data['date'],
                    'date': bill_data['date'],
                    'invoice_line_ids': bill_lines,
                })
                _logger.info("---------- Created bill for %s, vch_no %s ----------------------", bill_data['supplier'],
                             bill_data['vch_no'])

    # def _import_receipt(self, df):
    #     receipts = []
    #     current_receipt = None
    #
    #     for i in range(len(df)):
    #         row = df.iloc[i]
    #         if row.dropna().empty:
    #             continue
    #
    #         # Detect new receipt voucher
    #         if pd.notna(row.get(6)) and str(row.get(6, '')).strip() == 'Receipt' and pd.notna(row.get(9)):
    #             if current_receipt:
    #                 receipts.append(current_receipt)
    #
    #             inv_date = row[0].date() if pd.notna(row[0]) and isinstance(row[0], datetime) else None
    #
    #             partner_name = str(row.get(1, 'Unknown Partner')).strip()
    #             if pd.notna(row.get(0)) and str(row[0]).isdigit():
    #                 partner_name = f"{row[0]} - {partner_name}".strip()
    #
    #             current_receipt = {
    #                 'date': inv_date,
    #                 'partner': partner_name,
    #                 'vch_no': str(row.get(7, 'Unknown')).strip(),
    #                 'memo_lines': [],
    #                 'amount': float(row.get(9, 0)),
    #                 'payment_method': '',
    #                 'invoice_refs': [],  # This will now be filled properly
    #                 'tds_amount': 0.0,
    #             }
    #
    #         elif current_receipt:
    #             desc = str(row.get(1, '')).strip()
    #
    #             # === IMPROVED: Detect Agst Ref more flexibly ===
    #             if 'Agst Ref' in desc or (pd.notna(row.get(2)) and str(row.get(2)).startswith('AL')):
    #                 # Try column 2 for ref, column 4 or nearby for amount
    #                 ref_col = 2 if pd.notna(row.get(2)) else 1
    #                 amt_col_candidates = [4, 3, 5]  # Try multiple possible columns
    #                 ref = str(row.get(ref_col, '')).strip()
    #
    #                 alloc_amount = 0.0
    #                 for col in amt_col_candidates:
    #                     if pd.notna(row.get(col)) and isinstance(row[col], (int, float)):
    #                         try:
    #                             alloc_amount = float(row[col])
    #                             break
    #                         except ValueError:
    #                             pass
    #
    #                 if ref.startswith('AL') and alloc_amount > 0:
    #                     current_receipt['invoice_refs'].append((ref, alloc_amount))
    #                     current_receipt['memo_lines'].append(f"Agst Ref: {ref} ({alloc_amount:.2f})")
    #
    #             # Payment method / Bank
    #             if pd.notna(row.get(1)) and any(kw in str(row[1]).upper() for kw in ['CASH', 'BANK', 'SARASWAT']):
    #                 current_receipt['payment_method'] = str(row[1]).strip()
    #                 current_receipt['memo_lines'].append(f"Paid via: {current_receipt['payment_method']}")
    #
    #             # Transaction type + reference (NEFT/RTGS/IMPS)
    #             if pd.notna(row.get(1)) and any(
    #                     kw in str(row[1]).upper() for kw in ['NEFT', 'RTGS', 'IMPS', 'CHEQUE', 'DD']):
    #                 ref_text = str(row[1]).strip()
    #                 if pd.notna(row.get(2)):
    #                     ref_text += f" {str(row[2]).strip()}"
    #                 if pd.notna(row.get(4)):
    #                     ref_text += f" {str(row[4]).strip()}"
    #                 current_receipt['memo_lines'].append(f"Transaction: {ref_text}")
    #
    #             # Narrative / date + amount lines
    #             if pd.notna(row.get(1)) and (
    #                     any(kw in str(row[1]).upper() for kw in ['NEFT', 'RTGS', 'IMPS', 'TRANSFER', 'OPENING'])
    #                     or re.search(r'\d{2}-\d{2}-\d{4}', str(row[1]))  # date pattern
    #             ):
    #                 narrative = str(row[1]).strip()
    #                 for col in [2, 3, 4]:
    #                     if pd.notna(row.get(col)):
    #                         narrative += f" {str(row[col]).strip()}"
    #                 current_receipt['memo_lines'].append(f"Note: {narrative}")
    #
    #             # TDS
    #             if 'TDS Receivable' in desc and pd.notna(row.get(8)):
    #                 try:
    #                     tds = float(row[8])
    #                     current_receipt['tds_amount'] = tds
    #                     current_receipt['memo_lines'].append(f"TDS Receivable: {tds:.2f}")
    #                 except ValueError:
    #                     pass
    #
    #     if current_receipt:
    #         receipts.append(current_receipt)
    #
    #     # Create payments
    #     for receipt_data in receipts:
    #         account = self.env['account.account'].search([('name', '=', receipt_data['partner'])], limit=1)
    #         if account.account_type in ['asset_receivable']:
    #             partner = self.env['res.partner'].search([('name', '=', receipt_data['partner'])], limit=1)
    #             if not partner:
    #                 partner = self.env['res.partner'].create({
    #                     'name': receipt_data['partner'],
    #                     'company_type': 'company',
    #                 })
    #
    #             journal = self.env['account.journal'].search(
    #                 [('name', 'ilike', receipt_data['payment_method'] or 'Bank')], limit=1
    #             )
    #             if not journal:
    #                 journal = self.env['account.journal'].search([('type', '=', 'bank')], limit=1)
    #             if not journal:
    #                 raise UserError(f"Journal for {receipt_data['payment_method'] or 'Bank'} not found.")
    #
    #             memo = "\n".join(line.strip() for line in receipt_data['memo_lines'] if line.strip()).strip()
    #
    #             payment_vals = {
    #                 'partner_id': partner.id,
    #                 'amount': receipt_data['amount'] + receipt_data['tds_amount'],
    #                 'payment_type': 'inbound',
    #                 'partner_type': 'customer',
    #                 'name': receipt_data['vch_no'],
    #                 'memo': memo or f"Receipt {receipt_data['vch_no']}",
    #                 'date': receipt_data.get('date') or self.default_date,
    #                 'journal_id': journal.id,
    #                 'payment_method_line_id': journal.inbound_payment_method_line_ids[:1].id,
    #             }
    #
    #             payment = self.env['account.payment'].create(payment_vals)
    #             payment.action_post()
    #         else:
    #
    #
    #         # Safe reconciliation
    #         for inv_ref, alloc_amount in receipt_data['invoice_refs']:
    #             invoice = self.env['account.move'].search([
    #                 ('ref', '=', inv_ref),
    #                 ('move_type', '=', 'out_invoice'),
    #                 ('state', '!=', 'cancel')
    #             ], limit=1)
    #             if not invoice:
    #                 continue
    #
    #             payment_rec = payment.move_id.line_ids.filtered(
    #                 lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
    #             )
    #             inv_rec = invoice.line_ids.filtered(
    #                 lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
    #             )
    #
    #             if payment_rec and inv_rec:
    #                 try:
    #                     (payment_rec + inv_rec).reconcile()
    #                     _logger.info("--------- Reconciled payment %s with invoice %s ---------------", payment.name, invoice.name)
    #                 except UserError as e:
    #                     if "already reconciled" in str(e):
    #                         pass  # skip silently
    #                     else:
    #                         raise
    #         _logger.info("---------- Created payment for %s, vch_no %s ----------------------", receipt_data['partner'], receipt_data['vch_no'])
    #     return True

    def _import_receipt(self, df):
        company = 'lasertech'
        for row_idx in range(10):
            row = df.iloc[row_idx]
            header_text = str(row.get(0, '')).strip().upper()
            if 'ADROIT ENGINEERING' in header_text:
                company = 'engineering'
                break
            elif 'ADROITRE ENERGY LLP' in header_text:
                company = 'energyllp'
                break

        receipts = []
        current_receipt = None

        if company in ('energyllp'):
            for i in range(len(df)):
                row = df.iloc[i].dropna(how='all')
                if row.empty:
                    continue

                # Detect new receipt
                if pd.notna(row.get(6)) and 'Receipt' in str(row.get(6)).strip() and pd.notna(row.get(9)):
                    if current_receipt:
                        receipts.append(current_receipt)

                    inv_date = None
                    if pd.notna(row.get(0)):
                        if isinstance(row[0], datetime):
                            inv_date = row[0].date()
                        else:
                            try:
                                inv_date = datetime(1899, 12, 30) + timedelta(days=float(row[0]))
                                inv_date = inv_date.date()
                            except:
                                pass

                    partner_name = str(row.get(1, 'Unknown Partner')).strip().replace('_x000D_', ' ').strip()

                    current_receipt = {
                        'date': inv_date,
                        'partner': partner_name,
                        'vch_no': str(row.get(7, 'Unknown')).strip(),
                        'memo_lines': [],
                        'amount': float(row.get(9, 0)),
                        'debit_account_name': '',
                        'invoice_refs': [],  # list of (ref, alloc_amount)
                        'tds_amount': 0.0,
                    }

                elif current_receipt:
                    desc = str(row.get(1, '')).strip().replace('_x000D_', ' ').strip()

                    # === Agst Ref / New Ref (handles ARE... and AL... refs) ===
                    if ('Agst Ref' in desc or 'New Ref' in desc) and pd.notna(row.get(2)):
                        ref = str(row.get(2)).strip()
                        # Amount can be in col 4, 5 or 9
                        alloc_amount = 0.0
                        for col in [4, 5, 9]:
                            if pd.notna(row.get(col)) and isinstance(row[col], (int, float)):
                                try:
                                    alloc_amount = float(row[col])
                                    break
                                except:
                                    pass
                        if ('ARE' in ref or 'AL' in ref) and alloc_amount > 0:
                            current_receipt['invoice_refs'].append((ref, alloc_amount))
                            current_receipt['memo_lines'].append(f"Agst Ref: {ref} ({alloc_amount:.2f})")

                    # === Debit Account (Bank / Cash) - improved for LLP banks ===
                    if pd.notna(row.get(1)) and pd.notna(row.get(8)) and any(
                            kw in desc.upper() for kw in
                            ['IDFC', 'SARASWAT', 'HDFC', 'ICICI', 'AXIS', 'YESB', 'SBIN', 'BANK', 'CASH']):
                        current_receipt['debit_account_name'] = desc
                        current_receipt['memo_lines'].append(f"Debit Account: {desc}")

                    # === TDS Receivable ===
                    if 'TDS Receivable' in desc and pd.notna(row.get(8)):
                        try:
                            tds = float(row[8])
                            current_receipt['tds_amount'] = tds
                            current_receipt['memo_lines'].append(f"TDS Receivable U/s 194Q: {tds:.2f}")
                        except:
                            pass

                    # === Round Off ===
                    if 'Round Off' in desc:
                        try:
                            amount = float(row.get(8, 0)) if pd.notna(row.get(8)) else -float(row.get(9, 0))
                            current_receipt['memo_lines'].append(f"Round Off: {amount:.2f}")
                        except:
                            pass

                    # === Transaction Narrative (NEFT/RTGS/IMPS/Cheque etc.) ===
                    if pd.notna(row.get(1)) and any(
                            kw in desc.upper() for kw in ['NEFT', 'RTGS', 'IMPS', 'CHEQUE', 'DD', 'TRANSFER', 'IFT']):
                        narrative = desc
                        for col in [2, 3, 4, 5]:
                            if pd.notna(row.get(col)):
                                narrative += f" {str(row[col]).strip()}"
                        current_receipt['memo_lines'].append(f"Transaction: {narrative}")

            if current_receipt:
                receipts.append(current_receipt)
        else:
            for i in range(len(df)):
                row = df.iloc[i]
                if row.dropna().empty:
                    continue

                # Detect new receipt voucher
                if pd.notna(row.get(6)) and str(row.get(6, '')).strip() == 'Receipt' and pd.notna(row.get(9)):
                    if current_receipt:
                        receipts.append(current_receipt)

                    inv_date = None
                    if pd.notna(row.get(0)):
                        if isinstance(row[0], datetime):
                            inv_date = row[0].date()
                        elif isinstance(row[0], str):
                            try:
                                inv_date = datetime.strptime(row[0], '%d-%b-%y').date()
                            except ValueError:
                                pass

                    partner_name = str(row.get(1, 'Unknown Partner')).strip()
                    if pd.notna(row.get(0)) and str(row[0]).isdigit():
                        partner_name = f"{row[0]} - {partner_name}".strip()

                    current_receipt = {
                        'date': inv_date,
                        'partner': partner_name,
                        'vch_no': str(row.get(7, 'Unknown')).strip(),
                        'memo_lines': [],
                        'amount': float(row.get(9, 0)),
                        'debit_account_name': '',
                        'invoice_refs': [],
                        'tds_amount': 0.0,
                    }

                elif current_receipt:
                    desc = str(row.get(1, '')).strip()

                    # Agst Ref
                    if 'Agst Ref' in desc or (pd.notna(row.get(2)) and str(row.get(2, '')).startswith('AL')):
                        ref_col = 2 if pd.notna(row.get(2)) else 1
                        amt_col_candidates = [4, 3, 5]
                        ref = str(row.get(ref_col, '')).strip()

                        alloc_amount = 0.0
                        for col in amt_col_candidates:
                            if pd.notna(row.get(col)) and isinstance(row[col], (int, float)):
                                try:
                                    alloc_amount = float(row[col])
                                    break
                                except ValueError:
                                    pass

                        if ref.startswith('AL') and alloc_amount > 0:
                            current_receipt['invoice_refs'].append((ref, alloc_amount))
                            current_receipt['memo_lines'].append(f"Agst Ref: {ref} ({alloc_amount:.2f})")

                    # Debit account (bank/cash)
                    if pd.notna(row.get(1)) and pd.notna(row.get(8)) and any(
                            kw in desc.upper() for kw in ['CASH', 'BANK', 'SARASWAT', 'CO-OPERATIVE']):
                        current_receipt['debit_account_name'] = desc
                        current_receipt['memo_lines'].append(f"Debit Account: {desc}")

                    # Transaction details
                    if pd.notna(row.get(1)) and any(kw in desc.upper() for kw in ['NEFT', 'RTGS', 'IMPS', 'CHEQUE', 'DD']):
                        ref_text = desc
                        for col in [2, 3, 4]:
                            if pd.notna(row.get(col)):
                                ref_text += f" {str(row[col]).strip()}"
                        current_receipt['memo_lines'].append(f"Transaction: {ref_text}")

                    # Narrative
                    if pd.notna(row.get(1)) and (
                            any(kw in desc.upper() for kw in ['NEFT', 'RTGS', 'IMPS', 'TRANSFER', 'OPENING'])
                            or re.search(r'\d{2}-\d{2}-\d{4}', desc)
                    ):
                        narrative = desc
                        for col in [2, 3, 4]:
                            if pd.notna(row.get(col)):
                                narrative += f" {str(row[col]).strip()}"
                        current_receipt['memo_lines'].append(f"Note: {narrative}")

                    # TDS Receivable
                    if 'TDS Receivable' in desc and pd.notna(row.get(8)):
                        try:
                            tds = float(row[8])
                            current_receipt['tds_amount'] = tds
                            current_receipt['memo_lines'].append(f"TDS Receivable: {tds:.2f}")
                        except ValueError:
                            pass

            if current_receipt:
                receipts.append(current_receipt)

        # Process receipts as journal entries
        misc_journal = self.env['account.journal'].search([('type', '=', 'general'),('name', '=', 'Receipt')], limit=1)
        if not misc_journal:
            raise UserError("No Miscellaneous/General journal found. Please create one.")

        receivable_account = self.env['account.account'].search([
            ('account_type', '=', 'asset_receivable'),
        ], limit=1)
        if not receivable_account:
            raise UserError("No Receivable account found in Chart of Accounts.")

        # Search for TDS Receivable account (common names in Indian localization)
        if company == 'energyllp':
            tds_account = self.env['account.account'].search([
                ('name', '=', 'TDS Receivable U/s 194Q'),
            ], limit=1)
        else:
            tds_account = self.env['account.account'].search([
                ('name', '=', 'TDS Receivable 194C'),
            ], limit=1)

        for receipt_data in receipts:
            # Partner (optional)
            partner = self.env['res.partner'].search([('name', '=', receipt_data['partner'])], limit=1)

            # Debit account (bank/cash)
            debit_account = self.env['account.account'].search([('name', '=', receipt_data['debit_account_name'])],
                                                               limit=1)
            if not debit_account:
                # _logger.warning(
                #     f"Skipping entry {receipt_data['vch_no']} - Debit account '{receipt_data['debit_account_name']}' not found.")
                # continue
                raise UserError(f"------------Debit account '{receipt_data['debit_account_name']}' not found for receipt '{receipt_data['vch_no']}'. Please set it up before importing.")

            # Credit account: Partner-specific receivable if available, else default
            credit_account = partner.property_account_receivable_id

            if not credit_account:
                credit_account = self.env['account.account'].search([('name', '=', receipt_data['partner'])], limit=1)
                # _logger.warning(f"Skipping entry {receipt_data['vch_no']} - Credit account not found.")
                # continue
            if not credit_account:
                raise UserError(f"------------Credit account for partner '{receipt_data['partner']}' not found. Please set it up before importing.")

            memo = "\n".join(receipt_data['memo_lines']).strip() or f"Receipt {receipt_data['vch_no']}"

            line_ids = []

            # 2. Credit: Receivable (main amount)
            line_ids.append((0, 0, {
                'account_id': credit_account.id,
                'partner_id': partner.id if partner else False,
                'debit': 0.0,
                'credit': receipt_data['amount'],
                'name': f"Receipt - {receipt_data['vch_no']}",
            }))

            # 1. Debit: Bank/Cash (main amount + TDS)
            # total_debit = receipt_data['amount'] + receipt_data['tds_amount']
            total_debit = receipt_data['amount'] - receipt_data['tds_amount']
            line_ids.append((0, 0, {
                'account_id': debit_account.id,
                'partner_id': partner.id if partner else False,
                'debit': total_debit,
                'credit': 0.0,
                'name': f"Receipt - {receipt_data['vch_no']} (Bank/Cash)",
            }))

            # 3. If TDS exists → separate Debit line to TDS Receivable
            if receipt_data['tds_amount'] > 0:
                if tds_account:
                    line_ids.append((0, 0, {
                        'account_id': tds_account.id,
                        'partner_id': partner.id if partner else False,
                        'debit': receipt_data['tds_amount'],
                        'credit': 0.0,
                        'name': f"TDS Receivable - {receipt_data['vch_no']}",
                    }))
                else:
                    raise ValueError(
                        f"-------------- TDS Receivable account not found for {receipt_data['vch_no']}. TDS {receipt_data['tds_amount']} not booked.-----------------")

            move_vals = {
                'date': receipt_data.get('date') or self.default_date,
                'ref': receipt_data['vch_no'],
                'journal_id': misc_journal.id,
                'move_type': 'entry',
                'narration': memo,
                'line_ids': line_ids,
            }

            try:
                move = self.env['account.move'].create(move_vals)
                move.action_post()
            except:
                import pdb;pdb.set_trace()

            # Reconciliation with invoices (if any)
            if receipt_data['invoice_refs']:
                receivable_lines = move.line_ids.filtered(
                    lambda l: l.account_id.account_type == 'asset_receivable' and l.credit > 0
                )
                for inv_ref, alloc_amount in receipt_data['invoice_refs']:
                    invoice = self.env['account.move'].search([
                        ('ref', '=', inv_ref),
                        ('move_type', '=', 'out_invoice'),
                        ('state', '!=', 'cancel')
                    ], limit=1)
                    if not invoice:
                        continue

                    inv_rec = invoice.line_ids.filtered(
                        lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
                    )

                    if receivable_lines and inv_rec:
                        try:
                            (receivable_lines + inv_rec).reconcile()
                            _logger.info("--------- Reconciled receipt %s with invoice %s ---------------", move.name, invoice.name)
                        except UserError as e:
                            if "already reconciled" in str(e):
                                pass
                            else:
                                raise

            _logger.info(f"-------------- Created journal entry {move.name} for receipt {receipt_data['vch_no']}----------------")

        return True

    def _import_payment(self, df):
        # Detect company based on header
        company = 'lasertech'
        for row_idx in range(10):
            row = df.iloc[row_idx]
            if pd.notna(row.get(0)) and 'ADROIT ENGINEERING' in str(row[0]).strip():
                company = 'engineering'
                break
            if pd.notna(row.get(0)) and 'ADROITRE ENERGY LLP' in str(row[0]).strip():
                company = 'energyllp'
                break

        payments = []
        current_payment = None
        if company == 'engineering':
            # New logic for ADROIT ENGINEERING
            for i in range(len(df)):
                row = df.iloc[i].dropna(how='all')
                if row.empty:
                    continue

                # Detect new payment voucher
                if pd.notna(row.get(0)) and pd.notna(row.get(6)) and str(
                        row.get(6, '')).strip() == 'Payment' and pd.notna(row.get(8)):
                    if current_payment:
                        payments.append(current_payment)

                    inv_date = None
                    if pd.notna(row.get(0)):
                        if isinstance(row[0], datetime):
                            inv_date = row[0].date()
                        elif isinstance(row[0], (float, int)):
                            try:
                                inv_date = datetime(1899, 12, 30) + timedelta(days=float(row[0]))
                            except ValueError:
                                pass
                        elif isinstance(row[0], str):
                            try:
                                inv_date = datetime.strptime(row[0], '%d-%b-%Y').date()
                            except ValueError:
                                pass

                    partner_name = str(row.get(1, 'Unknown Partner')).strip().replace('_x000D_', ' ')

                    amount = float(row.get(8, 0))  # Debit amount

                    current_payment = {
                        'date': inv_date,
                        'partner': partner_name.strip(),
                        'vch_no': str(row.get(7, 'Unknown')).strip(),
                        'memo_lines': [],
                        'amount': amount,
                        'credit_account_name': '',  # Bank/Cash for credit
                        'bill_refs': [],
                        'notes': [],
                        'round_off_debit': 0.0,
                        'round_off_credit': 0.0,
                        'additional_lines': [],  # For GST or other
                    }

                elif current_payment:
                    desc = str(row.get(1, '')).strip().replace('_x000D_', ' ')

                    # Agst Ref
                    if 'Agst Ref' in desc:
                        ref = str(row.get(2, '')).strip().replace('_x000D_', ' ') if pd.notna(row.get(2)) else ''
                        amt_col = None
                        if pd.notna(row.get(3)) and not isinstance(row.get(3), datetime):
                            amt_col = row.get(3)
                        elif pd.notna(row.get(4)) and not isinstance(row.get(4), datetime):
                            amt_col = row.get(4)
                        if ref and amt_col is not None:
                            try:
                                alloc_amount = float(amt_col)
                                current_payment['bill_refs'].append((ref, alloc_amount))
                                current_payment['memo_lines'].append(f"Agst Ref: {ref} ({alloc_amount:.2f})")
                            except ValueError:
                                pass

                    # Credit account (bank/cash)
                    if pd.notna(row.get(1)) and pd.notna(row.get(9)) and any(
                            kw in desc.upper() for kw in
                            ['CASH', 'BANK', 'SARASWAT', 'CO-OPERATIVE', 'IDFC', 'AXIS', 'IDBI','HDFC']):
                        current_payment['credit_account_name'] = desc
                        current_payment['memo_lines'].append(f"Credit Account: {desc}")

                    # Round Off
                    if 'Round Off' in desc:
                        if pd.notna(row.get(8)):
                            try:
                                current_payment['round_off_debit'] = float(row[8])
                                current_payment['memo_lines'].append(
                                    f"Round Off Debit: {current_payment['round_off_debit']:.2f}")
                            except ValueError:
                                pass
                        elif pd.notna(row.get(9)):
                            try:
                                current_payment['round_off_credit'] = float(row[9])
                                current_payment['memo_lines'].append(
                                    f"Round Off Credit: {current_payment['round_off_credit']:.2f}")
                            except ValueError:
                                pass

                    # Additional lines like Input CGST/SGST
                    if pd.notna(row.get(1)) and (
                            'Input CGST' in desc or 'Input SGST' in desc or 'Input IGST' in desc) and (
                            pd.notna(row.get(8)) or pd.notna(row.get(9))):
                        account = desc
                        debit = float(row.get(8, 0))
                        credit = float(row.get(9, 0))
                        current_payment['additional_lines'].append(
                            {'account': account, 'debit': debit, 'credit': credit})
                        current_payment['memo_lines'].append(
                            f"Additional Line: {account} Debit: {debit} Credit: {credit}")

                    # Transaction details
                    if pd.notna(row.get(1)) and any(
                            kw in desc.upper() for kw in ['RTGS', 'NEFT', 'CHEQUE', 'TRF', 'IB', 'UPI', 'EMI']):
                        ref_text = desc
                        for col in [2, 3, 4, 5]:
                            if pd.notna(row.get(col)):
                                ref_text += f" {str(row[col]).strip().replace('_x000D_', ' ')}"
                        current_payment['memo_lines'].append(f"Transaction: {ref_text}")

                    # Notes (Being ...)
                    if desc.lower().startswith('being') or 'debited' in desc.lower() or 'charges' in desc.lower():
                        narrative = desc
                        current_payment['memo_lines'].append(f"Note: {narrative}")
                        current_payment['notes'].append(narrative)

                    # Entered By
                    if 'Entered By :' in desc and pd.notna(row.get(2)):
                        entered_by = str(row[2]).strip()
                        current_payment['notes'].append(f"Entered By: {entered_by}")

            if current_payment:
                payments.append(current_payment)

            # Process payments as journal entries in Miscellaneous journal
            misc_journal = self.env['account.journal'].search([('type', '=', 'general'), ('name', '=', 'Payment')],
                                                              limit=1)
            if not misc_journal:
                raise UserError("No Miscellaneous/General journal found. Please create one.")

            # payable_account = self.env['account.account'].search([
            #     ('account_type', '=', 'liability_payable'),
            # ], limit=1)
            # if not payable_account:
            #     raise UserError("No Payable account found in Chart of Accounts.")

            round_off_account = self.env['account.account'].search([
                ('name', '=', 'Round Off (+/-)'),
            ], limit=1)

            for payment_data in payments:
                # Partner (optional)
                partner = self.env['res.partner'].search([('name', '=', payment_data['partner'])], limit=1)

                # Debit account: Expense or Payable based on partner_name (search chart of accounts)
                debit_account = self.env['account.account'].search([('name', '=', payment_data['partner'])], limit=1)
                if not debit_account:
                    _logger.warning(
                        f"--------- Skipping entry {payment_data['vch_no']} - Debit account '{payment_data['partner']}' not found.-------------")
                    import pdb;
                    pdb.set_trace()
                    continue

                # Credit account: Bank/Cash (search by name)
                credit_account = self.env['account.account'].search(
                    [('name', '=', payment_data['credit_account_name'])],
                    limit=1)
                if not credit_account:
                    _logger.warning(
                        f"--------------Skipping entry {payment_data['vch_no']} - Credit account '{payment_data['credit_account_name']}' not found.------------------")
                    import pdb;
                    pdb.set_trace()
                    continue

                memo = "\n".join(payment_data['memo_lines']).strip() or f"Payment {payment_data['vch_no']}"

                line_ids = []

                # Debit: Expense or Payable
                debit_amount = payment_data['amount']
                line_ids.append((0, 0, {
                    'account_id': debit_account.id,
                    'partner_id': partner.id if partner else False,
                    'debit': debit_amount,
                    'credit': 0.0,
                    'name': f"Payment - {payment_data['vch_no']} ({payment_data['partner']})",
                }))

                # Credit: Bank/Cash
                credit_amount = payment_data['amount']
                if payment_data['round_off_debit'] or payment_data['round_off_credit']:
                    credit_amount += payment_data['round_off_debit']
                    credit_amount -= payment_data['round_off_credit']
                if payment_data['additional_lines']:
                    for add_line in payment_data['additional_lines']:
                        credit_amount += add_line['debit']
                        credit_amount -= add_line['credit']
                line_ids.append((0, 0, {
                    'account_id': credit_account.id,
                    'partner_id': partner.id if partner else False,
                    'debit': 0.0,
                    'credit': credit_amount,
                    'name': f"Paid from {payment_data['credit_account_name']}",
                }))

                # Round Off as separate line
                if (payment_data['round_off_debit'] or payment_data['round_off_credit']) and round_off_account:
                    line_ids.append((0, 0, {
                        'account_id': round_off_account.id,
                        'partner_id': partner.id if partner else False,
                        'debit': payment_data['round_off_debit'],
                        'credit': payment_data['round_off_credit'],
                        'name': f"Round Off - {payment_data['vch_no']}",
                    }))

                # Additional lines (e.g., GST)
                for add_line in payment_data['additional_lines']:
                    add_account = self.env['account.account'].search([('name', '=', add_line['account'])], limit=1)
                    if not add_account:
                        _logger.warning(
                            f"Skipping additional line for {add_line['account']} in entry {payment_data['vch_no']} - Account not found.")
                        continue
                    line_ids.append((0, 0, {
                        'account_id': add_account.id,
                        'partner_id': partner.id if partner else False,
                        'debit': add_line['debit'],
                        'credit': add_line['credit'],
                        'name': f"{add_line['account']} - {payment_data['vch_no']}",
                    }))

                move_vals = {
                    'date': payment_data.get('date') or self.default_date,
                    'ref': payment_data['vch_no'],
                    'journal_id': misc_journal.id,
                    'move_type': 'entry',
                    'narration': memo,
                    'line_ids': line_ids,
                }

                try:
                    move = self.env['account.move'].create(move_vals)
                    if move.state != 'posted':
                        move.action_post()
                except:
                    import pdb;
                    pdb.set_trace()

                # Reconciliation with vendor bills if bill_refs (Agst Ref)
                if payment_data['bill_refs']:
                    payable_line = move.line_ids.filtered(lambda l: l.account_id.account_type == 'liability_payable' and l.debit > 0)
                    for bill_ref, alloc_amount in payment_data['bill_refs']:
                        bill = self.env['account.move'].search([
                            ('ref', '=', bill_ref),
                            ('move_type', '=', 'in_invoice'),
                            ('state', '!=', 'cancel')
                        ], limit=1)
                        if not bill:
                            continue

                        bill_payable = bill.line_ids.filtered(
                            lambda l: l.account_id.account_type == 'liability_payable' and not l.reconciled
                        )

                        if payable_line and bill_payable:
                            try:
                                (payable_line + bill_payable).reconcile()
                            except UserError as e:
                                if "already reconciled" in str(e):
                                    pass
                                else:
                                    _logger.error(f"----------Reconciliation error for payment {move.name} and bill {bill.name}: {str(e)}---------------")

                _logger.info(
                    f"----------- Created payment entry {move.name} for payment {payment_data['vch_no']}---------------")

            return True
        elif company in ('energyllp'):
            for i in range(len(df)):
                row = df.iloc[i].dropna(how='all')
                if row.empty:
                    continue

                # Detect new payment voucher
                if pd.notna(row.get(0)) and pd.notna(row.get(6)) and str(
                        row.get(6, '')).strip() == 'Payment' and pd.notna(row.get(8)):
                    if current_payment:
                        payments.append(current_payment)

                    inv_date = None
                    if pd.notna(row.get(0)):
                        if isinstance(row[0], datetime):
                            inv_date = row[0].date()
                        else:
                            try:
                                inv_date = datetime(1899, 12, 30) + timedelta(days=float(row[0]))
                                inv_date = inv_date.date()
                            except:
                                pass

                    partner_name = str(row.get(1, 'Unknown Partner')).strip().replace('_x000D_', ' ').strip()

                    amount = float(row.get(8, 0))  # Debit amount (main amount)

                    current_payment = {
                        'date': inv_date,
                        'partner': partner_name,
                        'vch_no': str(row.get(7, 'Unknown')).strip(),
                        'memo_lines': [],
                        'amount': amount,
                        'credit_account_name': '',  # Bank / Cash
                        'bill_refs': [],  # Agst Ref
                        'notes': [],
                        'round_off_debit': 0.0,
                        'round_off_credit': 0.0,
                        'additional_lines': [],  # CGST / SGST etc.
                    }

                elif current_payment:
                    desc = str(row.get(1, '')).strip().replace('_x000D_', ' ').strip()

                    # === Agst Ref ===
                    if 'Agst Ref' in desc and pd.notna(row.get(2)):
                        ref = str(row.get(2)).strip()
                        alloc_amount = 0.0
                        for col in [3, 4]:
                            if pd.notna(row.get(col)):
                                try:
                                    alloc_amount = float(row[col])
                                    break
                                except:
                                    pass
                        if ref and alloc_amount != 0:
                            current_payment['bill_refs'].append((ref, alloc_amount))
                            current_payment['memo_lines'].append(f"Agst Ref: {ref} ({alloc_amount:.2f})")

                    # === Credit Account (Bank / Cash) ===
                    if pd.notna(row.get(1)) and pd.notna(row.get(9)) and any(
                            kw in desc.upper() for kw in
                            ['IDFC', 'SARASWAT', 'HDFC', 'ICICI', 'AXIS', 'YESB', 'SBIN', 'BANK', 'CASH']):
                        current_payment['credit_account_name'] = desc
                        current_payment['memo_lines'].append(f"Credit Account: {desc}")

                    # === Round Off ===
                    if 'Round Off' in desc:
                        try:
                            if pd.notna(row.get(8)):
                                current_payment['round_off_debit'] = float(row[8])
                            elif pd.notna(row.get(9)):
                                current_payment['round_off_credit'] = float(row[9])
                            current_payment['memo_lines'].append(
                                f"Round Off: Debit {current_payment['round_off_debit']:.2f} Credit {current_payment['round_off_credit']:.2f}")
                        except:
                            pass

                    # === Additional lines (Input CGST / SGST) ===
                    if any(x in desc for x in ['Input CGST', 'Input SGST', 'Input IGST']) and (
                            pd.notna(row.get(8)) or pd.notna(row.get(9))):
                        debit = float(row.get(8, 0))
                        credit = float(row.get(9, 0))
                        current_payment['additional_lines'].append({
                            'account': desc,
                            'debit': debit,
                            'credit': credit
                        })
                        current_payment['memo_lines'].append(f"Additional: {desc} D:{debit} C:{credit}")

                    # === Transaction / Narrative ===
                    if any(kw in desc.upper() for kw in ['NEFT', 'RTGS', 'IMPS', 'CHEQUE', 'TRF', 'IFT', 'UPI']):
                        narrative = desc
                        for col in [2, 3, 4, 5]:
                            if pd.notna(row.get(col)):
                                narrative += f" {str(row[col]).strip().replace('_x000D_', ' ')}"
                        current_payment['memo_lines'].append(f"Transaction: {narrative}")

                    # === Notes (Being ...) ===
                    if desc.lower().startswith('being') or 'being cash' in desc.lower():
                        current_payment['notes'].append(desc)
                        current_payment['memo_lines'].append(f"Note: {desc}")

            if current_payment:
                payments.append(current_payment)

            # ==================== CREATE JOURNAL ENTRIES ====================
            misc_journal = self.env['account.journal'].search([('type', '=', 'general'), ('name', 'ilike', 'Payment')],
                                                              limit=1)
            if not misc_journal:
                # misc_journal = self.env['account.journal'].search([('type', '=', 'general')], limit=1)
                raise UserError("------------No Miscellaneous/General journal found. Please create one.")

            round_off_account = self.env['account.account'].search([('name', 'ilike', 'Round Off')], limit=1)

            for payment_data in payments:
                partner = self.env['res.partner'].search([('name', '=', payment_data['partner'])], limit=1)

                # Debit Account (Expense / Payable / Loan etc.)
                debit_account = self.env['account.account'].search([('name', '=', payment_data['partner'])], limit=1)
                if not debit_account:
                    raise UserError(f"------------Debit account for '{payment_data['partner']}' not found for payment '{payment_data['vch_no']}'. Please set it up before importing.-----------------")
                    # debit_account = self.env['account.account'].search(
                    #     [('name', 'ilike', payment_data['partner'][:60])], limit=1)

                # Credit Account (Bank)
                credit_account = self.env['account.account'].search(
                    [('name', '=', payment_data['credit_account_name'])], limit=1)
                if not credit_account:
                    raise UserError(f"------------Credit account '{payment_data['credit_account_name']}' not found for payment '{payment_data['vch_no']}'. Please set it up before importing.-----------------")
                memo = "\n".join(payment_data['memo_lines']) or f"Payment {payment_data['vch_no']}"

                line_ids = []

                # Main Debit
                debit_amt = payment_data['amount'] - payment_data['round_off_debit']
                line_ids.append((0, 0, {
                    'account_id': debit_account.id,
                    'partner_id': partner.id if partner else False,
                    'debit': payment_data['amount'],
                    'credit': 0.0,
                    'name': f"Payment - {payment_data['vch_no']}",
                }))

                # Main Credit (Bank)
                credit_amt = payment_data['amount'] - payment_data['round_off_credit'] + payment_data['round_off_debit']
                if payment_data['additional_lines']:
                    for add in payment_data['additional_lines']:
                        credit_amt += add['debit']
                        credit_amt -= add['credit']
                line_ids.append((0, 0, {
                    'account_id': credit_account.id,
                    'partner_id': partner.id if partner else False,
                    'debit': 0.0,
                    'credit': credit_amt,
                    'name': f"Paid from {payment_data['credit_account_name']}",
                }))

                # Round Off
                if payment_data['round_off_debit'] or payment_data['round_off_credit']:
                    if round_off_account:
                        line_ids.append((0, 0, {
                            'account_id': round_off_account.id,
                            'debit': payment_data['round_off_debit'],
                            'credit': payment_data['round_off_credit'],
                            'name': f"Round Off - {payment_data['vch_no']}",
                        }))

                # Additional lines (CGST / SGST)
                for add in payment_data['additional_lines']:
                    add_acc = self.env['account.account'].search([('name', '=', add['account'])], limit=1)
                    if add_acc:
                        line_ids.append((0, 0, {
                            'account_id': add_acc.id,
                            'debit': add['debit'],
                            'credit': add['credit'],
                            'name': add['account'],
                        }))
                try:
                    move = self.env['account.move'].create({
                        'date': payment_data.get('date') or fields.Date.today(),
                        'ref': payment_data['vch_no'],
                        'journal_id': misc_journal.id,
                        'move_type': 'entry',
                        'narration': memo,
                        'line_ids': line_ids,
                    })
                except:
                    import pdb;pdb.set_trace()

                move.action_post()

                # Auto-reconcile with vendor bills (Agst Ref)
                if payment_data['bill_refs']:
                    payable_line = move.line_ids.filtered(lambda l: l.debit > 0 and l.account_id == debit_account)
                    for bill_ref, alloc in payment_data['bill_refs']:
                        bill = self.env['account.move'].search(
                            [('ref', '=', bill_ref), ('move_type', '=', 'in_invoice')], limit=1)
                        if bill:
                            bill_payable = bill.line_ids.filtered(
                                lambda l: l.account_id.account_type == 'liability_payable' and not l.reconciled)
                            if payable_line and bill_payable:
                                try:
                                    (payable_line + bill_payable).reconcile()
                                except:
                                    pass

                _logger.info(
                    f"---------- Created Payment Journal {move.name} for {payment_data['partner']} (Vch: {payment_data['vch_no']}) ----------------------")

            return True
        else:
            # Old logic for adroit lasertech
            for i in range(len(df)):
                row = df.iloc[i]
                if row.dropna().empty:
                    continue

                # Detect new payment voucher
                if pd.notna(row.get(6)) and str(row.get(6, '')).strip() == 'Payment' and (
                        pd.notna(row.get(8)) or pd.notna(row.get(9))):
                    if current_payment:
                        payments.append(current_payment)

                    inv_date = None
                    if pd.notna(row.get(0)):
                        if isinstance(row[0], datetime):
                            inv_date = row[0].date()
                        elif isinstance(row[0], str):
                            try:
                                inv_date = datetime.strptime(row[0], '%d-%b-%y').date()
                            except ValueError:
                                pass

                    partner_name = str(row.get(1, 'Unknown Partner')).strip()
                    if pd.notna(row.get(0)) and str(row[0]).isdigit():
                        partner_name = f"{row[0]} - {partner_name}".strip()

                    amount = float(row.get(8, 0))  # Debit amount (primary)

                    current_payment = {
                        'date': inv_date,
                        'partner': partner_name,
                        'vch_no': str(row.get(7, 'Unknown')).strip(),
                        'memo_lines': [],
                        'amount': amount,
                        'credit_account_name': '',  # Bank/Cash for credit
                        'bill_refs': [],
                        'notes': [],
                        'round_off_amount': 0.0,
                    }

                elif current_payment:
                    desc = str(row.get(1, '')).strip()

                    # Agst Ref or On Account
                    if 'Agst Ref' in desc or 'On Account' in desc:
                        ref = str(row.get(2, '')).strip() if pd.notna(row.get(2)) else ''
                        amt_col = row.get(3) if pd.notna(row.get(3)) else row.get(4)
                        if ref and pd.notna(amt_col):
                            try:
                                alloc_amount = float(amt_col)
                                current_payment['bill_refs'].append((ref, alloc_amount))
                                current_payment['memo_lines'].append(f"Agst Ref: {ref} ({alloc_amount:.2f})")
                            except ValueError:
                                pass
                        elif 'On Account' in desc:
                            current_payment['memo_lines'].append("On Account")

                    # Credit account (bank/cash)
                    if pd.notna(row.get(1)) and pd.notna(row.get(9)) and any(
                            kw in desc.upper() for kw in ['CASH', 'BANK', 'SARASWAT', 'CO-OPERATIVE']):
                        current_payment['credit_account_name'] = desc
                        current_payment['memo_lines'].append(f"Credit Account: {desc}")

                    if 'Round Off' in desc and pd.notna(row.get(9)):
                        try:
                            round_off = float(row[9])
                            current_payment['round_off_amount'] = round_off
                            current_payment['memo_lines'].append(f"Round Off: {round_off:.2f}")
                        except ValueError:
                            pass

                    # Transaction details
                    if pd.notna(row.get(1)) and any(
                            kw in desc.upper() for kw in ['RTGS', 'NEFT', 'CHEQUE', 'TRF', 'IB']):
                        ref_text = desc
                        for col in [2, 3, 4]:
                            if pd.notna(row.get(col)):
                                ref_text += f" {str(row[col]).strip()}"
                        current_payment['memo_lines'].append(f"Transaction: {ref_text}")

                    # Notes (being cash to...)
                    if desc.startswith('being cash') or 'Debited' in desc or 'Charges' in desc:
                        narrative = desc
                        current_payment['memo_lines'].append(f"Note: {narrative}")
                        current_payment['notes'].append(narrative)

            if current_payment:
                payments.append(current_payment)

                # Process payments as journal entries in Miscellaneous journal
            misc_journal = self.env['account.journal'].search([('type', '=', 'general'), ('name', '=', 'Payment')], limit=1)
            if not misc_journal:
                raise UserError("No Miscellaneous/General journal found. Please create one.")

            payable_account = self.env['account.account'].search([
                ('account_type', '=', 'liability_payable'),
            ], limit=1)
            if not payable_account:
                raise UserError("No Payable account found in Chart of Accounts.")

            round_off_account = self.env['account.account'].search([
                ('name', '=', 'Round Off'),
            ], limit=1)

            for payment_data in payments:
                # Partner (optional)
                partner = self.env['res.partner'].search([('name', '=', payment_data['partner'])], limit=1)

                # Debit account: Expense or Payable based on partner_name (search chart of accounts)
                debit_account = self.env['account.account'].search([('name', '=', payment_data['partner'])], limit=1)
                if not debit_account:
                    _logger.warning(
                        f"--------- Skipping entry {payment_data['vch_no']} - Debit account '{payment_data['partner']}' not found.-------------")
                    continue

                # Credit account: Bank/Cash (search by name)
                credit_account = self.env['account.account'].search(
                    [('name', '=', payment_data['credit_account_name'])],
                    limit=1)
                if not credit_account:
                    _logger.warning(
                        f"--------------Skipping entry {payment_data['vch_no']} - Credit account '{payment_data['credit_account_name']}' not found.------------------")
                    continue

                memo = "\n".join(payment_data['memo_lines']).strip() or f"Payment {payment_data['vch_no']}"

                line_ids = []

                # Debit: Expense or Payable
                line_ids.append((0, 0, {
                    'account_id': debit_account.id,
                    'partner_id': partner.id if partner else False,
                    'debit': payment_data['amount'],
                    'credit': 0.0,
                    'name': f"Payment - {payment_data['vch_no']} ({payment_data['partner']})",
                }))

                # Credit: Bank/Cash
                line_ids.append((0, 0, {
                    'account_id': credit_account.id,
                    'partner_id': partner.id if partner else False,
                    'debit': 0.0,
                    'credit': payment_data['amount'] - payment_data['round_off_amount'],
                    'name': f"Paid from {payment_data['credit_account_name']}",
                }))

                if payment_data['round_off_amount'] > 0:
                    if round_off_account:
                        line_ids.append((0, 0, {
                            'account_id': round_off_account.id,
                            'partner_id': partner.id if partner else False,
                            'debit': 0.0,
                            'credit': payment_data['round_off_amount'],
                            'name': f"Round Off - {payment_data['vch_no']}",
                        }))

                move_vals = {
                    'date': payment_data.get('date') or self.default_date,
                    'ref': payment_data['vch_no'],
                    'journal_id': misc_journal.id,
                    'move_type': 'entry',
                    'narration': memo,
                    'line_ids': line_ids,
                }

                try:
                    move = self.env['account.move'].create(move_vals)
                    move.action_post()
                except:
                    import pdb;
                    pdb.set_trace()

                # Reconciliation with vendor bills if bill_refs (Agst Ref)
                if payment_data['bill_refs']:
                    payable_line = move.line_ids.filtered(lambda l: l.account_id == debit_account and l.debit > 0)
                    for bill_ref, alloc_amount in payment_data['bill_refs']:
                        bill = self.env['account.move'].search([
                            ('ref', '=', bill_ref),
                            ('move_type', '=', 'in_invoice'),
                            ('state', '!=', 'cancel')
                        ], limit=1)
                        if not bill:
                            continue

                        bill_payable = bill.line_ids.filtered(
                            lambda l: l.account_id.account_type == 'liability_payable' and not l.reconciled
                        )

                        if payable_line and bill_payable:
                            import pdb;
                            pdb.set_trace()
                            try:
                                (payable_line + bill_payable).reconcile()
                            except UserError as e:
                                if "already reconciled" in str(e):
                                    pass
                                else:
                                    raise

                _logger.info(
                    f"----------- Created payment entry {move.name} for payment {payment_data['vch_no']}---------------")

            return True

    def _import_journal(self, df):
        # Detect company based on header
        company = 'lasertech'
        for row_idx in range(10):
            row = df.iloc[row_idx]
            if pd.notna(row.get(0)) and 'ADROIT ENGINEERING' in str(row[0]).strip():
                company = 'engineering'
                break
            if pd.notna(row.get(0)) and 'ADROITRE ENERGY LLP' in str(row[0]).strip():
                company = 'energyllp'
                break

        journals = []
        current_journal = None

        if company == 'engineering':
            # ====================== NEW LOGIC FOR ADROIT ENGINEERING ======================
            for i in range(len(df)):
                row = df.iloc[i]
                if row.dropna().empty:
                    continue

                # Detect new Journal voucher
                if pd.notna(row.get(6)) and str(row.get(6, '')).strip() == 'Journal' and pd.notna(row.get(7)):
                    if current_journal:
                        journals.append(current_journal)

                    # Date parsing
                    inv_date = None
                    if pd.notna(row.get(0)):
                        if isinstance(row[0], datetime):
                            inv_date = row[0].date()
                        elif isinstance(row[0], (int, float)):
                            try:
                                inv_date = (datetime(1899, 12, 30) + timedelta(days=float(row[0]))).date()
                            except:
                                pass
                        elif isinstance(row[0], str):
                            try:
                                inv_date = datetime.strptime(row[0].strip(), '%d-%b-%Y').date()
                            except:
                                pass

                    account_name = str(row.get(1, 'Unknown')).strip().replace('_x000D_', ' ').strip()

                    current_journal = {
                        'date': inv_date,
                        'vch_no': str(row.get(7, '')).strip(),
                        'lines': [],  # (account_name, debit, credit)
                        'memo_lines': [],
                    }

                    # Add first line - check both debit and credit columns
                    debit = float(row.get(8, 0)) if pd.notna(row.get(8)) else 0.0
                    credit = float(row.get(9, 0)) if pd.notna(row.get(9)) else 0.0

                    if debit != 0 or credit != 0:
                        current_journal['lines'].append((account_name, debit, credit))
                        current_journal['memo_lines'].append(f"{account_name} Dr:{debit:.2f} Cr:{credit:.2f}")

                elif current_journal:
                    desc = str(row.get(1, '')).strip().replace('_x000D_', ' ').strip()

                    debit = float(row.get(8, 0)) if pd.notna(row.get(8)) else 0.0
                    credit = float(row.get(9, 0)) if pd.notna(row.get(9)) else 0.0

                    if debit != 0 or credit != 0:
                        current_journal['lines'].append((desc, debit, credit))
                        current_journal['memo_lines'].append(f"{desc} Dr:{debit:.2f} Cr:{credit:.2f}")

                    # Notes when no amount
                    if desc and debit == 0 and credit == 0:
                        current_journal['memo_lines'].append(f"Note: {desc}")

            if current_journal:
                journals.append(current_journal)

            # ====================== CREATE JOURNAL ENTRIES ======================
            journal_journal = self.env['account.journal'].search([('name', '=', 'Journal')], limit=1)
            if not journal_journal:
                raise UserError("--------------Journal journal not found. Please make sure a journal named exactly 'Journal' exists.")

            for journal_data in journals:
                memo = "\n".join(journal_data['memo_lines']).strip() or f"Journal {journal_data['vch_no']}"

                line_ids = []

                for account_name, debit, credit in journal_data['lines']:
                    # Search account - exact first, then partial
                    account = self.env['account.account'].search([('name', '=', account_name)], limit=1)
                    if not account:
                        import pdb;pdb.set_trace()
                        # account = self.env['account.account'].search([('name', 'ilike', account_name[:60])], limit=1)

                    # if not account:
                    #     _logger.warning(f"Account not found: '{account_name}' in journal {journal_data['vch_no']}")
                    #     continue

                    partner = self.env['res.partner'].search([('name', '=', account_name)], limit=1)

                    line_ids.append((0, 0, {
                        'account_id': account.id,
                        'partner_id': partner.id if partner else False,
                        'debit': debit,
                        'credit': credit,
                        'name': account_name,
                    }))

                if not line_ids:
                    _logger.warning(f"Skipping journal {journal_data['vch_no']} - no valid lines")
                    continue

                move = self.env['account.move'].create({
                    'date': journal_data.get('date') or fields.Date.today(),
                    'ref': journal_data['vch_no'],
                    'journal_id': journal_journal.id,
                    'move_type': 'entry',
                    'narration': memo,
                    'line_ids': line_ids,
                })

                move.action_post()

                _logger.info(f"-----------------✅ Created Journal {move.name} - {journal_data['vch_no']}-----------------")

            return True
        elif company in ('energyllp'):
            for i in range(len(df)):
                row = df.iloc[i].dropna(how='all')
                if row.empty:
                    continue

                # Detect new Journal voucher
                if pd.notna(row.get(6)) and 'Journal' in str(row.get(6)).strip() and pd.notna(row.get(7)):
                    if current_journal:
                        journals.append(current_journal)

                    # Date parsing (Excel serial or string)
                    inv_date = None
                    if pd.notna(row.get(0)):
                        if isinstance(row[0], datetime):
                            inv_date = row[0].date()
                        else:
                            try:
                                inv_date = (datetime(1899, 12, 30) + timedelta(days=float(row[0]))).date()
                            except:
                                pass

                    account_name = str(row.get(1, 'Unknown Account')).strip().replace('_x000D_', ' ').strip()

                    current_journal = {
                        'date': inv_date,
                        'vch_no': str(row.get(7, '')).strip(),
                        'lines': [],  # list of (account_name, debit, credit)
                        'memo_lines': [],
                    }

                    # First line of this journal
                    debit = float(row.get(8, 0)) if pd.notna(row.get(8)) else 0.0
                    credit = float(row.get(9, 0)) if pd.notna(row.get(9)) else 0.0
                    if debit != 0 or credit != 0:
                        current_journal['lines'].append((account_name, debit, credit))
                        current_journal['memo_lines'].append(f"{account_name} Dr:{debit:.2f} Cr:{credit:.2f}")

                elif current_journal:
                    desc = str(row.get(1, '')).strip().replace('_x000D_', ' ').strip()

                    debit = float(row.get(8, 0)) if pd.notna(row.get(8)) else 0.0
                    credit = float(row.get(9, 0)) if pd.notna(row.get(9)) else 0.0

                    if debit != 0 or credit != 0:
                        current_journal['lines'].append((desc, debit, credit))
                        current_journal['memo_lines'].append(f"{desc} Dr:{debit:.2f} Cr:{credit:.2f}")

                    # Capture notes / descriptions when no amount
                    elif desc and desc.lower() not in ['agst ref', 'new ref']:
                        current_journal['memo_lines'].append(f"Note: {desc}")

                    # Agst Ref / New Ref (for memo only)
                    if 'Agst Ref' in desc or 'New Ref' in desc:
                        ref = str(row.get(2, '')).strip().replace('_x000D_', ' ')
                        if ref:
                            current_journal['memo_lines'].append(f"{desc}: {ref}")

            if current_journal:
                journals.append(current_journal)

            # ==================== CREATE ODOO JOURNAL ENTRIES ====================
            journal_journal = self.env['account.journal'].search([('name', '=', 'Journal')], limit=1)
            if not journal_journal:
                raise UserError("------------Journal journal not found. Please create a journal named 'Journal' (type = General).")

            for journal_data in journals:
                memo = "\n".join(journal_data['memo_lines']).strip() or f"Journal {journal_data['vch_no']}"

                line_ids = []
                for account_name, debit, credit in journal_data['lines']:
                    # Search account - exact match first
                    account = self.env['account.account'].search([('name', '=', account_name)], limit=1)
                    if not account:
                        # Fallback partial match
                        raise UserError(f"-------------Account '{account_name}' not found for journal {journal_data['vch_no']}. Please ensure all accounts are created before importing.")

                    partner = self.env['res.partner'].search([('name', '=', account_name)], limit=1)

                    line_ids.append((0, 0, {
                        'account_id': account.id,
                        'partner_id': partner.id if partner else False,
                        'debit': debit,
                        'credit': credit,
                        'name': account_name,
                    }))

                if not line_ids:
                    raise UserError(f"---------- Journal {journal_data['vch_no']} has no valid lines with accounts.")

                move = self.env['account.move'].create({
                    'date': journal_data.get('date') or fields.Date.today(),
                    'ref': journal_data['vch_no'],
                    'journal_id': journal_journal.id,
                    'move_type': 'entry',
                    'narration': memo,
                    'line_ids': line_ids,
                })
                move.action_post()

                _logger.info(
                    f"---------------✅ Created Journal Entry {move.name} - Vch No: {journal_data['vch_no']} ({len(line_ids)} lines)")

            return True

        else:
            # ====================== OLD LOGIC FOR LASERTECH (UNCHANGED) ======================
            journals = []
            current_journal = None

            for i in range(len(df)):
                row = df.iloc[i]
                if row.dropna().empty:
                    continue

                if pd.notna(row.get(6)) and str(row.get(6, '')).strip() == 'Journal' and pd.notna(
                        row.get(7)) and pd.notna(row.get(8)):
                    if current_journal:
                        journals.append(current_journal)

                    inv_date = None
                    if pd.notna(row.get(0)):
                        if isinstance(row[0], datetime):
                            inv_date = row[0].date()
                        elif isinstance(row[0], str):
                            try:
                                inv_date = datetime.strptime(row[0], '%d-%b-%y').date()
                            except ValueError:
                                pass

                    partner_name = str(row.get(1, 'Unknown Partner')).strip()
                    if pd.notna(row.get(0)) and str(row[0]).isdigit():
                        partner_name = f"{row[0]} - {partner_name}".strip()

                    current_journal = {
                        'date': inv_date,
                        'partner': partner_name,
                        'vch_no': str(row.get(7, 'Unknown')).strip(),
                        'memo_lines': [],
                        'lines': [],
                    }

                    try:
                        debit = float(row[8])
                        current_journal['lines'].append((partner_name, debit, 0.0))
                    except ValueError:
                        pass

                elif current_journal:
                    desc = str(row.get(1, '')).strip()

                    if desc:
                        debit = 0.0
                        if pd.notna(row.get(8)):
                            try:
                                debit = float(row[8])
                            except ValueError:
                                debit = 0.0

                        credit = 0.0
                        if pd.notna(row.get(9)):
                            try:
                                credit = float(row[9])
                            except ValueError:
                                credit = 0.0

                        if debit != 0 or credit != 0:
                            current_journal['lines'].append((desc, debit, credit))

                    if desc and not pd.notna(row.get(8)) and not pd.notna(row.get(9)):
                        current_journal['memo_lines'].append(f"Note: {desc}")

            if current_journal:
                journals.append(current_journal)

            misc_journal = self.env['account.journal'].search([('type', '=', 'general'), ('name', '=', 'Journal')],
                                                              limit=1)
            if not misc_journal:
                raise UserError("No Journal journal found.")

            for journal_data in journals:
                memo = "\n".join(journal_data['memo_lines']).strip() or f"Journal {journal_data['vch_no']}"

                line_ids = []
                for account_name, debit, credit in journal_data['lines']:
                    account = self.env['account.account'].search([('name', '=', account_name)], limit=1)
                    if not account:
                        _logger.warning(
                            f"Skipping line in {journal_data['vch_no']} - Account '{account_name}' not found.")
                        continue

                    partner = self.env['res.partner'].search([('name', '=', account_name)], limit=1)

                    line_ids.append((0, 0, {
                        'account_id': account.id,
                        'partner_id': partner.id if partner else False,
                        'debit': debit,
                        'credit': credit,
                        'name': account_name,
                    }))

                if not line_ids:
                    continue

                move_vals = {
                    'date': journal_data.get('date') or self.default_date,
                    'ref': "Journal " + journal_data['vch_no'],
                    'journal_id': misc_journal.id,
                    'move_type': 'entry',
                    'narration': memo,
                    'line_ids': line_ids,
                }
                move = self.env['account.move'].create(move_vals)
                move.action_post()

                _logger.info(f"Created journal entry {move.name} for journal voucher {journal_data['vch_no']}")

            return True

    def _import_contra(self, df):
        # Detect company based on header
        company = 'lasertech'
        for row_idx in range(10):
            row = df.iloc[row_idx]
            if pd.notna(row.get(0)) and 'ADROIT ENGINEERING' in str(row[0]).strip():
                company = 'engineering'
                break

        contras = []
        current_contra = None

        if company == 'engineering':
            for i in range(len(df)):
                row = df.iloc[i]
                if row.dropna().empty:
                    continue

                # === Detect new Contra voucher ===
                if pd.notna(row.get(4)) and str(row.get(4, '')).strip() == 'Contra' and pd.notna(row.get(5)):
                    if current_contra:
                        contras.append(current_contra)

                    inv_date = None
                    if pd.notna(row.get(0)):
                        if isinstance(row[0], datetime):
                            inv_date = row[0].date()
                        elif isinstance(row[0], (int, float)):
                            try:
                                inv_date = (datetime(1899, 12, 30) + timedelta(days=float(row[0]))).date()
                            except:
                                pass
                        elif isinstance(row[0], str):
                            try:
                                inv_date = datetime.strptime(row[0].strip(), '%d-%b-%Y').date()
                            except:
                                pass

                    account_name = str(row.get(1, 'Cash')).strip().replace('_x000D_', ' ').strip()

                    current_contra = {
                        'date': inv_date,
                        'vch_no': str(row.get(5, '')).strip(),
                        'lines': [],  # (account_name, debit, credit)
                        'memo_lines': [],
                    }

                    # === Add FIRST line correctly (check both debit & credit column) ===
                    debit = float(row.get(6, 0)) if pd.notna(row.get(6)) else 0.0
                    credit = float(row.get(7, 0)) if pd.notna(row.get(7)) else 0.0

                    if debit != 0 or credit != 0:
                        current_contra['lines'].append((account_name, debit, credit))
                        current_contra['memo_lines'].append(f"{account_name} Dr:{debit:.2f} Cr:{credit:.2f}")

                elif current_contra:
                    desc = str(row.get(1, '')).strip().replace('_x000D_', ' ').strip()

                    debit = float(row.get(6, 0)) if pd.notna(row.get(6)) else 0.0
                    credit = float(row.get(7, 0)) if pd.notna(row.get(7)) else 0.0

                    if debit != 0 or credit != 0:
                        current_contra['lines'].append((desc, debit, credit))
                        current_contra['memo_lines'].append(f"{desc} Dr:{debit:.2f} Cr:{credit:.2f}")

                    # Notes
                    if desc and debit == 0 and credit == 0 and desc not in ['Cash', '']:
                        current_contra['memo_lines'].append(f"Note: {desc}")

            if current_contra:
                contras.append(current_contra)

            # ====================== CREATE ENTRIES ======================
            contra_journal = self.env['account.journal'].search([('name', 'ilike', 'Contra')], limit=1)
            if not contra_journal:
                raise UserError("Contra journal not found. Please create one with 'Contra' in the name.")

            for contra_data in contras:
                memo = "\n".join(contra_data['memo_lines']).strip() or f"Contra {contra_data['vch_no']}"
                line_ids = []

                for account_name, debit, credit in contra_data['lines']:
                    if account_name == 'nan':
                        continue
                    account = self.env['account.account'].search([('name', '=', account_name)], limit=1)
                    if not account:
                        import pdb; pdb.set_trace()
                        # account = self.env['account.account'].search([('name', 'ilike', account_name[:40])], limit=1)

                    # if not account:
                    #     if 'CASH' in account_name.upper():
                    #         account = self.env['account.account'].search([('name', 'ilike', 'Cash')], limit=1)
                    #     else:
                    #         account = self.env['account.account'].search([('name', 'ilike', 'Bank')], limit=1)
                    #
                    # if not account:
                    #     _logger.warning(f"Account not found: {account_name} in voucher {contra_data['vch_no']}")
                    #     continue

                    line_ids.append((0, 0, {
                        'account_id': account.id,
                        'debit': debit,
                        'credit': credit,
                        'name': account_name,
                    }))

                if not line_ids:
                    continue

                try:
                    move = self.env['account.move'].create({
                        'date': contra_data.get('date') or fields.Date.today(),
                        'ref': contra_data['vch_no'],
                        'journal_id': contra_journal.id,
                        'move_type': 'entry',
                        'narration': memo,
                        'line_ids': line_ids,
                    })
                except:
                    import pdb; pdb.set_trace()
                move.action_post()

                _logger.info(f"------------ ✅ Created Contra {move.name} - {contra_data['vch_no']}--------------")

            return True

        else:
            # Old lasertech logic
            _logger.info("Old lasertech contra logic")
            return True

    def _import_credit_note(self, df):
        # Detect company based on header
        company = 'lasertech'
        for row_idx in range(10):
            row = df.iloc[row_idx]
            if pd.notna(row.get(0)) and 'ADROIT ENGINEERING' in str(row[0]).strip():
                company = 'engineering'
                break
            if pd.notna(row.get(0)) and 'ADROITRE ENERGY LLP' in str(row[0]).strip():
                company = 'energyllp'
                break

        credit_notes = []
        current_cn = None

        if company == 'engineering':
            # ====================== NEW LOGIC FOR ADROIT ENGINEERING ======================
            for i in range(len(df)):
                row = df.iloc[i].dropna(how='all')
                if row.empty:
                    continue

                # Detect new Credit Note
                if pd.notna(row.get(0)) and (
                        isinstance(row.get(0), datetime) or isinstance(row.get(0), (int, float))) and \
                        pd.notna(row.get(6)) and 'Credit Note' in str(row.get(6)).strip() and pd.notna(row.get(7)):

                    if current_cn:
                        credit_notes.append(current_cn)

                    # Date
                    inv_date = row[0]
                    if not isinstance(inv_date, datetime):
                        try:
                            inv_date = datetime(1899, 12, 30) + timedelta(days=float(inv_date))
                        except:
                            continue

                    customer = str(row.get(1, '')).strip().replace('_x000D_', ' ').strip()
                    if not customer:
                        import pdb; pdb.set_trace()

                    current_cn = {
                        'date': inv_date.date(),
                        'customer': customer,
                        'ref': str(row.get(7)).strip(),  # CN24250001 etc.
                        'lines': [],
                        'agst_ref': None,
                    }

                elif current_cn:
                    desc = str(row.get(1, '')).strip().replace('_x000D_', ' ').strip()

                    # Agst Ref (link to original invoice)
                    if 'Agst Ref' in desc and pd.notna(row.get(2)):
                        current_cn['agst_ref'] = str(row.get(2)).strip()

                    # Product / Service lines
                    if pd.notna(row.get(1)) and pd.notna(row.get(4)) and '@' not in desc:
                        try:
                            product_name = desc
                            qty = float(row.get(2, 1.0)) if pd.notna(row.get(2)) else 1.0
                            price = float(row.get(3)) if pd.notna(row.get(3)) else float(row.get(4)) / qty
                            current_cn['lines'].append({
                                'name': product_name,
                                'quantity': qty,
                                'price_unit': price
                            })
                        except:
                            pass

                    # GST lines (Output IGST / CGST / SGST)
                    # if ('Output IGST' in desc or 'Output CGST' in desc or 'Output SGST' in desc) and pd.notna(
                    #         row.get(9)):
                    #     try:
                    #         tax_amount = float(row.get(9))
                    #         current_cn['lines'].append({
                    #             'name': desc,
                    #             'quantity': 1.0,
                    #             'price_unit': tax_amount
                    #         })
                    #     except:
                    #         pass

            if current_cn:
                credit_notes.append(current_cn)

            # ====================== CREATE ODOO CREDIT NOTES ======================
            import pdb;pdb.set_trace()
            for cn_data in credit_notes:
                partner = self.env['res.partner'].search([('name', '=', cn_data['customer'])], limit=1)
                if not partner:
                    raise ValueError(f"------------------- Customer '{cn_data['customer']}' not found. Please create it before importing.")

                # Credit note lines
                cn_lines = []
                for line in cn_data['lines']:
                    product = self.env['product.product'].search([('name', '=', line['name'])], limit=1)
                    if not product:
                        raise ValueError(f"--------------- Product/Service '{line['name']}' not found. Please create it before importing.")
                        # Fallback: create as service if not found (you can comment this if you prefer error)
                        # product = self.env['product.product'].create({
                        #     'name': line['name'],
                        #     'type': 'service',
                        #     'list_price': line['price_unit'],
                        # })

                    cn_lines.append((0, 0, {
                        'product_id': product.id,
                        'quantity': line['quantity'],
                        'price_unit': line['price_unit'],
                        # Add tax_ids here if you want (same as sales)
                    }))

                # Create Credit Note (out_refund)
                credit_note = self.env['account.move'].create({
                    'partner_id': partner.id,
                    'move_type': 'out_refund',
                    'ref': cn_data['ref'],
                    'invoice_date': cn_data['date'],
                    'date': cn_data['date'],
                    'invoice_line_ids': cn_lines,
                })

                credit_note.action_post()

                # Optional: Link to original invoice via Agst Ref (reconciliation)
                if cn_data.get('agst_ref'):
                    original_invoice = self.env['account.move'].search([
                        ('ref', '=', cn_data['agst_ref']),
                        ('move_type', '=', 'out_invoice'),
                        ('state', '!=', 'cancel')
                    ], limit=1)
                    if original_invoice.state != 'posted':
                        original_invoice.action_post()  # Ensure original invoice is posted before reconciliation
                    lines_to_reconcile = (credit_note + original_invoice).line_ids.filtered(
                        lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
                    )

                    if len(lines_to_reconcile) > 1:
                        lines_to_reconcile.reconcile()

                _logger.info(
                    f"---------- Created Credit Note {credit_note.name} for {cn_data['customer']} (Ref: {cn_data['ref']}) ----------------------")

            return True
        elif company in ('energyllp'):
            for i in range(len(df)):
                row = df.iloc[i].dropna(how='all')
                if row.empty:
                    continue

                # Detect new Credit Note
                if pd.notna(row.get(0)) and (
                        isinstance(row.get(0), (datetime, int, float)) or str(row.get(0)).strip()) and \
                        pd.notna(row.get(6)) and 'Credit Note' in str(row.get(6)).strip() and pd.notna(row.get(7)):

                    if current_cn:
                        credit_notes.append(current_cn)

                    # Date parsing
                    inv_date = row[0]
                    if not isinstance(inv_date, datetime):
                        try:
                            inv_date = datetime(1899, 12, 30) + timedelta(days=float(inv_date))
                        except:
                            continue

                    customer = str(row.get(1, 'Unknown Customer')).strip().replace('_x000D_', ' ').strip()

                    current_cn = {
                        'date': inv_date.date(),
                        'customer': customer,
                        'ref': str(row.get(7)).strip(),  # CN2425001 etc.
                        'lines': [],  # (name, qty, price_unit)
                        'agst_ref': None,
                        'memo_lines': [],
                    }

                elif current_cn:
                    desc = str(row.get(1, '')).strip().replace('_x000D_', ' ').strip()

                    # Agst Ref (link to original invoice)
                    if ('Agst Ref' in desc or 'New Ref' in desc) and pd.notna(row.get(2)):
                        current_cn['agst_ref'] = str(row.get(2)).strip()
                        current_cn['memo_lines'].append(f"Agst Ref: {current_cn['agst_ref']}")

                    # Product / Service lines
                    if pd.notna(row.get(1)) and pd.notna(row.get(4)) and '@' not in desc and 'Output' not in desc:
                        try:
                            product_name = desc
                            qty = float(row.get(2, 1.0)) if pd.notna(row.get(2)) else 1.0
                            price = float(row.get(3)) if pd.notna(row.get(3)) else float(row.get(4)) / qty
                            current_cn['lines'].append({
                                'name': product_name,
                                'quantity': qty,
                                'price_unit': price
                            })
                            current_cn['memo_lines'].append(f"{product_name} x{qty} @ {price:.2f}")
                        except:
                            pass
                    if pd.notna(row.get(1)) and 'Metal Trolley' in row.get(1):
                        try:
                            product_name = 'Metal Trolley'
                            qty = float(row.get(2, 1.0)) if pd.notna(row.get(2)) else 1.0
                            price = float(row.get(3)) if pd.notna(row.get(3)) else 0.0
                            current_cn['lines'].append({
                                'name': product_name,
                                'quantity': qty,
                                'price_unit': price
                            })
                            current_cn['memo_lines'].append(f"{product_name} x{qty} @ {price:.2f}")
                        except:
                            pass

                    # GST lines (Output CGST / SGST / IGST)
                    if any(x in desc for x in ['Output CGST', 'Output SGST', 'Output IGST']) and pd.notna(row.get(8)):
                        try:
                            tax_amount = float(row.get(8)) if pd.notna(row.get(8)) else float(row.get(9))
                            current_cn['lines'].append({
                                'name': desc,
                                'quantity': 1.0,
                                'price_unit': tax_amount
                            })
                            current_cn['memo_lines'].append(f"{desc}: {tax_amount:.2f}")
                        except:
                            pass

                    # Notes / Remarks
                    if desc and not pd.notna(row.get(4)) and not pd.notna(row.get(8)) and not pd.notna(row.get(9)):
                        if desc not in ['Agst Ref', 'New Ref']:
                            current_cn['memo_lines'].append(f"Note: {desc}")

            if current_cn:
                credit_notes.append(current_cn)

            # ==================== CREATE ODOO CREDIT NOTES ====================
            import pdb;pdb.set_trace()
            for cn_data in credit_notes:
                partner = self.env['res.partner'].search([('name', '=', cn_data['customer'])], limit=1)
                if not partner:
                    raise ValueError(f"Customer '{cn_data['customer']}' not found. Please create it before importing.")

                cn_lines = []
                for line in cn_data['lines']:
                    if "Output" in line['name']:
                        continue
                    product = self.env['product.product'].search([('name', '=', line['name'])], limit=1)
                    if not product:
                        raise UserError('-------- Product Not found: ' + line['name'] + '. Please create it before importing.')

                    cn_lines.append((0, 0, {
                        'product_id': product.id,
                        'quantity': line['quantity'],
                        'price_unit': line['price_unit'],  # positive - Odoo will credit
                        'name': line['name'],
                    }))

                # Create Credit Note
                credit_note = self.env['account.move'].create({
                    'partner_id': partner.id,
                    'move_type': 'out_refund',
                    'ref': cn_data['ref'],
                    'invoice_date': cn_data['date'],
                    'date': cn_data['date'],
                    'invoice_line_ids': cn_lines,
                })
                credit_note.action_post()

                # Reconciliation with original invoice (via Agst Ref)
                if cn_data.get('agst_ref'):
                    original_invoice = self.env['account.move'].search([
                        ('ref', '=', cn_data['agst_ref']),
                        ('move_type', '=', 'out_invoice'),
                        ('state', '!=', 'cancel')
                    ], limit=1)
                    if original_invoice:
                        # Ensure both are posted
                        if original_invoice.state != 'posted':
                            original_invoice.action_post()

                        rec_lines = (credit_note + original_invoice).line_ids.filtered(
                            lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
                        )
                        if len(rec_lines) >= 2:
                            try:
                                rec_lines.reconcile()
                                _logger.info(
                                    f"Reconciled Credit Note {credit_note.name} with Invoice {original_invoice.name}")
                            except:
                                pass  # already reconciled or partial

                _logger.info(
                    f"---------- Created Credit Note {credit_note.name} for {cn_data['customer']} (Ref: {cn_data['ref']}) ----------------------")

            return True
        else:
            # Old logic for adroit lasertech (placeholder - you can add if needed)
            _logger.info("Old lasertech credit note logic - not implemented yet")
            return True

    def _import_debit_note(self, df):
        # Detect company based on header
        company = 'lasertech'
        for row_idx in range(10):
            row = df.iloc[row_idx]
            if pd.notna(row.get(0)) and 'ADROIT ENGINEERING' in str(row[0]).strip():
                company = 'engineering'
                break
            if pd.notna(row.get(0)) and 'ADROITRE ENERGY LLP' in str(row[0]).strip():
                company = 'energyllp'
                break

        debit_notes = []
        current_dn = None

        if company == 'engineering':
            # ====================== NEW LOGIC FOR ADROIT ENGINEERING ======================
            for i in range(len(df)):
                row = df.iloc[i].dropna(how='all')
                if row.empty:
                    continue

                # Detect new Debit Note
                if pd.notna(row.get(0)) and (
                        isinstance(row.get(0), datetime) or isinstance(row.get(0), (int, float))) and \
                        pd.notna(row.get(6)) and 'Debit Note' in str(row.get(6)).strip() and pd.notna(row.get(7)):

                    if current_dn:
                        debit_notes.append(current_dn)

                    # Date
                    inv_date = row[0]
                    if not isinstance(inv_date, datetime):
                        try:
                            inv_date = datetime(1899, 12, 30) + timedelta(days=float(inv_date))
                        except:
                            continue

                    supplier = str(row.get(1, '')).strip().replace('_x000D_', ' ').strip()
                    if not supplier:
                        supplier = 'Unknown Supplier'

                    current_dn = {
                        'date': inv_date.date(),
                        'supplier': supplier,
                        'ref': str(row.get(7)).strip(),  # DN2425001, CR/0038/24-25 etc.
                        'lines': [],
                        'agst_ref': None,
                    }

                elif current_dn:
                    desc = str(row.get(1, '')).strip().replace('_x000D_', ' ').strip()

                    # Agst Ref (link to original purchase invoice)
                    if 'Agst Ref' in desc and pd.notna(row.get(2)):
                        current_dn['agst_ref'] = str(row.get(2)).strip()

                    # Product / Service lines
                    if pd.notna(row.get(1)) and pd.notna(row.get(4)) and '@' not in desc:
                        try:
                            product_name = desc
                            qty = float(row.get(2, 1.0)) if pd.notna(row.get(2)) else 1.0
                            price = float(row.get(3)) if pd.notna(row.get(3)) else float(row.get(4)) / qty
                            current_dn['lines'].append({
                                'name': product_name,
                                'quantity': qty,
                                'price_unit': price
                            })
                        except:
                            pass

                    # GST lines (Input taxes - appear in debit column)
                    # if ('Input IGST' in desc or 'Input CGST' in desc or 'Input SGST' in desc) and pd.notna(row.get(9)):
                    #     try:
                    #         tax_amount = float(row.get(9))
                    #         current_dn['lines'].append({
                    #             'name': desc,
                    #             'quantity': 1.0,
                    #             'price_unit': tax_amount
                    #         })
                    #     except:
                    #         pass

            if current_dn:
                debit_notes.append(current_dn)

            # ====================== CREATE ODOO DEBIT NOTES ======================
            for dn_data in debit_notes:
                partner = self.env['res.partner'].search([('name', '=', dn_data['supplier'])], limit=1)
                if not partner:
                    raise ValueError(f"------------- Supplier '{dn_data['supplier']}' not found. Please create it before importing.")

                # Debit note lines
                dn_lines = []
                for line in dn_data['lines']:
                    product = self.env['product.product'].search([('name', '=', line['name'])], limit=1)
                    if not product:
                       raise ValueError(f"-------- Product/Service '{line['name']}' not found. Please create it before importing.")

                    dn_lines.append((0, 0, {
                        'product_id': product.id,
                        'quantity': line['quantity'],
                        'price_unit': line['price_unit'],
                    }))

                # Create Debit Note (in_refund = Vendor Debit Note)
                debit_note = self.env['account.move'].create({
                    'partner_id': partner.id,
                    'move_type': 'in_refund',
                    'ref': dn_data['ref'],
                    'invoice_date': dn_data['date'],
                    'date': dn_data['date'],
                    'invoice_line_ids': dn_lines,
                })

                debit_note.action_post()

                # Optional: Auto reconcile with original bill via Agst Ref
                if dn_data.get('agst_ref'):
                    original_bill = self.env['account.move'].search([
                        ('ref', '=', dn_data['agst_ref']),
                        ('move_type', '=', 'in_invoice'),
                        ('state', '!=', 'cancel')
                    ], limit=1)
                    if original_bill:
                        try:
                            # Reconcile payable lines
                            (debit_note.line_ids + original_bill.line_ids).filtered(
                                lambda l: l.account_id.account_type == 'liability_payable'
                            ).reconcile()
                        except:
                            pass

                _logger.info(
                    f"---------- Created Debit Note {debit_note.name} for {dn_data['supplier']} (Ref: {dn_data['ref']}) ----------------------")

            return True
        elif company in ('energyllp'):
            for i in range(len(df)):
                row = df.iloc[i].dropna(how='all')
                if row.empty:
                    continue

                # Detect new Debit Note
                if pd.notna(row.get(0)) and (
                        isinstance(row.get(0), (datetime, int, float)) or str(row.get(0)).strip()) and \
                        pd.notna(row.get(6)) and 'Debit Note' in str(row.get(6)).strip() and pd.notna(row.get(7)):

                    if current_dn:
                        debit_notes.append(current_dn)

                    # Date parsing
                    inv_date = row[0]
                    if not isinstance(inv_date, datetime):
                        try:
                            inv_date = datetime(1899, 12, 30) + timedelta(days=float(inv_date))
                        except:
                            continue

                    supplier = str(row.get(1, 'Unknown Supplier')).strip().replace('_x000D_', ' ').strip()

                    current_dn = {
                        'date': inv_date.date(),
                        'supplier': supplier,
                        'ref': str(row.get(7)).strip(),  # DN2526001, CN2425003 etc.
                        'lines': [],  # (name, qty, price_unit)
                        'agst_ref': None,
                        'memo_lines': [],
                    }

                elif current_dn:
                    desc = str(row.get(1, '')).strip().replace('_x000D_', ' ').strip()

                    # Agst Ref (link to original vendor bill)
                    if ('Agst Ref' in desc or 'New Ref' in desc) and pd.notna(row.get(2)):
                        current_dn['agst_ref'] = str(row.get(2)).strip()
                        current_dn['memo_lines'].append(f"Agst Ref: {current_dn['agst_ref']}")

                    # Product / Service lines
                    if pd.notna(row.get(1)) and pd.notna(row.get(4)) and '@' not in desc and 'Input' not in desc:
                        try:
                            product_name = desc
                            qty = float(row.get(2, 1.0)) if pd.notna(row.get(2)) else 1.0
                            price = float(row.get(3)) if pd.notna(row.get(3)) else float(row.get(4)) / qty
                            current_dn['lines'].append({
                                'name': product_name,
                                'quantity': qty,
                                'price_unit': price
                            })
                            current_dn['memo_lines'].append(f"{product_name} x{qty} @ {price:.2f}")
                        except:
                            pass

                    # Input Tax lines (CGST / SGST / IGST)
                    if any(x in desc for x in ['Input CGST', 'Input SGST', 'Input IGST']) and pd.notna(row.get(8)):
                        try:
                            tax_amount = float(row.get(8)) if pd.notna(row.get(8)) else float(row.get(9))
                            current_dn['lines'].append({
                                'name': desc,
                                'quantity': 1.0,
                                'price_unit': tax_amount
                            })
                            current_dn['memo_lines'].append(f"{desc}: {tax_amount:.2f}")
                        except:
                            pass

                    # Round Off & Notes
                    if 'Round Off' in desc:
                        current_dn['memo_lines'].append(f"Round Off: {desc}")
                    elif desc and not pd.notna(row.get(4)) and not pd.notna(row.get(8)) and not pd.notna(row.get(9)):
                        if desc not in ['Agst Ref', 'New Ref']:
                            current_dn['memo_lines'].append(f"Note: {desc}")

            if current_dn:
                debit_notes.append(current_dn)

            # ==================== CREATE ODOO DEBIT NOTES ====================
            for dn_data in debit_notes:
                partner = self.env['res.partner'].search([('name', '=', dn_data['supplier'])], limit=1)
                if not partner:
                    raise ValueError(f"Supplier '{dn_data['supplier']}' not found. Please create it before importing.")

                dn_lines = []
                for line in dn_data['lines']:
                    product = self.env['product.product'].search([('name', '=', line['name'])], limit=1)
                    if not product:
                        # Fallback: create as service
                        product = self.env['product.product'].create({
                            'name': line['name'],
                            'type': 'service',
                            'list_price': line['price_unit'],
                        })

                    dn_lines.append((0, 0, {
                        'product_id': product.id,
                        'quantity': line['quantity'],
                        'price_unit': line['price_unit'],  # positive value
                        'name': line['name'],
                    }))

                # Create Debit Note (in_refund = Vendor Debit Note)
                debit_note = self.env['account.move'].create({
                    'partner_id': partner.id,
                    'move_type': 'in_refund',
                    'ref': dn_data['ref'],
                    'invoice_date': dn_data['date'],
                    'date': dn_data['date'],
                    'invoice_line_ids': dn_lines,
                })
                debit_note.action_post()

                # Auto-reconcile with original vendor bill via Agst Ref
                if dn_data.get('agst_ref'):
                    original_bill = self.env['account.move'].search([
                        ('ref', '=', dn_data['agst_ref']),
                        ('move_type', '=', 'in_invoice'),
                        ('state', '!=', 'cancel')
                    ], limit=1)
                    if original_bill:
                        if original_bill.state != 'posted':
                            original_bill.action_post()

                        rec_lines = (debit_note + original_bill).line_ids.filtered(
                            lambda l: l.account_id.account_type == 'liability_payable' and not l.reconciled
                        )
                        if len(rec_lines) >= 2:
                            try:
                                rec_lines.reconcile()
                                _logger.info(f"Reconciled Debit Note {debit_note.name} with Bill {original_bill.name}")
                            except:
                                pass

                _logger.info(
                    f"---------- Created Debit Note {debit_note.name} for {dn_data['supplier']} (Ref: {dn_data['ref']}) ----------------------")

            return True
        else:
            # Old logic for lasertech (placeholder)
            _logger.info("Old lasertech debit note logic - not implemented yet")
            return True