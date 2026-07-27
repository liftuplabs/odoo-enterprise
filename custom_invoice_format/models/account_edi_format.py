
import re
import json
from datetime import timedelta
from markupsafe import Markup

from odoo import models, fields, api, _
from odoo.tools import html_escape
from odoo.exceptions import AccessError, UserError

import logging

_logger = logging.getLogger(__name__)


class AccountEdiFormatInt(models.Model):
    _inherit = "account.edi.format"

    def _check_move_configuration(self, move):
        _logger.info("---------------- Executing override _check_move_configuration ----------------")
        if self.code != "in_ewaybill_1_03":
            return super()._check_move_configuration(move)
        error_message = []
        base = self._l10n_in_edi_ewaybill_base_irn_or_direct(move)
        if not move.l10n_in_type_id and base == "direct":
            error_message.append(_("- Document Type"))
        if not move.l10n_in_mode:
            error_message.append(_("- Transportation Mode"))
        elif move.l10n_in_mode == "0" and not move.l10n_in_transporter_id:
            error_message.append(_("- Transporter is required when E-waybill is managed by transporter"))
        elif move.l10n_in_mode == "0" and move.l10n_in_transporter_id and not move.l10n_in_transporter_id.vat:
            error_message.append(_("- Selected Transporter is missing GSTIN"))
        elif move.l10n_in_mode == "1":
            if not move.l10n_in_vehicle_no and move.l10n_in_vehicle_type:
                error_message.append(_("- Vehicle Number and Type is required when Transportation Mode is By Road"))
        elif move.l10n_in_mode in ("2", "3", "4"):
            if not move.l10n_in_transportation_doc_no and move.l10n_in_transportation_doc_date:
                error_message.append(_("- Transport document number and date is required when Transportation Mode is Rail,Air or Ship"))
        if error_message:
            error_message.insert(0, _("The following information are missing on the invoice (see eWayBill tab):"))
        goods_lines = move.invoice_line_ids.filtered(lambda line: not (line.display_type in ('line_section', 'line_note', 'rounding') or line.product_id.type == "service"))
        # if not goods_lines:
        #     error_message.append(_('You need at least one product having "Product Type" as stockable or consumable.'))
        if base == "irn":
            # already checked by E-invoice (l10n_in_edi) so no need to check
            return error_message
        is_purchase = move.is_purchase_document(include_receipts=True)
        error_message += self._l10n_in_validate_partner(move.partner_id)
        error_message += self._l10n_in_validate_partner(move.company_id.partner_id, is_company=True)
        if not re.match("^.{1,16}$", is_purchase and move.ref or move.name):
            error_message.append(_("%s number should be set and not more than 16 characters",
                (is_purchase and "Bill Reference" or "Invoice")))
        for line in goods_lines:
            if line.display_type == 'product':
                hsn_code = self._l10n_in_edi_extract_digits(line.l10n_in_hsn_code)
                if not hsn_code:
                    error_message.append(_("HSN code is not set in product line %s", line.name))
                elif not re.match(r'^\d{4}$|^\d{6}$|^\d{8}$', hsn_code):
                    error_message.append(_(
                        "Invalid HSN Code (%(hsn_code)s) in product line %(product_line)s") % {
                        'hsn_code': hsn_code,
                        'product_line': line.product_id.name or line.name
                    })
        if error_message:
            error_message.insert(0, _("Impossible to send the Ewaybill."))
        return error_message

    def _l10n_in_edi_ewaybill_generate_json(self, invoices):
        # 1. Raise UserError if transaction_type is not set
        if not invoices.transaction_type:
            raise UserError(_("Please select transaction type."))

        def get_transaction_type(seller_details, dispatch_details, buyer_details, ship_to_details):
            """
                1 - Regular
                2 - Bill To - Ship To
                3 - Bill From - Dispatch From
                4 - Combination of 2 and 3
            """
            # 2. Use the manual transaction type since we already validated it exists
            if invoices.transaction_type:
                return int(invoices.transaction_type)

            # Fallback logic (safeguard)
            if seller_details != dispatch_details and buyer_details != ship_to_details:
                return 4
            elif seller_details != dispatch_details:
                return 3
            elif buyer_details != ship_to_details:
                return 2
            else:
                return 1

        saler_buyer = self._get_l10n_in_edi_saler_buyer_party(invoices)
        seller_details = saler_buyer.get("seller_details")
        dispatch_details = saler_buyer.get("dispatch_details")
        buyer_details = saler_buyer.get("buyer_details")
        ship_to_details = saler_buyer.get("ship_to_details")
        sign = invoices.is_inbound() and -1 or 1
        extract_digits = self._l10n_in_edi_extract_digits
        tax_details = self._l10n_in_prepare_edi_tax_details(invoices)
        tax_details_by_code = self._get_l10n_in_tax_details_by_line_code(tax_details.get("tax_details", {}))
        invoice_line_tax_details = tax_details.get("tax_details_per_record")
        rounding_amount = sum(line.balance for line in invoices.line_ids if line.display_type == 'rounding') * sign

        json_payload = {
            # Note:
            # Customer Invoice, Sales Receipt and Vendor Credit Note are Outgoing
            # Vendor Bill, Purchase Receipt, and Customer Credit Note are Incoming
            "supplyType": invoices.is_outbound() and "I" or "O",
            "subSupplyType": invoices.l10n_in_type_id.sub_type_code,
            "docType": invoices.l10n_in_type_id.code,
            "transactionType": get_transaction_type(seller_details, dispatch_details, buyer_details, ship_to_details),
            "transDistance": str(invoices.l10n_in_distance),
            "docNo": invoices.is_purchase_document(include_receipts=True) and invoices.ref or invoices.name,
            "docDate": invoices.date.strftime("%d/%m/%Y"),
            "fromGstin": seller_details.commercial_partner_id.vat or "URP",
            "fromTrdName": seller_details.commercial_partner_id.name,
            "fromAddr1": dispatch_details.street or "",
            "fromAddr2": dispatch_details.street2 or "",
            "fromPlace": dispatch_details.city or "",
            "fromPincode": dispatch_details.country_id.code == "IN" and int(extract_digits(dispatch_details.zip)) or "",
            "fromStateCode": int(seller_details.state_id.l10n_in_tin) or "",
            "actFromStateCode": dispatch_details.state_id.l10n_in_tin and int(
                dispatch_details.state_id.l10n_in_tin) or "",
            "toGstin": buyer_details.commercial_partner_id.vat or "URP",
            "toTrdName": buyer_details.commercial_partner_id.name,
            "toAddr1": ship_to_details.street or "",
            "toAddr2": ship_to_details.street2 or "",
            "toPlace": ship_to_details.city or "",
            "toPincode": int(extract_digits(ship_to_details.zip)),
            "actToStateCode": int(ship_to_details.state_id.l10n_in_tin),
            "toStateCode": invoices.l10n_in_state_id.l10n_in_tin and int(invoices.l10n_in_state_id.l10n_in_tin) or (
                    buyer_details.state_id.l10n_in_tin or int(buyer_details.state_id.l10n_in_tin) or ""
            ),
            "itemList": [
                self._get_l10n_in_edi_ewaybill_line_details(line, line_tax_details, sign)
                for line, line_tax_details in invoice_line_tax_details.items()
            ],
            "totalValue": self._l10n_in_round_value(tax_details.get("base_amount")),
            "cgstValue": self._l10n_in_round_value(tax_details_by_code.get("cgst_amount", 0.00)),
            "sgstValue": self._l10n_in_round_value(tax_details_by_code.get("sgst_amount", 0.00)),
            "igstValue": self._l10n_in_round_value(tax_details_by_code.get("igst_amount", 0.00)),
            "cessValue": self._l10n_in_round_value(tax_details_by_code.get("cess_amount", 0.00)),
            "cessNonAdvolValue": self._l10n_in_round_value(tax_details_by_code.get("cess_non_advol_amount", 0.00)),
            "otherValue": self._l10n_in_round_value(tax_details_by_code.get("other_amount", 0.00) + rounding_amount),
            "totInvValue": self._l10n_in_round_value(
                tax_details.get("base_amount") + tax_details.get("tax_amount") + rounding_amount),
        }
        is_overseas = invoices.l10n_in_gst_treatment in ("overseas", "special_economic_zone")
        if invoices.is_outbound():
            if is_overseas:
                json_payload.update({"fromStateCode": 99})
            if is_overseas and dispatch_details.state_id.country_id.code != "IN":
                json_payload.update({
                    "actFromStateCode": 99,
                    "fromPincode": 999999,
                })
            else:
                json_payload.update({
                    "actFromStateCode": dispatch_details.state_id.l10n_in_tin and int(
                        dispatch_details.state_id.l10n_in_tin) or "",
                    "fromPincode": int(extract_digits(dispatch_details.zip)),
                })
        else:
            if is_overseas:
                json_payload.update({"toStateCode": 99})
            if is_overseas and ship_to_details.state_id.country_id.code != "IN":
                # For exports without LUT, the e-waybill total invoice value must include Reverse Charges.
                # Reverse charge amounts are stored as a negative value,
                # so we subtract it here to effectively add it to the total. i.e. -(-x) = +x).
                adjusting_rc_amount = sum(
                    amount for code, amount in tax_details_by_code.items()
                    if code in ("cgst_rc_amount", "sgst_rc_amount", "igst_rc_amount")
                )
                json_payload.update({
                    "actToStateCode": 99,
                    "toPincode": 999999,
                    "totInvValue": json_payload["totInvValue"] - adjusting_rc_amount,
                })
            else:
                json_payload.update({
                    "actToStateCode": int(ship_to_details.state_id.l10n_in_tin),
                    "toPincode": int(extract_digits(ship_to_details.zip)),
                })

        if invoices.l10n_in_mode == "0":
            json_payload.update({
                "transporterId": invoices.l10n_in_transporter_id.vat or "",
                "transporterName": invoices.l10n_in_transporter_id.name or "",
            })
        if invoices.l10n_in_mode in ("2", "3", "4"):
            json_payload.update({
                "transMode": invoices.l10n_in_mode,
                "transDocNo": invoices.l10n_in_transportation_doc_no or "",
                "transDocDate": invoices.l10n_in_transportation_doc_date and
                                invoices.l10n_in_transportation_doc_date.strftime("%d/%m/%Y") or "",
            })
        if invoices.l10n_in_mode == "1":
            json_payload.update({
                "transMode": invoices.l10n_in_mode,
                "vehicleNo": invoices.l10n_in_vehicle_no or "",
                "vehicleType": invoices.l10n_in_vehicle_type or "",
                **{
                    k: v for k, v in {
                        "transporterId": invoices.l10n_in_transporter_id.vat,
                        "transporterName": invoices.l10n_in_transporter_id.name,
                    }.items() if v
                },
            })
        return json_payload