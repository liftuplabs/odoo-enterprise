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



class DowntimeReasons(models.Model):
    _name = "downtime.reasons"
    _description = "Downtime Reasons"

    name = fields.Char(string="Reason", required=True, help="Name of the downtime reason.")
