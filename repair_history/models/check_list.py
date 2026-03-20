from django.utils.duration import duration_string
from pkg_resources import require
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


class CheckList(models.Model):
    _name = 'check.list'
    _description = 'Test Check List'

    is_check = fields.Boolean("IS checked?")
    Check_list_id = fields.Many2one("repair.order", "Stock Transfer",invisible='1')
    question_id = fields.Many2one('check.list.question', string="Name Of Check List")


class CheckListQuestion(models.Model):
    _name = 'check.list.question'
    _description = "Check List Question"

    name = fields.Char("Name")
